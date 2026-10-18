// The window, its sections and memory gauge, and the models this app started: a watchdog stops those once the app is
// gone, however it ended.
import AppKit

let ownedFile = root.appendingPathComponent("logs/app-owned")   // "<ctl>\t<model>" per line; the watchdog stops these

final class AppDelegate: NSObject, NSApplicationDelegate {
    let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 460, height: 100),
                          styleMask: [.titled, .closable, .miniaturizable, .fullSizeContentView], backing: .buffered, defer: false)
    let sections = projects.map(Section.init)
    let gauge = MemoryGauge()
    private var owned: [(URL, String)] = []

    func applicationDidFinishLaunching(_ note: Notification) {
        // a list left by an earlier run whose watchdog never ran, e.g. across a reboot; this run started none of those
        try? FileManager.default.removeItem(at: ownedFile)
        buildWindow()
        window.center()
        window.makeKeyAndOrderFront(nil)
        window.makeFirstResponder(nil)   // otherwise a port field takes focus on launch
        NSApp.activate(ignoringOtherApps: true)
        for s in sections {
            s.onOwn = { [weak self, weak s] name, on in if let s { self?.own(s.project.ctl, name, on) } }
            DispatchQueue.global().async { s.load() }
        }
        startWatchdog()
        Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in self?.refresh() }
    }

    func refresh() {
        sections.forEach { $0.poll() }
        gauge.update()
    }

    func buildWindow() {
        window.title = "Local Models"
        window.titlebarAppearsTransparent = true
        window.isMovableByWindowBackground = true
        let bg = NSVisualEffectView()
        bg.material = .underWindowBackground
        bg.blendingMode = .behindWindow
        bg.state = .active
        window.contentView = bg

        let rule = NSBox()
        rule.boxType = .separator
        let stack = NSStackView(views: sections + [rule, gauge])
        stack.orientation = .vertical
        stack.spacing = 16
        stack.setCustomSpacing(20, after: sections.last!)
        stack.setCustomSpacing(0, after: rule)
        stack.edgeInsets = NSEdgeInsets(top: 40, left: 0, bottom: 0, right: 0)   // below the title bar
        stack.translatesAutoresizingMaskIntoConstraints = false
        bg.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: bg.leadingAnchor), stack.trailingAnchor.constraint(equalTo: bg.trailingAnchor),
            stack.topAnchor.constraint(equalTo: bg.topAnchor), stack.bottomAnchor.constraint(equalTo: bg.bottomAnchor),
            bg.widthAnchor.constraint(equalToConstant: 460),
            rule.widthAnchor.constraint(equalTo: stack.widthAnchor),
            gauge.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -40),
            gauge.heightAnchor.constraint(equalToConstant: 44),
        ] + sections.map { $0.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -40) })
    }

    // Keeps logs/app-owned in step with the models this app started, for the watchdog.
    func own(_ ctl: URL, _ name: String, _ on: Bool) {
        owned.removeAll { $0 == (ctl, name) }
        if on { owned.append((ctl, name)) }
        try? FileManager.default.createDirectory(at: ownedFile.deletingLastPathComponent(), withIntermediateDirectories: true)
        try? owned.map { "\($0.0.path)\t\($0.1)\n" }.joined().write(to: ownedFile, atomically: true, encoding: .utf8)
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

    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { true }
}
