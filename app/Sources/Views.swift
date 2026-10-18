// Small views shared by the sections. Colours are resolved when drawn, so they follow light and dark mode.
import AppKit

func label(_ s: String, size: CGFloat, weight: NSFont.Weight = .regular, color: NSColor = .labelColor) -> NSTextField {
    let l = NSTextField(labelWithString: s)
    l.font = .systemFont(ofSize: size, weight: weight)
    l.textColor = color
    l.lineBreakMode = .byTruncatingTail
    return l
}

extension NSColor {
    static let groupFill = NSColor(name: nil) { $0.isDark ? .white.withAlphaComponent(0.05) : .white.withAlphaComponent(0.7) }
    static let groupStroke = NSColor(name: nil) { $0.isDark ? .white.withAlphaComponent(0.09) : .black.withAlphaComponent(0.09) }
}

extension NSAppearance {
    var isDark: Bool { bestMatch(from: [.aqua, .darkAqua]) == .darkAqua }
}

// A rounded box around a list of rows, as in System Settings.
final class GroupBox: NSView {
    private let stack = NSStackView()

    init() {
        super.init(frame: .zero)
        stack.orientation = .vertical
        stack.spacing = 0
        stack.translatesAutoresizingMaskIntoConstraints = false
        addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: leadingAnchor), stack.trailingAnchor.constraint(equalTo: trailingAnchor),
            stack.topAnchor.constraint(equalTo: topAnchor, constant: 4), stack.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -4),
        ])
    }
    required init?(coder: NSCoder) { fatalError() }

    func setRows(_ rows: [NSView]) {
        stack.arrangedSubviews.forEach { $0.removeFromSuperview() }
        for row in rows {
            stack.addArrangedSubview(row)
            row.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        }
    }

    override func draw(_ r: NSRect) {
        let box = NSBezierPath(roundedRect: bounds.insetBy(dx: 0.5, dy: 0.5), xRadius: 10, yRadius: 10)
        NSColor.groupFill.setFill()
        box.fill()
        NSColor.groupStroke.setStroke()
        box.stroke()
    }
}

// A coloured dot for a state: green while a model answers, orange while it starts or stops, red after a failure.
final class StatusLight: NSView {
    var color = NSColor.tertiaryLabelColor { didSet { needsDisplay = true } }
    override var intrinsicContentSize: NSSize { NSSize(width: 8, height: 8) }
    override func draw(_ r: NSRect) {
        color.setFill()
        NSBezierPath(ovalIn: bounds).fill()
    }
}
