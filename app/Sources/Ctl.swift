import Foundation

// scripts/build-app.sh writes it into Info.plist
let root = URL(fileURLWithPath: Bundle.main.infoDictionary?["ProjectRoot"] as? String ?? "")

struct Project {
    let key: String
    let title: String
    let subtitle: String
    let ctl: URL
}

let projects = [
    Project(key: "kev", title: "Kev", subtitle: "Decision models", ctl: root.appendingPathComponent(".venv/bin/kevctl")),
    Project(key: "llm", title: "LLM", subtitle: "Qwen, MiniCPM-V, Gemma", ctl: root.appendingPathComponent(".venv/bin/llmctl")),
]

// decodes servers.list_row and servers.status_row
struct Model: Decodable {
    let name: String
    var port: Int
    let memory_gb: Double
    let isDefault: Bool
    let note: String?
    let missing: Bool
    enum CodingKeys: String, CodingKey { case name, port, memory_gb, isDefault = "default", note, missing }
}

struct Status: Decodable { let name: String; let state: String; let url: String }

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

// Blocks until the command exits: call it off the main thread, except for commands that finish at once.
func runCtl(_ ctl: URL, _ args: [String]) -> (Int32, String, String) {
    let (p, out, err) = ctlProcess(ctl, args)
    do { try p.run() } catch { return (-1, "", "\(error)") }
    let o = out.fileHandleForReading.readDataToEndOfFile(), e = err.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    return (p.terminationStatus, String(data: o, encoding: .utf8) ?? "", String(data: e, encoding: .utf8) ?? "")
}

// A ctl reports errors on its last line, in lower case as on a command line; the window starts them with a capital.
func lastLine(_ s: String) -> String {
    let line = s.split(separator: "\n").last.map(String.init) ?? ""
    return line.prefix(1).uppercased() + line.dropFirst()
}
