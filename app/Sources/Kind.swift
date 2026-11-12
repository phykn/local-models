import Foundation
import Observation

// title is nil when the header should keep the server's state, e.g. after a refused port or a missing download
struct Failure {
    var title: String?
    var detail: String
    var command: String? = nil
    var log: String? = nil
}

// One kind of model (decision or LLM): its models as its ctl lists them, which one is up, and what the window shows.
@MainActor @Observable
final class Kind: Identifiable {
    let key: String
    let title: String
    let ctl: URL
    var onOwn: (String, Bool) -> Void = { _, _ in }

    private(set) var models: [Model] = []
    private(set) var port = 0
    private(set) var statuses: [String: Status] = [:]
    private(set) var starting: String?
    private(set) var stopping: String?
    private(set) var settingPort = false
    private(set) var failure: Failure?
    private(set) var info = ""
    // what the section shows while editing the port, asking about memory, or confirming a copy
    var portText = ""
    var confirm: Model?
    var copied = false
    var selected: String? { didSet { UserDefaults.standard.set(selected, forKey: "model.\(key)") } }
    private var starter: Process?
    private var watched: String?   // a model this app started, to notice when it goes away
    private var polling = false

    nonisolated var id: String { key }
    var ctlName: String { ctl.lastPathComponent }
    var live: Status? { models.compactMap { statuses[$0.name] }.first { $0.state != "stopped" } }
    var upName: String? { stopping ?? starting ?? live?.name }
    var isUp: Bool { live != nil || starting != nil }

    init(key: String, title: String, ctl: String) {
        self.key = key
        self.title = title
        self.ctl = root.appendingPathComponent(".venv/bin/\(ctl)")
    }

    func load() async {
        let r = await runCtl(ctl, ["list", "--json"])
        let ms = r.code == 0 ? try? JSONDecoder().decode([Model].self, from: Data(r.out.utf8)) : nil
        guard let ms, let first = ms.first else {
            let why = r.code != 0 ? r.message : ms == nil ? "\(ctlName) list --json printed something else." : "It lists no models."
            failure = Failure(title: "Can't read \(key).toml", detail: why)
            return
        }
        models = ms
        port = first.port
        portText = ":\(port)"
        let last = UserDefaults.standard.string(forKey: "model.\(key)")
        selected = ms.first { $0.name == last }?.name ?? ms.first { $0.isDefault }?.name ?? first.name
        await poll()
    }

    // follows the servers themselves, so models started or stopped from the command line show up too
    func poll() async {
        guard !polling, !models.isEmpty else { return }
        polling = true
        defer { polling = false }
        let r = await runCtl(ctl, ["status", "--json"])
        guard r.code == 0, let list = try? JSONDecoder().decode([Status].self, from: Data(r.out.utf8)) else { return }
        statuses = Dictionary(uniqueKeysWithValues: list.map { ($0.name, $0) })
        if let w = watched, statuses[w]?.state == "stopped", starting == nil, stopping == nil {
            watched = nil
            onOwn(w, false)
            failure = Failure(title: "Stopped unexpectedly", detail: "\(w) quit on its own; its log may say why.", log: w)
        }
        if let up = upName { selected = up }
    }

    func start() async {
        guard let m = models.first(where: { $0.name == selected }) else { return }
        failure = nil
        info = ""
        if m.missing {
            failure = Failure(detail: "Download it first:", command: "\(ctl.path) pull \(m.name)")
            return
        }
        let p = makeCtl(ctl, ["start", m.name])
        starter = p
        starting = m.name
        watched = m.name
        onOwn(m.name, true)
        let r = await run(p)
        guard starter === p else { return }   // Stop was pressed meanwhile
        starter = nil
        starting = nil
        if r.code != 0 {
            watched = nil
            onOwn(m.name, false)
            failure = Failure(title: "Failed to start", detail: r.message, log: m.name)
        }
        await poll()
    }

    func stop() async {
        guard let name = starting ?? live?.name else { return }
        if let s = starter, s.isRunning { s.terminate() }   // the server runs in its own session; stop handles it
        starter = nil
        starting = nil
        stopping = name
        watched = nil
        failure = nil
        info = ""
        let r = await runCtl(ctl, ["stop", name])
        stopping = nil
        onOwn(name, false)
        if r.code != 0 { failure = Failure(title: "Failed to stop", detail: r.message) }
        statuses[name] = nil
        await poll()
    }

    // The ctl writes the port into its .toml, so the ctl, its MCP server and this app all use the same one.
    // Start stays disabled until it is written, so a Start pressed right after never uses the old port.
    func setPort(_ text: String) async {
        let digits = text.trimmingCharacters(in: .whitespaces).trimmingPrefix(":")
        guard let p = Int(digits), p != port else { portText = ":\(port)"; return }
        failure = nil
        info = ""
        settingPort = true
        let r = await runCtl(ctl, ["port", String(p)])
        settingPort = false
        if r.code != 0 {
            failure = Failure(detail: r.message)
        } else {
            port = p
            info = "\(title) models now use port \(p)."
        }
        portText = ":\(port)"
    }
}
