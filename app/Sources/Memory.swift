import Darwin
import SwiftUI

let totalGB = Double(ProcessInfo.processInfo.physicalMemory) / 1_073_741_824

// counted like servers.free_gb, so the app and the ctls agree on what fits
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

// SwiftUI's @State needs a macro plugin that the Command Line Tools lack, so view state lives in @Observable objects
@MainActor @Observable
final class Memory {
    private(set) var free = freeGB()
    func update() { free = freeGB() }
}

struct MemoryGauge: View {
    let free: Double

    var body: some View {
        let used = min(max(1 - free / totalGB, 0), 1)
        let text = String(format: "%.1f of %.0f GB free", free, totalGB)
        HStack(spacing: 12) {
            Text("Memory").font(.system(size: 12, weight: .medium)).foregroundStyle(.secondary)
            GeometryReader { g in
                ZStack(alignment: .leading) {
                    Capsule().fill(.primary.opacity(0.1))
                    // red from 90%, about where macOS starts to swap
                    Capsule().fill(used > 0.9 ? Color.red : used > 0.75 ? .orange : .secondary)
                        .frame(width: max(g.size.height, g.size.width * used))
                }
            }
            .frame(height: 6)
            Text(text).font(.system(size: 12).monospacedDigit()).foregroundStyle(.secondary)
                .frame(width: 140, alignment: .trailing)
        }
        .frame(height: 24)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Memory")
        .accessibilityValue(text)
    }
}
