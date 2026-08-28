import AppKit
import SwiftUI

/// O painel inteiro. Não existe janela neste app: o que o dono precisa fechar,
/// ele fecha daqui — confirmar envio, trocar de modo, entrar, sair, desinstalar.
struct PanelView: View {
    @ObservedObject var store: Store
    @State private var mostrandoLogin = false
    @State private var contaExpandida: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            cabecalho
            Divider()

            if store.cliMissing {
                aviso(L.noCLI)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        if !store.pending.isEmpty { fila }
                        contas
                        if mostrandoLogin || store.accounts.isEmpty {
                            LoginView(store: store) { mostrandoLogin = false }
                        }
                        if let erro = store.error { aviso(erro) }
                    }
                    .padding(12)
                }
                .frame(maxHeight: 460)
            }

            Divider()
            rodape
        }
        .frame(width: 380)
        .id(store.langTick)
        .onAppear { store.refresh() }
    }

    // ------------------------------------------------------------ cabeçalho

    private var cabecalho: some View {
        HStack {
            Text("MyMailForAI").font(.system(size: 12, weight: .semibold))
            Spacer()
            if store.busy { ProgressView().controlSize(.small) }
            Button {
                store.refreshUnread()
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .buttonStyle(.plain)
            .help(L.refresh)
        }
        .padding(.horizontal, 12).padding(.vertical, 9)
    }

    // ----------------------------------------------------------------- fila

    private var fila: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(L.queue.uppercased())
                    .font(.system(size: 10, weight: .semibold)).foregroundStyle(.secondary)
                Spacer()
                Text("\(store.pending.count)")
                    .font(.system(size: 10, weight: .semibold))
                    .padding(.horizontal, 6).padding(.vertical, 1)
                    .background(Color.accentColor, in: Capsule())
                    .foregroundStyle(.white)
            }
            ForEach(store.pending) { item in
                VStack(alignment: .leading, spacing: 6) {
                    Text(item.summary)
                        .font(.system(size: 12, weight: .medium))
                        .fixedSize(horizontal: false, vertical: true)
                    if let detalhe = item.detail, !detalhe.isEmpty {
                        Text(detalhe)
                            .font(.system(size: 10)).foregroundStyle(.secondary)
                            .lineLimit(6)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    HStack(spacing: 6) {
                        Text(item.account)
                            .font(.system(size: 9)).foregroundStyle(.tertiary)
                        Spacer()
                        Button(L.reject) { store.reject(item.id) }
                            .controlSize(.small)
                        Button(item.action == "send" || item.action == "reply"
                               || item.action == "forward" ? L.confirmSend : L.confirm) {
                            store.approve(item.id)
                        }
                        .controlSize(.small)
                        .buttonStyle(.borderedProminent)
                    }
                }
                .padding(10)
                .background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
            }
        }
    }

    // ---------------------------------------------------------------- contas

    private var contas: some View {
        VStack(alignment: .leading, spacing: 10) {
            if !store.accounts.isEmpty {
                Text(L.t("CONTAS", "ACCOUNTS"))
                    .font(.system(size: 10, weight: .semibold)).foregroundStyle(.secondary)
            }
            ForEach(store.accounts) { conta in
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 6) {
                        Circle()
                            .fill(conta.mode == "read" ? Color.secondary
                                  : (conta.mode == "auto" ? Color.green : Color.orange))
                            .frame(width: 6, height: 6)
                        Text(conta.address).font(.system(size: 12, weight: .medium)).lineLimit(1)
                        Spacer()
                        Button {
                            contaExpandida = contaExpandida == conta.address ? nil : conta.address
                        } label: {
                            Image(systemName: contaExpandida == conta.address
                                  ? "chevron.up" : "chevron.down")
                                .font(.system(size: 9))
                        }
                        .buttonStyle(.plain)
                    }

                    HStack(spacing: 10) {
                        if let naoLidos = conta.unread {
                            Text("\(naoLidos) \(L.unread)")
                        } else {
                            Text("— \(L.unread)")
                        }
                        Text("\(conta.sentToday)/\(conta.dailyLimit) \(L.sentToday)")
                    }
                    .font(.system(size: 10)).foregroundStyle(.secondary)

                    Picker("", selection: Binding(
                        get: { conta.mode },
                        set: { store.setMode($0, account: conta.address) })) {
                        Text(L.modeAuto).tag("auto")
                        Text(L.modeAsk).tag("ask")
                        Text(L.modeRead).tag("read")
                    }
                    .pickerStyle(.segmented)
                    .labelsHidden()

                    Text(L.modeHelp(conta.mode))
                        .font(.system(size: 10)).foregroundStyle(.tertiary)

                    if contaExpandida == conta.address {
                        if conta.mode == "ask" {
                            Toggle(L.strict, isOn: Binding(
                                get: { conta.askCoversMailbox },
                                set: { store.setStrict($0, account: conta.address) }))
                                .toggleStyle(.checkbox)
                                .font(.system(size: 10))
                        }
                        HStack {
                            if !conta.isDefault {
                                Button(L.t("Usar como padrão", "Make default")) {
                                    store.setDefault(conta.address)
                                }
                                .controlSize(.small)
                            }
                            Spacer()
                            Button(L.logout) { confirmarLogout(conta.address) }
                                .controlSize(.small)
                        }
                    }
                }
                .padding(10)
                .background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
            }
        }
    }

    private func aviso(_ texto: String) -> some View {
        Text(texto)
            .font(.system(size: 11))
            .foregroundStyle(.red)
            .textSelection(.enabled)
            .fixedSize(horizontal: false, vertical: true)
            .padding(12)
    }

    // ---------------------------------------------------------------- rodapé

    private var rodape: some View {
        HStack(spacing: 12) {
            if !store.accounts.isEmpty && !mostrandoLogin {
                Button {
                    mostrandoLogin = true
                } label: {
                    Label(L.t("Outro e-mail", "Another email"), systemImage: "plus")
                }
                .buttonStyle(.plain).font(.system(size: 11))
            }
            if !store.claudeConnected && !store.accounts.isEmpty {
                Button(L.claudeConnect) { store.connectClaude() }
                    .buttonStyle(.plain).font(.system(size: 11))
            }
            Spacer()
            Menu {
                Picker(L.language, selection: Binding(
                    get: { L.lang }, set: { store.setLanguage($0) })) {
                    Text("Português").tag("pt")
                    Text("English").tag("en")
                }
                Divider()
                Button(L.uninstall) { confirmarDesinstalar() }
                Divider()
                Button(L.quit) { NSApp.terminate(nil) }
            } label: {
                Image(systemName: "ellipsis.circle")
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
    }

    // ------------------------------------------------------------ confirmações

    private func confirmarLogout(_ conta: String) {
        let alerta = NSAlert()
        alerta.messageText = L.logoutTitle
        alerta.informativeText = "\(conta)\n\n\(L.logoutBody)"
        alerta.addButton(withTitle: L.logout)
        alerta.addButton(withTitle: L.cancel)
        alerta.alertStyle = .warning
        NSApp.activate(ignoringOtherApps: true)
        if alerta.runModal() == .alertFirstButtonReturn { store.logout(conta) }
    }

    private func confirmarDesinstalar() {
        let alerta = NSAlert()
        alerta.messageText = L.uninstallTitle
        alerta.informativeText = L.uninstallBody
        alerta.addButton(withTitle: L.uninstall)
        alerta.addButton(withTitle: L.cancel)
        alerta.alertStyle = .critical
        NSApp.activate(ignoringOtherApps: true)
        if alerta.runModal() == .alertFirstButtonReturn { store.uninstall() }
    }
}
