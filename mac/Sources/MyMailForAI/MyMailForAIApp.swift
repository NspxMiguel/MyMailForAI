import AppKit
import SwiftUI

/// Não existe janela neste app, e isso é o pedido — não um atalho. O MailForAI
/// tem app com abas; aqui o que ele quis foi só o item da barra de menus.
///
/// O item é um `NSStatusItem` na mão, e não `MenuBarExtra`, por um motivo que
/// custou caro no MacTray: numa barra lotada o macOS põe o item novo na ponta
/// esquerda, que o notch cobre, e o app nasce invisível justo para quem tem a
/// barra cheia. A posição preferida precisa ser semeada antes de criar o item,
/// e o `MenuBarExtra` não deixa escolher o `autosaveName`.
final class AppDelegate: NSObject, NSApplicationDelegate, NSPopoverDelegate {
    private var item: NSStatusItem!
    private var popover: NSPopover!
    private var observador: NSObjectProtocol?
    private var monitorDeFora: Any?

    private let autosave = "MyMailForAI"

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
        popover.contentSize = NSSize(width: 380, height: 340)
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

        // Primeira execução: abre o painel sozinho. Um app que não mostra nada
        // ao instalar passa por quebrado, e o ícone da barra é discreto demais.
        if !UserDefaults.standard.bool(forKey: "jaAbriuUmaVez") {
            UserDefaults.standard.set(true, forKey: "jaAbriuUmaVez")
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { [weak self] in self?.abrir() }
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
