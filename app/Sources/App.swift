import SwiftUI

@main
struct LocalModelsApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate

    var body: some Scene {
        Window("Local Models", id: "main") {
            ContentView(kinds: delegate.kinds, memory: delegate.memory)
        }
        .windowResizability(.contentSize)
    }
}

let ownedFile = root.appendingPathComponent("logs/app-owned")

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    let kinds = [Kind(key: "decision", title: "Decision", ctl: "decisionctl"), Kind(key: "llm", title: "LLM", ctl: "llmctl")]
    let memory = Memory()
    private var owned: [(ctl: String, name: String)] = []

    func applicationDidFinishLaunching(_ note: Notification) {
        // a list left by an earlier run whose watchdog never ran, e.g. across a reboot; this run started none of those
        try? FileManager.default.removeItem(at: ownedFile)
        for kind in kinds {
            kind.onOwn = { [weak self, ctl = kind.ctl.path] name, on in self?.own(ctl, name, on) }
        }
        startWatchdog()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { true }

    private func own(_ ctl: String, _ name: String, _ on: Bool) {
        owned.removeAll { $0 == (ctl, name) }
        if on { owned.append((ctl, name)) }
        try? FileManager.default.createDirectory(at: ownedFile.deletingLastPathComponent(), withIntermediateDirectories: true)
        try? owned.map { "\($0.ctl)\t\($0.name)\n" }.joined().write(to: ownedFile, atomically: true, encoding: .utf8)
    }

    // A child process outlives the app (macOS does not kill children with their parent), so it stops the models
    // this app started after a normal quit, a force quit, or a crash alike.
    private func startWatchdog() {
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
}
