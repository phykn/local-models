// Draws the LOCAL-MODELS 1024×1024 app icon to the path given as the first argument. Used by scripts/build-app.sh.
import AppKit

let size = 1024.0
let img = NSImage(size: NSSize(width: size, height: size))
img.lockFocus()
// macOS icon grid: an 824pt rounded square centred on the canvas.
let rect = NSRect(x: 100, y: 100, width: 824, height: 824)
let shape = NSBezierPath(roundedRect: rect, xRadius: 185, yRadius: 185)
NSGraphicsContext.current?.saveGraphicsState()
let shadow = NSShadow()
shadow.shadowColor = NSColor.black.withAlphaComponent(0.3)
shadow.shadowBlurRadius = 24
shadow.shadowOffset = NSSize(width: 0, height: -10)
shadow.set()
NSColor.black.setFill()
shape.fill()
NSGraphicsContext.current?.restoreGraphicsState()
// the Kev app's charcoal blending into the LLM app's blue
NSGradient(colors: [NSColor(red: 0.08, green: 0.08, blue: 0.10, alpha: 1),
                    NSColor(red: 0.16, green: 0.30, blue: 0.55, alpha: 1)])!.draw(in: shape, angle: -60)
let cfg = NSImage.SymbolConfiguration(pointSize: 400, weight: .semibold).applying(.init(paletteColors: [.white]))
let glyph = NSImage(systemSymbolName: "cpu", accessibilityDescription: nil)!.withSymbolConfiguration(cfg)!
glyph.draw(in: NSRect(x: (size - glyph.size.width) / 2, y: (size - glyph.size.height) / 2,
                      width: glyph.size.width, height: glyph.size.height))
img.unlockFocus()
let rep = NSBitmapImageRep(data: img.tiffRepresentation!)!
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
