// Everything the app knows about the models comes from kevctl and llmctl: `list --json`, `status --json`, `start`,
// `stop` and `port`. This file runs them and decodes what they print (src/local_models/servers.py writes the JSON).
import Foundation

// The project the app was built in; scripts/build-app.sh writes it into Info.plist.
let root = URL(fileURLWithPath: Bundle.main.infoDictionary?["ProjectRoot"] as? String ?? "")

// A ctl and the section of the window that drives it. key also names its registry: kev.toml, llm.toml.
struct Project {
    let key: String
    let title: String
    let subtitle: String
    let ctl: URL
}

let projects = [
    Project(key: "kev", title: "Kev", subtitle: "Decision models", ctl: root.appendingPathComponent(".venv/bin/kevctl")),
    Project(key: "llm", title: "LLM", subtitle: "Qwen, MiniCPM-V, Bonsai", ctl: root.appendingPathComponent(".venv/bin/llmctl")),
]

struct Model: Decodable {
    let name: String
    var port: Int
    let memory_gb: Double
    let isDefault: Bool
    let note: String?    // shown next to the name, e.g. the weights' quantization
    let missing: Bool    // weights not downloaded
    enum CodingKeys: String, CodingKey { case name, port, memory_gb, isDefault = "default", note, missing }
}

// state: running (answering, with a pid file in this project's logs/), external (answering, without one: started
// outside this project, so its ctl cannot stop it), starting (pid file, not answering yet), stopped
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

// Runs a ctl command to the end; returns its exit status, stdout and stderr. Call it off the main thread, except for
// commands that finish at once.
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
