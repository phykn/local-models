// Draws the LOCAL-MODELS 1024×1024 app icon to the path given as the first argument. Used by scripts/build-app.sh.
// It is the window in miniature: two model rows, one running (green light) and one stopped.
import AppKit

let size = 1024.0
let img = NSImage(size: NSSize(width: size, height: size))
img.lockFocus()
// macOS icon grid: an 824pt rounded square centred on the canvas, with a soft shadow below.
let tile = NSBezierPath(roundedRect: NSRect(x: 100, y: 100, width: 824, height: 824), xRadius: 185, yRadius: 185)
NSGraphicsContext.current?.saveGraphicsState()
let shadow = NSShadow()
shadow.shadowColor = NSColor.black.withAlphaComponent(0.3)
shadow.shadowBlurRadius = 24
shadow.shadowOffset = NSSize(width: 0, height: -10)
shadow.set()
NSColor.black.setFill()
tile.fill()
NSGraphicsContext.current?.restoreGraphicsState()
NSGradient(colors: [NSColor(red: 0.07, green: 0.08, blue: 0.11, alpha: 1),
                    NSColor(red: 0.13, green: 0.22, blue: 0.40, alpha: 1)])!.draw(in: tile, angle: -60)

func row(y: Double, light: NSColor, glow: Bool, name: Double) {
    let r = NSRect(x: 212, y: y, width: 600, height: 196)
    let pill = NSBezierPath(roundedRect: r, xRadius: 52, yRadius: 52)
    NSColor.white.withAlphaComponent(glow ? 0.16 : 0.08).setFill()
    pill.fill()
    NSColor.white.withAlphaComponent(glow ? 0.22 : 0.12).setStroke()
    pill.lineWidth = 4
    pill.stroke()
    let dot = NSRect(x: r.minX + 62, y: r.midY - 40, width: 80, height: 80)
    if glow {
        NSGraphicsContext.current?.saveGraphicsState()
        let halo = NSShadow()
        halo.shadowColor = light.withAlphaComponent(0.9)
        halo.shadowBlurRadius = 48
        halo.set()
        light.setFill()
        NSBezierPath(ovalIn: dot).fill()
        NSGraphicsContext.current?.restoreGraphicsState()
    }
    light.setFill()
    NSBezierPath(ovalIn: dot).fill()
    NSColor.white.withAlphaComponent(glow ? 0.92 : 0.45).setFill()
    NSBezierPath(roundedRect: NSRect(x: dot.maxX + 52, y: r.midY - 20, width: name, height: 40), xRadius: 20, yRadius: 20).fill()
}
row(y: 548, light: NSColor(red: 0.20, green: 0.84, blue: 0.42, alpha: 1), glow: true, name: 300)
row(y: 280, light: NSColor.white.withAlphaComponent(0.3), glow: false, name: 220)

img.unlockFocus()
let rep = NSBitmapImageRep(data: img.tiffRepresentation!)!
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
