import AppKit

final class Section: NSView {
    // title is nil when the header should keep the server's state, e.g. after a refused port or a missing download
    struct Failure {
        var title: String?
        var detail: String
        var command: String? = nil
        var log: String? = nil
    }

    private enum Phase { case loading, stopped, starting(String), running(Status), stopping(String), failed(Failure) }

    let project: Project
    var onOwn: ((String, Bool) -> Void)?
    private var rows: [ModelRow] = []
    private var selectedIndex = 0
    private var statuses: [String: Status] = [:]
    private var starter: Process?
    private var starting: String?
    private var stopping: String?
    private var failure: Failure?
    private var info = ""
    private var watched: String?           // a model this app started, to notice when it goes away
    private var polling = false
    private var copied: String?
    private var logged: String?

    private let light = StatusLight()
    private let spinner = NSProgressIndicator()
    private let state = label("", size: 12, weight: .medium)
    private let button = NSButton(title: "Start", target: nil, action: nil)
    private let group = GroupBox()
    private let detail = label("", size: 11.5, color: .secondaryLabelColor)
    private let copy = NSButton()
    private let showLog = NSButton(title: "Show Log", target: nil, action: nil)

    private var selected: Model? { rows.indices.contains(selectedIndex) ? rows[selectedIndex].model : nil }
    private var live: Status? { rows.compactMap { statuses[$0.model.name] }.first { $0.state != "stopped" } }
    private var ctlName: String { project.ctl.lastPathComponent }

    init(_ p: Project) {
        project = p
        super.init(frame: .zero)
        build()
    }
    required init?(coder: NSCoder) { fatalError() }

    private func build() {
        let title = label(project.title, size: 15, weight: .semibold)
        let subtitle = label(project.subtitle, size: 13, color: .secondaryLabelColor)
        let name = NSStackView(views: [title, subtitle])
        name.alignment = .firstBaseline
        name.spacing = 7
        spinner.style = .spinning
        spinner.controlSize = .small
        spinner.isDisplayedWhenStopped = false
        button.bezelStyle = .push
        button.target = self
        button.action = #selector(toggle)
        let head = NSStackView(views: [name, NSView(), spinner, light, state, button])
        head.spacing = 8
        head.setCustomSpacing(6, after: light)
        head.setCustomSpacing(12, after: state)

        copy.image = NSImage(systemSymbolName: "doc.on.doc", accessibilityDescription: "Copy")
        copy.bezelStyle = .accessoryBarAction
        copy.isBordered = false
        copy.contentTintColor = .secondaryLabelColor
        copy.target = self
        copy.action = #selector(copyDetail)
        showLog.isBordered = false
        showLog.font = .systemFont(ofSize: 11.5, weight: .medium)
        showLog.contentTintColor = .linkColor
        showLog.target = self
        showLog.action = #selector(openLog)
        let foot = NSStackView(views: [detail, copy, showLog, NSView()])
        foot.spacing = 4
        foot.setCustomSpacing(10, after: copy)
        foot.edgeInsets = NSEdgeInsets(top: 0, left: 12, bottom: 0, right: 12)

        let stack = NSStackView(views: [head, group, foot])
        stack.orientation = .vertical
        stack.spacing = 8
        stack.setCustomSpacing(6, after: group)
        stack.translatesAutoresizingMaskIntoConstraints = false
        addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: leadingAnchor), stack.trailingAnchor.constraint(equalTo: trailingAnchor),
            stack.topAnchor.constraint(equalTo: topAnchor), stack.bottomAnchor.constraint(equalTo: bottomAnchor),
            head.widthAnchor.constraint(equalTo: stack.widthAnchor),
            group.widthAnchor.constraint(equalTo: stack.widthAnchor),
            foot.widthAnchor.constraint(equalTo: stack.widthAnchor),
            foot.heightAnchor.constraint(equalToConstant: 16),   // fixed, so the window keeps its size whatever the line says
            light.widthAnchor.constraint(equalToConstant: 8), light.heightAnchor.constraint(equalToConstant: 8),
            button.widthAnchor.constraint(equalToConstant: 76),
        ])
        render()
    }

    // off the main thread: runCtl blocks
    func load() {
        let (code, out, err) = runCtl(project.ctl, ["list", "--json"])
        let ms = code == 0 ? try? JSONDecoder().decode([Model].self, from: Data(out.utf8)) : nil
        DispatchQueue.main.async {
            guard let ms, !ms.isEmpty else {
                let why = code != 0 ? lastLine(err) : ms == nil ? "\(self.ctlName) list --json printed something else." : "It lists no models."
                self.failure = Failure(title: "Can't read \(self.project.key).toml", detail: why)
                self.render()
                return
            }
            self.show(ms)
        }
    }

    private func show(_ ms: [Model]) {
        rows = ms.enumerated().map { i, m in
            let row = ModelRow(m, registry: "\(project.key).toml")
            row.onSelect = { [weak self] in self?.select(i) }
            row.onPort = { [weak self] port in self?.setPort(i, port) }
            return row
        }
        group.setRows(rows)
        let last = UserDefaults.standard.string(forKey: "model.\(project.key)")
        select(ms.firstIndex { $0.name == last } ?? ms.firstIndex { $0.isDefault } ?? 0)
        poll()
    }

    private func select(_ i: Int) {
        selectedIndex = i
        if let m = selected { UserDefaults.standard.set(m.name, forKey: "model.\(project.key)") }
        render()
    }

    // follows the servers themselves, so models started or stopped from the command line show up too
    func poll() {
        guard !polling, !rows.isEmpty else { return }
        polling = true
        DispatchQueue.global().async {
            let (code, out, _) = runCtl(self.project.ctl, ["status", "--json"])
            let list = code == 0 ? (try? JSONDecoder().decode([Status].self, from: Data(out.utf8))) : nil
            DispatchQueue.main.async {
                self.polling = false
                guard let list else { return }
                self.statuses = Dictionary(uniqueKeysWithValues: list.map { ($0.name, $0) })
                if let w = self.watched, self.statuses[w]?.state == "stopped", self.starting == nil, self.stopping == nil {
                    self.watched = nil
                    self.onOwn?(w, false)
                    self.failure = Failure(title: "Stopped unexpectedly", detail: "\(w) quit on its own; its log may say why.", log: w)
                }
                self.render()
            }
        }
    }

    private var phase: Phase {
        if let s = stopping { return .stopping(s) }
        if let s = starting { return .starting(s) }
        if let l = live { return l.state == "starting" ? .starting(l.name) : .running(l) }
        if let f = failure { return .failed(f) }
        return rows.isEmpty ? .loading : .stopped
    }

    func render() {
        let phase = self.phase
        var up: String?
        switch phase {
        case .starting(let n), .stopping(let n): up = n
        case .running(let s): up = s.name
        default: up = nil
        }
        if let up, let i = rows.firstIndex(where: { $0.model.name == up }), i != selectedIndex {
            selectedIndex = i
            UserDefaults.standard.set(up, forKey: "model.\(project.key)")
        }
        let free = freeGB()
        for (i, row) in rows.enumerated() {
            let look: ModelRow.Look = switch phase {
                case .running where row.model.name == up: .running
                case .starting where row.model.name == up: .starting
                case .stopping where row.model.name == up: .stopping
                case .running, .starting, .stopping: .waiting
                default: .idle(selected: i == selectedIndex)
            }
            row.update(look, free: free)
        }

        var title = "Stopped", color = NSColor.tertiaryLabelColor, loading = false
        var line = "", lineColor = NSColor.secondaryLabelColor
        var code: String?
        copied = nil
        logged = nil
        switch phase {
        case .loading:
            title = "Loading…"; loading = true
        case .stopped:
            line = info
        case .starting:
            title = "Starting…"; color = .systemOrange; line = "Loading the model can take a minute."
        case .running(let s):
            title = s.state == "external" ? "Running, not started here" : "Running"; color = .systemGreen
            code = s.url; copied = s.url
        case .stopping:
            title = "Stopping…"; color = .systemOrange
        case .failed(let f):
            if let t = f.title { title = t; color = .systemRed }
            line = f.detail; lineColor = .systemRed; logged = f.log
            // the command runs from anywhere as copied; it reads better with the ctl's name than its full path
            code = f.command?.replacingOccurrences(of: project.ctl.path, with: ctlName); copied = f.command
        }
        state.stringValue = title
        state.toolTip = title
        state.textColor = color == .tertiaryLabelColor ? .secondaryLabelColor : .labelColor
        light.color = color
        // the header spins only while the list loads; a model starting or stopping spins in its own row
        light.isHidden = loading
        if loading { spinner.startAnimation(nil) } else { spinner.stopAnimation(nil) }
        let style = NSMutableParagraphStyle()
        style.lineBreakMode = .byTruncatingTail
        let text = NSMutableAttributedString(string: line, attributes: [.font: NSFont.systemFont(ofSize: 11.5), .foregroundColor: lineColor, .paragraphStyle: style])
        if let code {
            let font = NSFont.monospacedSystemFont(ofSize: 11.5, weight: .regular)
            text.append(NSAttributedString(string: (line.isEmpty ? "" : " ") + code, attributes: [.font: font, .foregroundColor: lineColor, .paragraphStyle: style]))
        }
        detail.attributedStringValue = text
        detail.toolTip = text.string
        copy.isHidden = copied == nil
        copy.toolTip = copied.map { "Copy \($0)" }
        showLog.isHidden = logged.map { !FileManager.default.fileExists(atPath: logURL($0).path) } ?? true

        let l = live
        let isUp = l != nil || starting != nil
        button.title = isUp ? "Stop" : "Start"
        button.bezelColor = isUp ? nil : .controlAccentColor
        // a server another checkout or tool started has no pid file here, so the ctl cannot stop it
        button.isEnabled = stopping == nil && !rows.isEmpty && l?.state != "external"
        button.toolTip = l?.state == "external" ? "Started outside this project; stop it where it was started" : nil
    }

    private func logURL(_ model: String) -> URL { root.appendingPathComponent("logs/\(model).log") }

    @objc private func copyDetail() {
        guard let copied else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(copied, forType: .string)
        copy.image = NSImage(systemSymbolName: "checkmark", accessibilityDescription: "Copied")
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
            self.copy.image = NSImage(systemSymbolName: "doc.on.doc", accessibilityDescription: "Copy")
        }
    }

    @objc private func openLog() {
        if let logged { NSWorkspace.shared.open(logURL(logged)) }
    }

    @objc private func toggle() {
        window?.makeFirstResponder(nil)   // saves a port still being edited before Start reads it
        if live != nil || starting != nil { stop() } else { start() }
    }

    private func start() {
        guard let m = selected else { return }
        failure = nil
        info = ""
        if m.missing {
            failure = Failure(detail: "Download it first:", command: "\(project.ctl.path) pull \(m.name)")
            render()
            return
        }
        let free = freeGB()
        guard m.memory_gb > free, let window else { return launch(m) }
        let a = NSAlert()
        a.alertStyle = .warning
        a.messageText = "Not enough free memory for \(m.name)"
        a.informativeText = String(format: "It needs about %.0f GB and %.1f GB is free. Other apps or models may be swapped out.", m.memory_gb, free)
        a.addButton(withTitle: "Start Anyway")
        a.addButton(withTitle: "Cancel")
        a.beginSheetModal(for: window) { if $0 == .alertFirstButtonReturn { self.launch(m) } }
    }

    private func launch(_ m: Model) {
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
                    self.failure = Failure(title: "Failed to start", detail: lastLine(msg), log: m.name)
                }
                self.render()
                self.poll()
            }
        }
        do { try p.run() } catch {
            failure = Failure(title: "Can't run \(ctlName)", detail: "\(error)")
            render()
            return
        }
        starter = p
        starting = m.name
        watched = m.name
        onOwn?(m.name, true)
        render()
    }

    private func stop() {
        guard let name = starting ?? live?.name else { return }
        if let s = starter, s.isRunning { s.terminate() }   // the server runs in its own session; stop handles it
        starter = nil
        starting = nil
        stopping = name
        watched = nil
        failure = nil
        info = ""
        render()
        DispatchQueue.global().async {
            let (code, out, err) = runCtl(self.project.ctl, ["stop", name])
            DispatchQueue.main.async {
                self.stopping = nil
                self.onOwn?(name, false)
                if code != 0 { self.failure = Failure(title: "Failed to stop", detail: lastLine(err.isEmpty ? out : err)) }
                self.statuses[name] = nil
                self.render()
                self.poll()
            }
        }
    }

    // The ctl writes the port into its .toml, so the ctl, its MCP server and this app all use the same one.
    // It runs synchronously (usually well under a second; the ctl first checks that nothing answers on the old port)
    // so a Start pressed right after never uses the old port.
    private func setPort(_ i: Int, _ port: Int) {
        let m = rows[i].model
        let (code, out, err) = runCtl(project.ctl, ["port", m.name, String(port)])
        failure = nil
        info = ""
        if code != 0 {
            failure = Failure(detail: "\(m.name): " + lastLine(err.isEmpty ? out : err))   // the field has gone back to the old port
        } else {
            rows[i].setPort(port)
            info = "\(m.name) now uses port \(port)."
        }
        render()
    }
}
