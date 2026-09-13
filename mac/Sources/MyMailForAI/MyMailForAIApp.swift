import AppKit
import SwiftUI

/// A menu bar item plus a regular window.
///
/// The item is a hand-made `NSStatusItem`, not `MenuBarExtra`: on a full menu
/// bar macOS puts a new item at the far left, under the notch, and the app is
/// born invisible to exactly the people with a crowded bar. The preferred
/// position has to be seeded before the item exists, and `MenuBarExtra` does not
/// let you pick the `autosaveName`.
///
/// The window exists because even that is not always enough: with a bar full
/// enough, no position is visible. Opening the app from Launchpad, Spotlight or
/// the Dock shows the same panel in a window, with a Dock icon while it is open.
final class AppDelegate: NSObject, NSApplicationDelegate, NSPopoverDelegate, NSWindowDelegate {
    private var item: NSStatusItem!
    private var popover: NSPopover!
    private var observador: NSObjectProtocol?
    private var monitorDeFora: Any?

    private let autosave = "MyMailForAI"
    private var window: NSWindow?
    private var launchedAsLoginItem = false

    func applicationWillFinishLaunching(_ notification: Notification) {
        // Only the launch event carries this; by didFinishLaunching it is gone.
        if let event = NSAppleEventManager.shared().currentAppleEvent,
            event.eventID == kAEOpenApplication,
            event.paramDescriptor(forKeyword: keyAEPropData)?.enumCodeValue == keyAELaunchedAsLogInItem
        {
            launchedAsLoginItem = true
        }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        semearPosicao()

        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.autosaveName = autosave
        item.button?.target = self
        item.button?.action = #selector(alternar(_:))
        item.button?.toolTip = "MyMailForAI"

        popover = NSPopover()
        popover.behavior = .transient
        // Fixa antes de aparecer. Sem isto o popover nasce do tamanho do painel
        // vazio, cresce quando os dados chegam, e o AppKit não reposiciona o que
        // já está na tela: perto do relógio, metade dele fica fora do monitor.
        popover.contentSize = NSSize(width: 380, height: 540)
        popover.delegate = self
        popover.contentViewController = NSHostingController(
            rootView: PanelView(store: Store.shared))

        Task { @MainActor in
            Store.shared.start()
            desenhar()
        }
        // O contador na barra segue a fila: é o único sinal que ele vê sem clicar.
        observador = NotificationCenter.default.addObserver(
            forName: Store.filaMudou, object: nil, queue: .main) { [weak self] _ in
                Task { @MainActor in self?.desenhar() }
            }

        // Opened by hand (Launchpad, Spotlight, Finder, Dock): show the window, so
        // the app is visible whatever the menu bar looks like. Started at login:
        // stay in the menu bar only.
        if !launchedAsLoginItem {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [weak self] in
                Task { @MainActor in self?.showWindow() }
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in self?.rescueHiddenItem() }
    }

    /// Opening the app again while it runs (Dock, Launchpad, Spotlight) lands here.
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        Task { @MainActor in showWindow() }
        return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    @MainActor
    private func showWindow() {
        if popover.isShown { popover.performClose(nil) }
        if window == nil {
            let window = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 440, height: 680),
                styleMask: [.titled, .closable, .miniaturizable, .resizable],
                backing: .buffered,
                defer: false)
            window.title = "MyMailForAI"
            window.contentViewController = NSHostingController(rootView: PanelView(store: Store.shared))
            window.contentMinSize = NSSize(width: 380, height: 540)
            window.isReleasedWhenClosed = false
            window.setContentSize(NSSize(width: 440, height: 680))
            window.center()
            window.setFrameAutosaveName("MyMailForAIWindow")
            window.delegate = self
            self.window = window
        }
        Task { @MainActor in Store.shared.refresh() }
        // A Dock icon while the window is open: Cmd-Tab and the Dock find it.
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }

    func windowWillClose(_ notification: Notification) {
        guard (notification.object as? NSWindow) === window else { return }
        // Back to a menu bar app. Deferred so AppKit finishes closing first.
        DispatchQueue.main.async { NSApp.setActivationPolicy(.accessory) }
    }

    /// A position saved earlier (a drag, or an older build) can still leave the
    /// item under the notch. When the item's button is not inside the part of
    /// the menu bar right of the notch, seed the position next to the clock
    /// again and recreate the item. Removing an item deletes its saved position
    /// after the removal, so the key is written after a delay, not right away.
    private func rescueHiddenItem() {
        guard let buttonWindow = item.button?.window, let screen = buttonWindow.screen ?? NSScreen.main else {
            return
        }
        let frame = buttonWindow.frame
        let visibleMinX = screen.auxiliaryTopRightArea.map { screen.frame.minX + $0.minX } ?? screen.frame.minX
        let onScreen = frame.minX >= visibleMinX && frame.maxX <= screen.frame.maxX && frame.width > 0
        guard !onScreen, !UserDefaults.standard.bool(forKey: "rescuedHiddenItem") else { return }
        UserDefaults.standard.set(true, forKey: "rescuedHiddenItem")

        NSStatusBar.system.removeStatusItem(item)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
            guard let self else { return }
            UserDefaults.standard.set(4.0, forKey: "NSStatusItem Preferred Position \(self.autosave)")
            self.item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
            self.item.autosaveName = self.autosave
            self.item.button?.target = self
            self.item.button?.action = #selector(self.alternar(_:))
            UserDefaults.standard.set(4.0, forKey: "NSStatusItem Preferred Position \(self.autosave)")
            Task { @MainActor in self.desenhar() }
        }
    }

    /// A chave é a mesma que o sistema escreve quando se arrasta o ícone com ⌘.
    /// O valor é a distância até a borda direita — perto do relógio, portanto
    /// dentro do que sobra visível numa barra cheia. Só na primeira vez: depois
    /// quem manda é onde o dono arrastou.
    private func semearPosicao() {
        let chave = "NSStatusItem Preferred Position \(autosave)"
        guard UserDefaults.standard.object(forKey: chave) == nil else { return }
        UserDefaults.standard.set(4.0, forKey: chave)
    }

    @MainActor
    private func desenhar() {
        guard let botao = item.button else { return }
        let fila = Store.shared.pendingCount
        let nome = fila > 0 ? "envelope.badge.fill" : "envelope"
        let imagem = NSImage(systemSymbolName: nome, accessibilityDescription: "MyMailForAI")
        imagem?.isTemplate = true
        botao.image = imagem
        botao.imagePosition = fila > 0 ? .imageLeading : .imageOnly
        botao.title = fila > 0 ? " \(fila)" : ""
        botao.toolTip = fila > 0
            ? L.t("\(fila) esperando você", "\(fila) waiting for you")
            : "MyMailForAI"
    }

    @objc private func alternar(_ sender: Any?) {
        popover.isShown ? popover.performClose(sender) : abrir()
    }

    private func abrir() {
        guard let botao = item.button else { return }
        Task { @MainActor in Store.shared.refresh() }
        // Sem ativar, os campos de texto do painel não recebem teclado — e o
        // login inteiro acontece dentro dele.
        NSApp.activate(ignoringOtherApps: true)
        popover.show(relativeTo: botao.bounds, of: botao, preferredEdge: .minY)
        popover.contentViewController?.view.window?.makeKey()
    }

    func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool { true }
}

@main
enum Principal {
    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        // LSUIElement já está no Info.plist; `.accessory` garante o mesmo quando
        // o app roda do .build, fora do bundle, durante o desenvolvimento.
        app.setActivationPolicy(.accessory)
        app.run()
        _ = delegate
    }
}
