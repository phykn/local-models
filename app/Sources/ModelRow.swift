// One model in a section: a radio to pick it, or its state while it runs; its name and note; its port, which can be
// changed while nothing in the section runs; and the memory it needs, in orange when that is more than is free.
import AppKit

final class ModelRow: NSView, NSTextFieldDelegate {
    // waiting: another model of the section is running or busy, so this one cannot be picked
    enum Look: Equatable { case idle(selected: Bool), running, starting, stopping, waiting }

    private(set) var model: Model
    var onSelect: (() -> Void)?
    var onPort: ((Int) -> Void)?   // a new port typed into the port field
    private var look = Look.idle(selected: false)
    private var editing = false { didSet { needsDisplay = true } }

    private let radio = NSButton(radioButtonWithTitle: "", target: nil, action: nil)
    private let light = StatusLight()
    private let spinner = NSProgressIndicator()
    private let name: NSTextField
    private let note: NSTextField
    private let port = NSTextField()
    private let memory: NSTextField

    init(_ m: Model, registry: String) {
        model = m
        name = label(m.name, size: 13, weight: .medium)
        note = label(m.note ?? "", size: 12, color: .secondaryLabelColor)
        memory = label(String(format: "%.0f GB", m.memory_gb), size: 12, color: .secondaryLabelColor)
        super.init(frame: .zero)

        radio.target = self
        radio.action = #selector(pick)
        radio.setAccessibilityLabel(m.name)
        light.color = .systemGreen
        spinner.style = .spinning
        spinner.controlSize = .small
        spinner.isDisplayedWhenStopped = false
        let mark = NSView()   // the radio, the light and the spinner share one spot; one shows at a time
        for v in [radio, light, spinner] as [NSView] {
            v.translatesAutoresizingMaskIntoConstraints = false
            mark.addSubview(v)
            v.centerXAnchor.constraint(equalTo: mark.centerXAnchor).isActive = true
            v.centerYAnchor.constraint(equalTo: mark.centerYAnchor).isActive = true
        }

        note.isHidden = m.note == nil
        port.font = .monospacedDigitSystemFont(ofSize: 12, weight: .regular)
        port.isBordered = false
        port.drawsBackground = false
        port.focusRingType = .none
        port.alignment = .center
        port.delegate = self
        port.stringValue = ":\(m.port)"
        port.toolTip = "Port of \(m.name). Click to change it; Return saves it to \(registry)."
        port.setAccessibilityLabel("Port of \(m.name)")
        memory.font = .monospacedDigitSystemFont(ofSize: 12, weight: .regular)
        memory.alignment = .right

        let row = NSStackView(views: [mark, name, NSView(), note, port, memory])
        row.spacing = 10
        row.setCustomSpacing(12, after: note)
        row.setCustomSpacing(8, after: port)
        row.edgeInsets = NSEdgeInsets(top: 0, left: 12, bottom: 0, right: 14)
        row.translatesAutoresizingMaskIntoConstraints = false
        addSubview(row)
        NSLayoutConstraint.activate([
            row.leadingAnchor.constraint(equalTo: leadingAnchor), row.trailingAnchor.constraint(equalTo: trailingAnchor),
            row.topAnchor.constraint(equalTo: topAnchor), row.bottomAnchor.constraint(equalTo: bottomAnchor),
            heightAnchor.constraint(equalToConstant: 40),
            mark.widthAnchor.constraint(equalToConstant: 16), mark.heightAnchor.constraint(equalToConstant: 16),
            light.widthAnchor.constraint(equalToConstant: 8), light.heightAnchor.constraint(equalToConstant: 8),
            port.widthAnchor.constraint(equalToConstant: 52),
            memory.widthAnchor.constraint(equalToConstant: 42),
        ])
        name.setContentCompressionResistancePriority(.defaultHigh, for: .horizontal)
    }
    required init?(coder: NSCoder) { fatalError() }

    func update(_ look: Look, free: Double) {
        self.look = look
        let idle: Bool
        if case .idle(let selected) = look { idle = true; radio.state = selected ? .on : .off } else { idle = false; radio.state = .off }
        radio.isHidden = !(idle || look == .waiting)
        radio.isEnabled = idle
        light.isHidden = look != .running
        if look == .starting || look == .stopping { spinner.startAnimation(nil) } else { spinner.stopAnimation(nil) }

        let dim = look == .waiting
        name.textColor = dim ? .secondaryLabelColor : .labelColor
        note.textColor = !dim && model.missing ? .systemOrange : .secondaryLabelColor
        port.isEditable = idle
        port.isSelectable = idle
        port.textColor = idle ? .labelColor : .secondaryLabelColor
        let short = idle && model.memory_gb > free
        memory.textColor = short ? .systemOrange : .secondaryLabelColor
        memory.toolTip = short ? String(format: "Needs about %.0f GB; %.1f GB is free", model.memory_gb, free) : nil
        needsDisplay = true
    }

    func setPort(_ p: Int) {
        model.port = p
        port.stringValue = ":\(p)"
    }

    @objc private func pick() { onSelect?() }

    override func mouseDown(with e: NSEvent) {
        if case .idle = look { onSelect?() }
    }

    override func draw(_ r: NSRect) {
        // the picked model, or the one running, sits on a soft highlight
        let tint: NSColor? = switch look {
            case .idle(selected: true): .controlAccentColor.withAlphaComponent(0.1)
            case .starting, .stopping: .systemOrange.withAlphaComponent(0.12)
            case .running: .systemGreen.withAlphaComponent(0.13)
            default: nil
        }
        if let tint {
            tint.setFill()
            NSBezierPath(roundedRect: bounds.insetBy(dx: 4, dy: 2), xRadius: 7, yRadius: 7).fill()
        }
        // the picked model's port sits in a small field, since it can be changed while nothing runs
        guard look == .idle(selected: true) || editing else { return }
        let field = NSBezierPath(roundedRect: port.convert(port.bounds, to: self).insetBy(dx: 0.5, dy: -2.5), xRadius: 5, yRadius: 5)
        NSColor.textBackgroundColor.setFill()
        field.fill()
        (editing ? NSColor.controlAccentColor : NSColor.labelColor.withAlphaComponent(0.18)).setStroke()
        field.lineWidth = editing ? 1.5 : 1
        field.stroke()
    }

    func controlTextDidBeginEditing(_ note: Notification) {
        editing = true
        onSelect?()
    }

    // Return or leaving the field saves; anything that is not a number goes back to the current port.
    func controlTextDidEndEditing(_ note: Notification) {
        editing = false
        var text = port.stringValue.trimmingCharacters(in: .whitespaces)
        if text.hasPrefix(":") { text.removeFirst() }
        port.stringValue = ":\(model.port)"
        if let p = Int(text), p != model.port { onPort?(p) }
    }

    // Escape leaves the port as it was.
    func control(_ c: NSControl, textView: NSTextView, doCommandBy sel: Selector) -> Bool {
        guard sel == #selector(NSResponder.cancelOperation(_:)) else { return false }
        port.abortEditing()
        port.stringValue = ":\(model.port)"
        editing = false
        window?.makeFirstResponder(nil)
        return true
    }
}
