import Combine
import SwiftUI

struct ContentView: View {
    let kinds: [Kind]
    let memory: Memory
    private let tick = Timer.publish(every: 2, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(spacing: 16) {
            ForEach(kinds) { SectionView(kind: $0, free: memory.free) }
            Divider()
            MemoryGauge(free: memory.free)
        }
        .padding(20)
        .frame(width: 460)
        .task {
            for kind in kinds { Task { await kind.load() } }
        }
        .onReceive(tick) { _ in
            for kind in kinds { Task { await kind.poll() } }
            memory.update()
        }
    }
}

struct SectionView: View {
    @Bindable var kind: Kind
    let free: Double
    @FocusState private var portFocused: Bool

    private var selectedModel: Model? { kind.models.first { $0.name == kind.selected } }
    private var external: Bool { kind.live?.state == "external" }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            header
            VStack(spacing: 0) {
                ForEach(kind.models) { ModelRow(model: $0, kind: kind, free: free) }
            }
            .padding(.vertical, 4)
            .background(RoundedRectangle(cornerRadius: 10).fill(.background.opacity(0.6)))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(.primary.opacity(0.09)))
            footer
        }
        .alert("Not enough free memory for \(kind.confirm?.name ?? "")",
               isPresented: Binding { kind.confirm != nil } set: { if !$0 { kind.confirm = nil } }, presenting: kind.confirm) { _ in
            Button("Start Anyway") { Task { await kind.start() } }
            Button("Cancel", role: .cancel) {}
        } message: { m in
            Text(String(format: "It needs about %.0f GB and %.1f GB is free. Other apps or models may be swapped out.", m.memoryGB, free))
        }
    }

    private var header: some View {
        let (state, color) = headline
        return HStack(spacing: 8) {
            Text(kind.title).font(.system(size: 15, weight: .semibold))
            Spacer()
            if kind.models.isEmpty && kind.failure == nil {
                ProgressView().controlSize(.small)
            } else {
                Circle().fill(color).frame(width: 8, height: 8)
            }
            Text(state).font(.system(size: 12, weight: .medium)).lineLimit(1).help(state)
            TextField("Port", text: $kind.portText)
                .textFieldStyle(.roundedBorder)
                .font(.system(size: 12).monospacedDigit())
                .multilineTextAlignment(.center)
                .frame(width: 58)
                .focused($portFocused)
                .disabled(kind.upName != nil || kind.models.isEmpty)
                .help("Port of every \(kind.title) model. Return saves it to \(kind.key).toml.")
                .onSubmit { Task { await kind.setPort(kind.portText) } }
                .onExitCommand { kind.portText = ":\(kind.port)"; portFocused = false }
            Button(kind.isUp ? "Stop" : "Start", action: toggle)
                .frame(width: 76)
                .buttonStyle(.borderedProminent)
                .tint(kind.isUp ? .secondary : .accentColor)
                // a server another checkout or tool started has no pid file here, so the ctl cannot stop it
                .disabled(kind.stopping != nil || kind.settingPort || kind.models.isEmpty || external)
                .help(external ? "Started outside this project; stop it where it was started" : "")
        }
    }

    private var headline: (String, Color) {
        if kind.stopping != nil { return ("Stopping…", .orange) }
        if kind.starting != nil || kind.live?.state == "starting" { return ("Starting…", .orange) }
        if let l = kind.live { return (l.state == "external" ? "Running, not started here" : "Running", .green) }
        if let t = kind.failure?.title { return (t, .red) }
        return (kind.models.isEmpty ? "Loading…" : "Stopped", Color.secondary.opacity(0.5))
    }

    private var footer: some View {
        let (line, code, copy, log, isError) = footLine
        return HStack(spacing: 4) {
            Text(line).foregroundStyle(isError ? .red : .secondary)
            if let code { Text(code).font(.system(size: 11.5, design: .monospaced)).foregroundStyle(isError ? .red : .secondary) }
            if let copy {
                Button {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(copy, forType: .string)
                    kind.copied = true
                    Task { try? await Task.sleep(for: .seconds(1.2)); kind.copied = false }
                } label: {
                    Image(systemName: kind.copied ? "checkmark" : "doc.on.doc")
                }
                .buttonStyle(.borderless)
                .help("Copy \(copy)")
            }
            if let log {
                Button("Show Log") { NSWorkspace.shared.open(log) }.buttonStyle(.link).padding(.leading, 6)
            }
            Spacer()
        }
        .font(.system(size: 11.5))
        .lineLimit(1)
        .truncationMode(.tail)
        .frame(height: 16)   // fixed, so the window keeps its size whatever the line says
        .padding(.horizontal, 12)
    }

    private var footLine: (String, String?, String?, URL?, Bool) {
        if kind.stopping != nil { return ("", nil, nil, nil, false) }
        if kind.starting != nil || kind.live?.state == "starting" { return ("Loading the model can take a minute.", nil, nil, nil, false) }
        if let l = kind.live { return ("", l.url, l.url, nil, false) }
        if let f = kind.failure {
            let log = f.log.map { root.appendingPathComponent("logs/\($0).log") }.flatMap { FileManager.default.fileExists(atPath: $0.path) ? $0 : nil }
            // the command runs from anywhere as copied; it reads better with the ctl's name than its full path
            return (f.detail, f.command?.replacingOccurrences(of: kind.ctl.path, with: kind.ctlName), f.command, log, true)
        }
        return (kind.info, nil, nil, nil, false)
    }

    private func toggle() {
        portFocused = false
        if kind.isUp { Task { await kind.stop() }; return }
        if let m = selectedModel, !m.missing, m.memoryGB > free { kind.confirm = m; return }
        Task { await kind.start() }
    }
}

struct ModelRow: View {
    let model: Model
    let kind: Kind
    let free: Double

    private enum Look { case idle, selected, running, changing, waiting }

    private var look: Look {
        guard let up = kind.upName else { return kind.selected == model.name ? .selected : .idle }
        if up != model.name { return .waiting }
        return kind.stopping != nil || kind.starting != nil || kind.live?.state == "starting" ? .changing : .running
    }

    var body: some View {
        let look = look
        let idle = look == .idle || look == .selected
        let short = idle && model.memoryGB > free
        Button { if idle { kind.selected = model.name } } label: { label(look, short: short) }
            .buttonStyle(.plain)
            .accessibilityAddTraits(look == .selected ? .isSelected : [])
    }

    private func label(_ look: Look, short: Bool) -> some View {
        HStack(spacing: 10) {
            Group {
                switch look {
                case .running: Circle().fill(.green).frame(width: 8, height: 8)
                case .changing: ProgressView().controlSize(.small).scaleEffect(0.7)
                case .selected: Image(systemName: "largecircle.fill.circle").foregroundStyle(Color.accentColor)
                case .idle, .waiting: Image(systemName: "circle").foregroundStyle(.tertiary)
                }
            }
            .frame(width: 16, height: 16)
            Text(model.name).font(.system(size: 13, weight: .medium)).foregroundStyle(look == .waiting ? .secondary : .primary)
            Spacer()
            if let note = model.note {
                Text(note).font(.system(size: 12)).foregroundStyle(model.missing && look != .waiting ? .orange : .secondary)
            }
            Text(String(format: "%.0f GB", model.memoryGB))
                .font(.system(size: 12).monospacedDigit())
                .foregroundStyle(short ? .orange : .secondary)
                .frame(width: 42, alignment: .trailing)
                .help(short ? String(format: "Needs about %.0f GB; %.1f GB is free", model.memoryGB, free) : "")
        }
        .lineLimit(1)
        .padding(.horizontal, 12)
        .frame(height: 40)
        .background(RoundedRectangle(cornerRadius: 7).fill(tint(look)).padding(.horizontal, 4).padding(.vertical, 2))
        .contentShape(Rectangle())
    }

    private func tint(_ look: Look) -> Color {
        switch look {
        case .selected: .accentColor.opacity(0.1)
        case .changing: .orange.opacity(0.12)
        case .running: .green.opacity(0.13)
        case .idle, .waiting: .clear
        }
    }
}
