// LOCAL-MODELS.app: one window to start and stop the Kev decision models and the LLMs. Each section runs one model at
// a time and the sections are independent, so either or both can be up. Quitting the app stops the models it started,
// and only those. Built by scripts/build-app.sh. The app knows nothing model-specific: see Ctl.swift.
import AppKit

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)

let menu = NSMenu()
func submenu(_ title: String, _ items: [(String, Selector, String)]) {
    let item = NSMenuItem(), sub = NSMenu(title: title)
    for (name, action, key) in items { sub.addItem(withTitle: name, action: action, keyEquivalent: key) }
    item.submenu = sub
    menu.addItem(item)
}
submenu("Local Models", [
    ("Hide Local Models", #selector(NSApplication.hide(_:)), "h"),
    ("Quit Local Models", #selector(NSApplication.terminate(_:)), "q"),
])
submenu("Edit", [   // so ⌘C, ⌘V and ⌘A work in the port fields
    ("Cut", #selector(NSText.cut(_:)), "x"),
    ("Copy", #selector(NSText.copy(_:)), "c"),
    ("Paste", #selector(NSText.paste(_:)), "v"),
    ("Select All", #selector(NSText.selectAll(_:)), "a"),
])
submenu("Window", [
    ("Minimize", #selector(NSWindow.performMiniaturize(_:)), "m"),
    ("Close", #selector(NSWindow.performClose(_:)), "w"),
])
app.mainMenu = menu
app.run()
