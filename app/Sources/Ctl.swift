import Foundation

// scripts/build-app.sh writes it into Info.plist
let root = URL(fileURLWithPath: Bundle.main.infoDictionary?["ProjectRoot"] as? String ?? "")

// the rows of `list --json` and `status --json` (src/local_models/ctl.py)
struct Model: Decodable, Identifiable {
    let name: String
    let port: Int
    let memoryGB: Double
    let isDefault: Bool
    let note: String?
    let missing: Bool
    var id: String { name }
    enum CodingKeys: String, CodingKey { case name, port, memoryGB = "memory_gb", isDefault = "default", note, missing }
}

struct Status: Decodable {
    let name: String
    let state: String
    let url: String
}

struct CtlResult {
    let code: Int32
    let out: String
    let err: String

    // a ctl reports errors on its last line, in lower case as on a command line; the window starts them with a capital
    var message: String {
        let line = (err.isEmpty ? out : err).split(separator: "\n").last.map(String.init) ?? ""
        return line.prefix(1).uppercased() + line.dropFirst()
    }
}

func makeCtl(_ ctl: URL, _ args: [String]) -> Process {
    let p = Process()
    p.executableURL = ctl
    p.arguments = args
    p.currentDirectoryURL = root
    p.standardOutput = Pipe()
    p.standardError = Pipe()
    return p
}

// waits off the main thread; the pipes are read before waiting, so a full pipe cannot stall the ctl
func run(_ p: Process) async -> CtlResult {
    await withCheckedContinuation { done in
        DispatchQueue.global().async {
            do { try p.run() } catch { return done.resume(returning: CtlResult(code: -1, out: "", err: "\(error)")) }
            let out = (p.standardOutput as! Pipe).fileHandleForReading.readDataToEndOfFile()
            let err = (p.standardError as! Pipe).fileHandleForReading.readDataToEndOfFile()
            p.waitUntilExit()
            done.resume(returning: CtlResult(code: p.terminationStatus, out: String(decoding: out, as: UTF8.self),
                                             err: String(decoding: err, as: UTF8.self)))
        }
    }
}

func runCtl(_ ctl: URL, _ args: [String]) async -> CtlResult { await run(makeCtl(ctl, args)) }
