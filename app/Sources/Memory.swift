import AppKit

let totalGB = Double(ProcessInfo.processInfo.physicalMemory) / 1_073_741_824

// Memory macOS can hand out without swapping, counted like servers.free_gb in the ctls.
func freeGB() -> Double {
    var stats = vm_statistics64()
    var count = mach_msg_type_number_t(MemoryLayout<vm_statistics64>.size / MemoryLayout<integer_t>.size)
    let kr = withUnsafeMutablePointer(to: &stats) {
        $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) { host_statistics64(mach_host_self(), HOST_VM_INFO64, $0, &count) }
    }
    guard kr == KERN_SUCCESS else { return 0 }
    let pages = UInt64(stats.free_count) + UInt64(stats.inactive_count) + UInt64(stats.speculative_count) + UInt64(stats.purgeable_count)
    return Double(pages) * Double(vm_kernel_page_size) / 1_073_741_824
}

// The window's footer: how much of the Mac's unified memory is in use, which is what limits the models that can run.
final class MemoryGauge: NSView {
    private let bar = Bar()
    private let value = label("", size: 12, color: .secondaryLabelColor)

    init() {
        super.init(frame: .zero)
        let title = label("Memory", size: 12, weight: .medium, color: .secondaryLabelColor)
        value.font = .monospacedDigitSystemFont(ofSize: 12, weight: .regular)
        value.alignment = .right
        let row = NSStackView(views: [title, bar, value])
        row.spacing = 12
        row.translatesAutoresizingMaskIntoConstraints = false
        addSubview(row)
        NSLayoutConstraint.activate([
            row.leadingAnchor.constraint(equalTo: leadingAnchor), row.trailingAnchor.constraint(equalTo: trailingAnchor),
            row.centerYAnchor.constraint(equalTo: centerYAnchor),
            bar.heightAnchor.constraint(equalToConstant: 6),
            value.widthAnchor.constraint(equalToConstant: 140),
        ])
        setAccessibilityElement(true)
        setAccessibilityRole(.levelIndicator)
        setAccessibilityLabel("Memory")
        update()
    }
    required init?(coder: NSCoder) { fatalError() }

    func update() {
        let free = freeGB()
        bar.used = 1 - free / totalGB
        value.stringValue = String(format: "%.1f of %.0f GB free", free, totalGB)
        setAccessibilityValue(value.stringValue)
    }

    // A rounded track filled to the share in use: grey, then orange past 75% and red past 90%, when macOS starts to swap.
    private final class Bar: NSView {
        var used = 0.0 { didSet { needsDisplay = true } }

        override func draw(_ r: NSRect) {
            let radius = bounds.height / 2
            NSColor.labelColor.withAlphaComponent(0.1).setFill()
            NSBezierPath(roundedRect: bounds, xRadius: radius, yRadius: radius).fill()
            let share = min(max(used, 0), 1)
            (share > 0.9 ? NSColor.systemRed : share > 0.75 ? NSColor.systemOrange : NSColor.secondaryLabelColor).setFill()
            let fill = NSRect(x: 0, y: 0, width: max(bounds.height, bounds.width * share), height: bounds.height)
            NSBezierPath(roundedRect: fill, xRadius: radius, yRadius: radius).fill()
        }
    }
}
