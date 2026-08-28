import AppKit
import SwiftUI

/// O "loga uma vez e cabum": escreve o e-mail, o app descobre o provedor pelo
/// domínio (ou pelo MX, em domínio próprio), abre a página onde a senha de
/// aplicativo é criada, e valida IMAP e SMTP antes de guardar qualquer coisa.
struct LoginView: View {
    @ObservedObject var store: Store
    var onDone: () -> Void

    @State private var address = ""
    @State private var password = ""
    @State private var username = ""
    @State private var info: ProviderInfo?
    @State private var detecting = false
    @State private var erro: String?
    @FocusState private var focoSenha: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(L.addAccount).font(.system(size: 12, weight: .semibold))

            TextField(L.emailPlaceholder, text: $address)
                .textFieldStyle(.roundedBorder)
                .onSubmit { detectar() }
                .onChange(of: address) { _ in info = nil; erro = nil }

            if detecting {
                Label(L.checking, systemImage: "ellipsis")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            }

            if let info {
                HStack(spacing: 6) {
                    Image(systemName: "checkmark.seal")
                    Text(info.label).font(.system(size: 11, weight: .medium))
                }
                .foregroundStyle(.secondary)

                if !info.passwordUrl.isEmpty {
                    Button {
                        if let url = URL(string: info.passwordUrl) { NSWorkspace.shared.open(url) }
                        focoSenha = true
                    } label: {
                        Label(L.openPasswordPage, systemImage: "arrow.up.forward.square")
                    }
                    .buttonStyle(.link)
                    .font(.system(size: 11))
                    Text(info.passwordHint)
                        .font(.system(size: 10)).foregroundStyle(.tertiary)
                        .fixedSize(horizontal: false, vertical: true)
                }

                SecureField(L.appPassword, text: $password)
                    .textFieldStyle(.roundedBorder)
                    .focused($focoSenha)
                    .onSubmit { entrar() }

                // O iCloud autentica pelo Apple ID, não pelo alias do domínio
                // próprio: sem este campo, quem usa domínio no iCloud não entra.
                if info.provider == "icloud" && !address.lowercased().hasSuffix("@icloud.com") {
                    TextField(info.usernameHint, text: $username)
                        .textFieldStyle(.roundedBorder)
                        .font(.system(size: 11))
                }
            }

            if let erro {
                Text(erro)
                    .font(.system(size: 10)).foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)
            }

            HStack {
                Button(L.cancel) { onDone() }.buttonStyle(.plain).font(.system(size: 11))
                Spacer()
                if info == nil {
                    Button(L.t("Continuar", "Continue")) { detectar() }
                        .disabled(!address.contains("@") || detecting)
                } else {
                    Button(L.connect) { entrar() }
                        .keyboardShortcut(.defaultAction)
                        .disabled(password.isEmpty || store.busy)
                }
            }
        }
        .padding(12)
        .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
    }

    private func detectar() {
        guard address.contains("@") else { return }
        detecting = true; erro = nil
        Task {
            let achado = await store.detect(address.trimmingCharacters(in: .whitespaces))
            detecting = false
            if let achado {
                info = achado
                focoSenha = true
            } else {
                erro = L.t("não reconheci esse provedor — conecte pelo terminal com --imap-host",
                           "provider not recognised — connect from the terminal with --imap-host")
            }
        }
    }

    private func entrar() {
        guard !password.isEmpty else { return }
        Task {
            let falha = await store.login(address: address.trimmingCharacters(in: .whitespaces),
                                          password: password, username: username)
            if let falha {
                erro = falha
            } else {
                password = ""
                onDone()
            }
        }
    }
}
