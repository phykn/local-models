// LOCAL-MODELS.app: one window for the Kev decision models and the LLMs. Each section runs one model at a time and the
// sections are independent, so either or both can be up. Quitting the app stops the models it started, and only those.
// Built by scripts/build-app.sh, which writes the project path into Info.plist. Everything about the models comes from
// kevctl and llmctl (list --json, status --json, start, stop, port), so this app knows nothing Kev- or Qwen-specific.
import AppKit

let root = URL(fileURLWithPath: Bundle.main.infoDictionary?["ProjectRoot"] as? String ?? "")
let ownedFile = root.appendingPathComponent("logs/app-owned")   // "<ctl>\t<model>" per line; the watchdog stops these

struct Project { let key: String; let title: String; let subtitle: String; let ctl: URL }
let projects = [
    Project(key: "kev", title: "Kev", subtitle: "Decision models", ctl: root.appendingPathComponent(".venv/bin/kevctl")),
    Project(key: "llm", title: "LLM", subtitle: "Qwen", ctl: root.appendingPathComponent(".venv/bin/llmctl")),
]

struct Model: Decodable {
    let name: String
    var port: Int
    let memory_gb: Double
    let isDefault: Bool
    let note: String?
    let missing: Bool   // weights not downloaded
    enum CodingKeys: String, CodingKey { case name, port, memory_gb, isDefault = "default", note, missing }
}

struct Status: Decodable { let name: String; let state: String; let url: String }   // state: running, external, starting, stopped

func ctlProcess(_ ctl: URL, _ args: [String]) -> (Process, Pipe, Pipe) {
    let p = Process()
    p.executableURL = ctl
    p.arguments = args
    p.currentDirectoryURL = root
    let out = Pipe(), err = Pipe()
    p.standardOutput = out
    p.standardError = err
    return (p, out, err)
}

// Runs a ctl command to the end; returns its exit status, stdout and stderr. Call it off the main thread.
func runCtl(_ ctl: URL, _ args: [String]) -> (Int32, String, String) {
    let (p, out, err) = ctlProcess(ctl, args)
    do { try p.run() } catch { return (-1, "", "\(error)") }
    let o = out.fileHandleForReading.readDataToEndOfFile(), e = err.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    return (p.terminationStatus, String(data: o, encoding: .utf8) ?? "", String(data: e, encoding: .utf8) ?? "")
}

func lastLine(_ s: String) -> String { s.split(separator: "\n").last.map(String.init) ?? "" }

// Memory macOS can hand out without swapping, counted like llmctl's free_gb.
func freeGB() -> Double {
    var stats = vm_statistics64()
    var count = mach_msg_type_number_t(MemoryLayout<vm_statistics64>.size / MemoryLayout<integer_t>.size)
    let kr = withUnsafeMutablePointer(to: &stats) {
        $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) { host_statistics64(mach_host_self(), HOST_VM_INFO64, $0, &count) }
    }
    guard kr == KERN_SUCCESS else { return 0 }
    let pages = UInt64(stats.free_count) + UInt64(stats.inactive_count) + UInt64(stats.speculative_count) + UInt64(stats.purgeable_count)
    return Double(pages) * Double(vm_kernel_page_size) / 1_073_741_824
}

// Stops the models this app started once its process is gone, however it ended (quit, force quit, crash).
// applicationWillTerminate only runs on a normal quit; this child outlives the app because macOS does not kill
// children when their parent dies.
func startWatchdog() {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/bin/sh")
    p.arguments = ["-c", """
        app=$1; f=$2; while kill -0 "$app" 2>/dev/null; do sleep 1; done
        [ -f "$f" ] || exit 0
        while IFS="$(printf '\\t')" read -r ctl m; do "$ctl" stop "$m"; done < "$f"; rm -f "$f"
        """, "watchdog", String(getpid()), ownedFile.path]
    p.standardOutput = FileHandle.nullDevice
    p.standardError = FileHandle.nullDevice
    try? p.run()
}

func label(_ s: String, size: CGFloat, weight: NSFont.Weight = .regular, color: NSColor = .labelColor) -> NSTextField {
    let l = NSTextField(labelWithString: s)
    l.font = .systemFont(ofSize: size, weight: weight)
    l.textColor = color
    l.lineBreakMode = .byTruncatingTail
    return l
}

// A selectable card for one model: name, note (e.g. quantization) and memory.
final class ModelCard: NSView {
    let model: Model
    var onSelect: (() -> Void)?
    var selected = false { didSet { refresh() } }
    var enabled = true { didSet { alphaValue = enabled ? 1 : 0.5 } }
    private let check = NSImageView()

    init(_ m: Model) {
        model = m
        super.init(frame: .zero)
        wantsLayer = true
        layer?.cornerRadius = 10
        layer?.borderWidth = 1
        let name = label(m.name, size: 14, weight: .medium)
        let note = label(m.note ?? "", size: 12, color: m.missing ? .systemOrange : .secondaryLabelColor)
        let mem = label("\(Int(m.memory_gb)) GB", size: 12, color: .secondaryLabelColor)
        mem.alignment = .right
        // note and mem sit at the right edge, mem at a fixed width, so both line up across cards whatever the name length
        let row = NSStackView(views: [check, name, NSView(), note, mem])
        row.spacing = 10
        row.edgeInsets = NSEdgeInsets(top: 0, left: 14, bottom: 0, right: 16)
        row.translatesAutoresizingMaskIntoConstraints = false
        addSubview(row)
        NSLayoutConstraint.activate([
            row.leadingAnchor.constraint(equalTo: leadingAnchor), row.trailingAnchor.constraint(equalTo: trailingAnchor),
            row.topAnchor.constraint(equalTo: topAnchor), row.bottomAnchor.constraint(equalTo: bottomAnchor),
            check.widthAnchor.constraint(equalToConstant: 18),
            mem.widthAnchor.constraint(equalToConstant: 44),
            heightAnchor.constraint(equalToConstant: 44),
        ])
        refresh()
    }
    required init?(coder: NSCoder) { fatalError() }

    override func mouseDown(with e: NSEvent) { if enabled { onSelect?() } }
    override func viewDidChangeEffectiveAppearance() { refresh() }

    private func refresh() {
        effectiveAppearance.performAsCurrentDrawingAppearance {
            layer?.backgroundColor = (selected ? NSColor.controlAccentColor.withAlphaComponent(0.12)
                                              : NSColor.labelColor.withAlphaComponent(0.03)).cgColor
            layer?.borderColor = (selected ? NSColor.controlAccentColor : NSColor.labelColor.withAlphaComponent(0.12)).cgColor
        }
        check.image = NSImage(systemSymbolName: selected ? "checkmark.circle.fill" : "circle", accessibilityDescription: nil)
        check.contentTintColor = selected ? .controlAccentColor : .tertiaryLabelColor
    }
}

// The selected model's port next to Start: a small "PORT" caption and an editable number, styled like the cards.
final class PortBox: NSView {
    let field = NSTextField()
    var editing = false { didSet { refresh() } }
    var enabled = true { didSet { field.isEditable = enabled; alphaValue = enabled ? 1 : 0.5 } }

    init() {
        super.init(frame: .zero)
        wantsLayer = true
        layer?.cornerRadius = 7
        layer?.borderWidth = 1
        let caption = label("PORT", size: 9, weight: .semibold, color: .secondaryLabelColor)
        caption.attributedStringValue = NSAttributedString(string: "PORT", attributes: [.kern: 0.8, .font: caption.font!, .foregroundColor: NSColor.secondaryLabelColor])
        field.font = .monospacedDigitSystemFont(ofSize: 14, weight: .medium)
        field.isBordered = false
        field.drawsBackground = false
        field.focusRingType = .none
        field.alignment = .right
        let row = NSStackView(views: [caption, field])
        row.spacing = 6
        row.edgeInsets = NSEdgeInsets(top: 0, left: 10, bottom: 0, right: 10)
        row.translatesAutoresizingMaskIntoConstraints = false
        addSubview(row)
        NSLayoutConstraint.activate([
            row.leadingAnchor.constraint(equalTo: leadingAnchor), row.trailingAnchor.constraint(equalTo: trailingAnchor),
            row.centerYAnchor.constraint(equalTo: centerYAnchor),
        ])
        refresh()
    }
    required init?(coder: NSCoder) { fatalError() }

    override func mouseDown(with e: NSEvent) { if enabled { window?.makeFirstResponder(field) } }
    override func viewDidChangeEffectiveAppearance() { refresh() }

    private func refresh() {
        effectiveAppearance.performAsCurrentDrawingAppearance {
            layer?.backgroundColor = NSColor.labelColor.withAlphaComponent(editing ? 0.06 : 0.03).cgColor
            layer?.borderColor = (editing ? NSColor.controlAccentColor : NSColor.labelColor.withAlphaComponent(0.12)).cgColor
            layer?.borderWidth = editing ? 1.5 : 1
        }
    }
}

// A thin bar for the share of memory in use.
final class MemoryBar: NSView {
    var used = 0.0 { didSet { needsDisplay = true } }
    override func draw(_ r: NSRect) {
        let track = NSBezierPath(roundedRect: bounds, xRadius: bounds.height / 2, yRadius: bounds.height / 2)
        NSColor.labelColor.withAlphaComponent(0.08).setFill()
        track.fill()
        let w = max(bounds.height, bounds.width * min(max(used, 0), 1))
        (used > 0.9 ? NSColor.systemRed : used > 0.75 ? NSColor.systemOrange : NSColor.systemGreen).setFill()
        NSBezierPath(roundedRect: NSRect(x: 0, y: 0, width: w, height: bounds.height), xRadius: bounds.height / 2, yRadius: bounds.height / 2).fill()
    }
}

enum Look { case stopped, busy, running, failed }

// One project: its models, what is running, and Start/Stop. At most one of its models runs at a time.
final class Section: NSView, NSTextFieldDelegate {
    let project: Project
    var models: [Model] = []
    var cards: [ModelCard] = []
    var selectedIndex = 0
    var statuses: [String: Status] = [:]
    var starter: Process?       // the running "ctl start", while this app starts a model
    var starting: String?
    var stopping: String?
    var failure: (String, String)?   // title and detail of the last failed action, until the next action
    var info = ""                    // a passing note, e.g. a port change
    var watched: String?             // a model this app started, to notice when it goes away
    var polling = false
    var onOwn: ((String, Bool) -> Void)?

    let dot = NSView()
    let status = label("Loading…", size: 12, weight: .medium, color: .secondaryLabelColor)
    let spinner = NSProgressIndicator()
    let cardStack = NSStackView()
    let detail = label("", size: 11, color: .secondaryLabelColor)
    let copy = NSButton()
    let portBox = PortBox()
    let button = NSButton(title: "Start", target: nil, action: nil)
    var portField: NSTextField { portBox.field }

    var selected: Model? { models.indices.contains(selectedIndex) ? models[selectedIndex] : nil }
    var live: Status? { models.compactMap { statuses[$0.name] }.first { $0.state != "stopped" } }

    init(_ p: Project) {
        project = p
        super.init(frame: .zero)
        wantsLayer = true
        layer?.cornerRadius = 14
        build()
    }
    required init?(coder: NSCoder) { fatalError() }

    override func viewDidChangeEffectiveAppearance() {
        effectiveAppearance.performAsCurrentDrawingAppearance { layer?.backgroundColor = NSColor.labelColor.withAlphaComponent(0.04).cgColor }
    }

    func build() {
        viewDidChangeEffectiveAppearance()
        let title = label(project.title, size: 15, weight: .semibold)
        let subtitle = label(project.subtitle, size: 12, color: .secondaryLabelColor)
        dot.wantsLayer = true
        dot.layer?.cornerRadius = 4
        spinner.style = .spinning
        spinner.controlSize = .small
        spinner.isDisplayedWhenStopped = false
        let head = NSStackView(views: [title, subtitle, NSView(), spinner, dot, status])
        head.spacing = 8
        head.setCustomSpacing(6, after: dot)

        cardStack.orientation = .vertical
        cardStack.spacing = 8

        detail.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        copy.image = NSImage(systemSymbolName: "doc.on.doc", accessibilityDescription: "Copy address")
        copy.bezelStyle = .accessoryBarAction
        copy.isBordered = false
        copy.contentTintColor = .secondaryLabelColor
        copy.target = self
        copy.action = #selector(copyEndpoint)
        let detailRow = NSStackView(views: [detail, copy, NSView()])
        detailRow.spacing = 4

        portBox.toolTip = "Port of the selected model, saved to \(project.key).toml. Press Return to save."
        portField.delegate = self
        button.bezelStyle = .push
        button.controlSize = .large
        button.font = .systemFont(ofSize: 14, weight: .semibold)
        button.target = self
        button.action = #selector(toggle)
        button.setContentHuggingPriority(.defaultLow, for: .horizontal)
        let controls = NSStackView(views: [portBox, button])
        controls.spacing = 10

        let stack = NSStackView(views: [head, cardStack, detailRow, controls])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 10
        stack.setCustomSpacing(12, after: head)
        stack.setCustomSpacing(6, after: cardStack)
        stack.setCustomSpacing(6, after: detailRow)
        stack.edgeInsets = NSEdgeInsets(top: 14, left: 16, bottom: 16, right: 16)
        stack.translatesAutoresizingMaskIntoConstraints = false
        addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: leadingAnchor), stack.trailingAnchor.constraint(equalTo: trailingAnchor),
            stack.topAnchor.constraint(equalTo: topAnchor), stack.bottomAnchor.constraint(equalTo: bottomAnchor),
            dot.widthAnchor.constraint(equalToConstant: 8), dot.heightAnchor.constraint(equalToConstant: 8),
            head.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -32),
            cardStack.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -32),
            detailRow.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -32),
            detailRow.heightAnchor.constraint(equalToConstant: 16),   // fixed so the window does not jump between states
            controls.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -32),
            portBox.widthAnchor.constraint(equalToConstant: 96),
            portBox.heightAnchor.constraint(equalTo: button.heightAnchor, constant: -4),   // the push button's bezel sits 2pt inside its frame
            button.trailingAnchor.constraint(equalTo: controls.trailingAnchor),
        ])
        render()
    }

    // Reads the models from the ctl; called once, off the main thread.
    func load() {
        let (code, out, err) = runCtl(project.ctl, ["list", "--json"])
        let ms = code == 0 ? try? JSONDecoder().decode([Model].self, from: Data(out.utf8)) : nil
        DispatchQueue.main.async {
            guard let ms, !ms.isEmpty else {
                self.failure = ("Could not read \(self.project.key).toml", code == 0 ? "no models" : lastLine(err))
                self.render()
                return
            }
            self.models = ms
            for (i, m) in ms.enumerated() {
                let c = ModelCard(m)
                c.onSelect = { [weak s = self] in s?.select(i) }
                self.cards.append(c)
                self.cardStack.addArrangedSubview(c)
                c.widthAnchor.constraint(equalTo: self.cardStack.widthAnchor).isActive = true
            }
            let last = UserDefaults.standard.string(forKey: "model.\(self.project.key)")
            self.select(ms.firstIndex { $0.name == last } ?? ms.firstIndex { $0.isDefault } ?? 0)
            self.poll()
        }
    }

    func select(_ i: Int) {
        selectedIndex = i
        for (j, c) in cards.enumerated() { c.selected = j == i }
        if let m = selected {
            portField.stringValue = String(m.port)
            UserDefaults.standard.set(m.name, forKey: "model.\(project.key)")
        }
    }

    // The section shows what the servers are actually doing, not just what the last command reported.
    func poll() {
        guard !polling, !models.isEmpty else { return }
        polling = true
        DispatchQueue.global().async {
            let (code, out, _) = runCtl(self.project.ctl, ["status", "--json"])
            let rows = code == 0 ? (try? JSONDecoder().decode([Status].self, from: Data(out.utf8))) : nil
            DispatchQueue.main.async {
                self.polling = false
                guard let rows else { return }
                self.statuses = Dictionary(uniqueKeysWithValues: rows.map { ($0.name, $0) })
                if let w = self.watched, self.statuses[w]?.state == "stopped", self.starting == nil, self.stopping == nil {
                    self.watched = nil
                    self.onOwn?(w, false)
                    self.failure = ("\(w) stopped unexpectedly", "See logs/\(w).log")
                }
                self.render()
            }
        }
    }

    func render() {
        let l = live
        var look = Look.stopped, title = "Stopped", sub = info, endpoint = false
        if let s = stopping {
            look = .busy; title = "Stopping \(s)…"; sub = ""
        } else if let s = starting {
            look = .busy; title = "Starting \(s)…"; sub = "Loading the model can take a minute"
        } else if let l, l.state == "starting" {
            look = .busy; title = "Starting \(l.name)…"; sub = ""
        } else if let l {
            look = .running; title = l.name; sub = l.url; endpoint = true
            if l.state == "external" { title += " · not started here" }
        } else if let f = failure {
            look = .failed; title = f.0; sub = f.1
        } else if models.isEmpty {
            title = "Loading…"
        }
        status.stringValue = title
        status.toolTip = title
        status.textColor = look == .stopped ? .secondaryLabelColor : .labelColor
        detail.stringValue = sub
        detail.toolTip = sub
        detail.textColor = look == .failed ? .systemRed : .secondaryLabelColor
        copy.isHidden = !endpoint
        let color: NSColor = switch look {
            case .running: .systemGreen
            case .busy: .systemOrange
            case .failed: .systemRed
            case .stopped: .tertiaryLabelColor
        }
        dot.layer?.backgroundColor = color.cgColor
        if look == .busy { spinner.startAnimation(nil) } else { spinner.stopAnimation(nil) }

        let up = l != nil || starting != nil
        button.title = up ? "Stop" : "Start"
        button.bezelColor = up ? .systemRed : .controlAccentColor
        // a server another checkout or tool started has no pid file here, so the ctl cannot stop it
        button.isEnabled = stopping == nil && !models.isEmpty && l?.state != "external"
        button.toolTip = l?.state == "external" ? "Started outside this project; stop it where it was started" : nil
        let idle = !up && stopping == nil
        cards.forEach { $0.enabled = idle }
        portBox.enabled = idle && !models.isEmpty
        // show the running model as the selection
        if let name = l?.name ?? starting, let i = models.firstIndex(where: { $0.name == name }), i != selectedIndex { select(i) }
    }

    @objc func copyEndpoint() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(detail.stringValue, forType: .string)
        copy.image = NSImage(systemSymbolName: "checkmark", accessibilityDescription: "Copied")
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
            self.copy.image = NSImage(systemSymbolName: "doc.on.doc", accessibilityDescription: "Copy address")
        }
    }

    @objc func toggle() {
        window?.makeFirstResponder(nil)   // saves a port still being edited before Start reads it
        if live != nil || starting != nil { stop() } else { start() }
    }

    func start() {
        guard let m = selected else { return }
        failure = nil
        info = ""
        if m.missing {
            failure = ("\(m.name) is not downloaded", "Run: \(project.ctl.lastPathComponent) pull \(m.name)")
            render()
            return
        }
        let free = freeGB()
        if m.memory_gb > free {
            let a = NSAlert()
            a.messageText = "Not enough free memory for \(m.name)"
            a.informativeText = String(format: "It needs about %.0f GB and %.1f GB is free. Other apps or models may be swapped out.", m.memory_gb, free)
            a.addButton(withTitle: "Start Anyway")
            a.addButton(withTitle: "Cancel")
            guard a.runModal() == .alertFirstButtonReturn else { return }
        }
        let (p, out, err) = ctlProcess(project.ctl, ["start", m.name])
        p.terminationHandler = { p in
            let msg = String(data: out.fileHandleForReading.readDataToEndOfFile() + err.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            DispatchQueue.main.async {
                guard self.starter === p else { return }   // Stop was pressed meanwhile
                self.starter = nil
                self.starting = nil
                if p.terminationStatus != 0 {
                    self.watched = nil
                    self.onOwn?(m.name, false)
                    self.failure = ("\(m.name) failed to start", lastLine(msg))
                }
                self.render()
                self.poll()
            }
        }
        do { try p.run() } catch {
            failure = ("Could not run \(project.ctl.lastPathComponent)", "\(error)")
            render()
            return
        }
        starter = p
        starting = m.name
        watched = m.name
        onOwn?(m.name, true)
        render()
    }

    func stop() {
        guard let name = starting ?? live?.name else { return }
        if let s = starter, s.isRunning { s.terminate() }   // the server runs in its own session; stop handles it
        starter = nil
        starting = nil
        stopping = name
        watched = nil
        failure = nil
        render()
        DispatchQueue.global().async {
            let (code, out, err) = runCtl(self.project.ctl, ["stop", name])
            DispatchQueue.main.async {
                self.stopping = nil
                self.onOwn?(name, false)
                if code != 0 { self.failure = ("Could not stop \(name)", lastLine(err.isEmpty ? out : err)) }
                self.statuses[name] = nil
                self.render()
                self.poll()
            }
        }
    }

    func controlTextDidBeginEditing(_ note: Notification) { portBox.editing = true }

    // Return or leaving the field saves; anything that is not a number goes back to the current port.
    func controlTextDidEndEditing(_ note: Notification) {
        portBox.editing = false
        guard let m = selected else { return }
        let p = Int(portField.stringValue.trimmingCharacters(in: .whitespaces))
        portField.stringValue = String(m.port)
        if let p, p != m.port { setPort(p) }
    }

    // The ctl writes the port into its .toml, so the ctl, its MCP server and this app all use the same one.
    // It runs synchronously (well under a second) so a Start pressed right after never uses the old port.
    func setPort(_ port: Int) {
        guard let m = selected else { return }
        let (code, out, err) = runCtl(project.ctl, ["port", m.name, String(port)])
        failure = nil
        if code != 0 {
            failure = ("Could not change the port", lastLine(err.isEmpty ? out : err))
        } else {
            models[selectedIndex].port = port
            portField.stringValue = String(port)
            info = "\(m.name) now uses port \(port)"
        }
        render()
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 460, height: 100),
                          styleMask: [.titled, .closable, .miniaturizable, .fullSizeContentView], backing: .buffered, defer: false)
    let sections = projects.map(Section.init)
    let memText = label("", size: 11, color: .secondaryLabelColor)
    let memBar = MemoryBar()
    var owned: [(URL, String)] = []

    func applicationDidFinishLaunching(_ note: Notification) {
        buildWindow()
        for s in sections {
            s.onOwn = { [weak self, weak s] name, on in if let s { self?.own(s.project.ctl, name, on) } }
            DispatchQueue.global().async { s.load() }
        }
        startWatchdog()
        updateMemory()
        Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { _ in
            self.sections.forEach { $0.poll() }
            self.updateMemory()
        }
    }

    func buildWindow() {
        window.title = "Local Models"
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.isMovableByWindowBackground = true
        let bg = NSVisualEffectView()
        bg.material = .underWindowBackground
        bg.blendingMode = .behindWindow
        bg.state = .active
        window.contentView = bg

        let memTitle = label("Memory", size: 11, weight: .medium, color: .secondaryLabelColor)
        memText.alignment = .right
        let memRow = NSStackView(views: [memTitle, memBar, memText])
        memRow.spacing = 10

        let stack = NSStackView(views: sections + [memRow])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 12
        stack.setCustomSpacing(16, after: sections.last!)
        stack.edgeInsets = NSEdgeInsets(top: 38, left: 20, bottom: 18, right: 20)
        stack.translatesAutoresizingMaskIntoConstraints = false
        bg.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: bg.leadingAnchor), stack.trailingAnchor.constraint(equalTo: bg.trailingAnchor),
            stack.topAnchor.constraint(equalTo: bg.topAnchor), stack.bottomAnchor.constraint(equalTo: bg.bottomAnchor),
            bg.widthAnchor.constraint(equalToConstant: 460),
            memRow.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -48),
            memBar.heightAnchor.constraint(equalToConstant: 6),
            memText.widthAnchor.constraint(equalToConstant: 150),
        ] + sections.map { $0.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -40) })
        memRow.edgeInsets = NSEdgeInsets(top: 0, left: 4, bottom: 0, right: 4)
        window.center()
        window.makeKeyAndOrderFront(nil)
        window.makeFirstResponder(nil)   // otherwise a port field takes focus on launch
        NSApp.activate(ignoringOtherApps: true)
    }

    func updateMemory() {
        let total = Double(ProcessInfo.processInfo.physicalMemory) / 1_073_741_824
        let free = freeGB()
        memBar.used = 1 - free / total
        memText.stringValue = String(format: "%.1f GB free of %.0f GB", free, total)
    }

    // Keeps logs/app-owned in step with the models this app started, for the watchdog.
    func own(_ ctl: URL, _ name: String, _ on: Bool) {
        owned.removeAll { $0 == (ctl, name) }
        if on { owned.append((ctl, name)) }
        try? FileManager.default.createDirectory(at: ownedFile.deletingLastPathComponent(), withIntermediateDirectories: true)
        try? owned.map { "\($0.0.path)\t\($0.1)\n" }.joined().write(to: ownedFile, atomically: true, encoding: .utf8)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { true }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
let menu = NSMenu(), appItem = NSMenuItem(), appMenu = NSMenu()
appMenu.addItem(withTitle: "Quit Local Models", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
appItem.submenu = appMenu
menu.addItem(appItem)
let editItem = NSMenuItem(), editMenu = NSMenu(title: "Edit")   // so ⌘C/⌘V/⌘A work in the port fields
editMenu.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
editMenu.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
editMenu.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
editMenu.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
editItem.submenu = editMenu
menu.addItem(editItem)
app.mainMenu = menu
app.run()
