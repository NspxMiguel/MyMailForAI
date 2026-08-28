import Foundation

/// Português e inglês. O idioma do sistema decide o padrão, `MYMAILFORAI_LANG`
/// força, e a escolha salva pelo CLI (`mymailforai lang`) vence os dois.
enum L {
    static var lang: String = {
        if let forcado = ProcessInfo.processInfo.environment["MYMAILFORAI_LANG"],
           ["pt", "en"].contains(String(forcado.prefix(2)).lowercased()) {
            return String(forcado.prefix(2)).lowercased()
        }
        let sistema = Locale.preferredLanguages.first ?? "en"
        return sistema.hasPrefix("pt") ? "pt" : "en"
    }()

    static func t(_ pt: String, _ en: String) -> String { lang == "pt" ? pt : en }

    // painel
    static var noAccounts: String { t("Nenhuma conta conectada.", "No account connected.") }
    static var addAccount: String { t("Conectar um e-mail", "Connect an email") }
    static var emailPlaceholder: String { t("voce@gmail.com", "you@gmail.com") }
    static var appPassword: String { t("Senha de aplicativo", "App password") }
    static var openPasswordPage: String { t("Criar a senha", "Create the password") }
    static var connect: String { t("Conectar", "Connect") }
    static var cancel: String { t("Cancelar", "Cancel") }
    static var checking: String { t("Conferindo com o servidor…", "Checking with the server…") }
    static var queue: String { t("Esperando você", "Waiting for you") }
    static var queueEmpty: String { t("Nada esperando confirmação.", "Nothing waiting for confirmation.") }
    static var confirmSend: String { t("Confirmar envio", "Confirm send") }
    static var confirm: String { t("Confirmar", "Confirm") }
    static var reject: String { t("Recusar", "Reject") }
    static var logout: String { t("Sair", "Log out") }
    static var uninstall: String { t("Desinstalar", "Uninstall") }
    static var quit: String { t("Encerrar", "Quit") }
    static var unread: String { t("não lidos", "unread") }
    static var sentToday: String { t("enviados 24h", "sent 24h") }
    static var modeAuto: String { t("Automático", "Automatic") }
    static var modeAsk: String { t("Pedir permissão", "Ask permission") }
    static var modeRead: String { t("Somente leitura", "Read-only") }
    static var modeAutoHelp: String { t("O agente envia sem perguntar.", "The agent sends without asking.") }
    static var modeAskHelp: String { t("Todo envio espera o seu botão.", "Every send waits for your button.") }
    static var modeReadHelp: String { t("O agente lê, mas não escreve.", "The agent reads, but does not write.") }
    static var strict: String { t("Pedir também para mover, arquivar e lixeira",
                                  "Also ask for move, archive and trash") }
    static var uninstallTitle: String { t("Desinstalar o MyMailForAI?", "Uninstall MyMailForAI?") }
    static var uninstallBody: String {
        t("Isto apaga as senhas do Chaveiro, as contas, a fila e o próprio app. Não dá para desfazer.",
          "This deletes the passwords from the Keychain, the accounts, the queue and the app itself. It cannot be undone.")
    }
    static var logoutTitle: String { t("Sair desta conta?", "Log out of this account?") }
    static var logoutBody: String {
        t("A senha some do Chaveiro e o que estava na fila desta conta é descartado.",
          "The password leaves the Keychain and anything queued for this account is dropped.")
    }
    static var noCLI: String {
        t("Não achei o comando mymailforai. Instale com: brew install --cask nspxmiguel/tap/mymailforai",
          "Could not find the mymailforai command. Install it with: brew install --cask nspxmiguel/tap/mymailforai")
    }
    static var claudeConnected: String { t("Ligado ao Claude Code", "Connected to Claude Code") }
    static var claudeConnect: String { t("Ligar ao Claude Code", "Connect to Claude Code") }
    static var refresh: String { t("Atualizar", "Refresh") }

    static func modeName(_ m: String) -> String {
        switch m {
        case "auto": return modeAuto
        case "read": return modeRead
        default: return modeAsk
        }
    }
    static func modeHelp(_ m: String) -> String {
        switch m {
        case "auto": return modeAutoHelp
        case "read": return modeReadHelp
        default: return modeAskHelp
        }
    }
}
