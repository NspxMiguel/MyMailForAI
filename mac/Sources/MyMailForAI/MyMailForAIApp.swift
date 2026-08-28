import SwiftUI

/// Não existe janela aqui, e isso é o pedido, não um atalho: o MailForAI tem um
/// app com abas, e o que ele quis desta vez foi só o item da barra de menus.
@main
struct MyMailForAIApp: App {
    @StateObject private var store = Store.shared

    var body: some Scene {
        MenuBarExtra {
            PanelView(store: store)
                .onAppear { store.start() }
        } label: {
            // Ícone e número precisam sair como UM Text interpolado: dois
            // elementos soltos e o SwiftUI desenha só o primeiro, deixando o
            // contador invisível.
            if store.pendingCount > 0 {
                Text("\(Image(systemName: "envelope.badge.fill")) \(store.pendingCount)")
            } else {
                Text("\(Image(systemName: "envelope"))")
            }
        }
        .menuBarExtraStyle(.window)
    }
}
