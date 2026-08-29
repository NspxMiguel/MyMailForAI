import AppKit
import SwiftUI
import UserNotifications

/// O estado do painel. Não fala IMAP: chama o mesmo `mymailforai` que uma
/// pessoa digitaria no terminal, e por isso app e terminal nunca discordam
/// sobre o que aconteceu — o modo, o teto diário e o histórico valem igual.
@MainActor
final class Store: ObservableObject {
    static let shared = Store()

    /// O item da barra escuta isto para redesenhar o contador.
    static let filaMudou = Notification.Name("MyMailForAI.filaMudou")

    @Published var accounts: [Account] = []
    @Published var pending: [QueueItem] = []
    @Published var defaultAccount: String?
    @Published var busy = false
    @Published var status: String?
    @Published var error: String?
    @Published var claudeConnected = false
    @Published var cliMissing = false
    /// Trocar de idioma redesenha o painel inteiro: os textos são estáticos.
    @Published var langTick = 0

    private var rapido: Timer?
    private var lento: Timer?

    var pendingCount: Int { pending.count }

    /// Onde o binário pode estar: dentro do bundle (instalado pelo Homebrew),
    /// no PATH, ou no clone de quem está mexendo no código.
    static func cliPath() -> String? {
        var candidatos: [String] = []
        if let recursos = Bundle.main.resourceURL {
            candidatos.append(recursos.appendingPathComponent("mymailforai/bin/mymailforai").path)
        }
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        candidatos += [
            "\(home)/.local/bin/mymailforai",
            "/opt/homebrew/bin/mymailforai",
            "/usr/local/bin/mymailforai",
            "\(home)/Documents/Claude/Projetos/MyMailForAI/bin/mymailforai",
        ]
        return candidatos.first { FileManager.default.isExecutableFile(atPath: $0) }
    }

    struct Saida { var status: Int32; var out: String; var err: String }

    /// Roda o CLI. `input` vai pelo stdin de propósito: senha em argumento
    /// apareceria em `ps` para qualquer processo da máquina.
    nonisolated static func run(_ cli: String, _ args: [String], input: String? = nil,
                               timeout: TimeInterval = 90) -> Saida {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: cli)
        p.arguments = args
        let saida = Pipe(), erro = Pipe(), entrada = Pipe()
        p.standardOutput = saida; p.standardError = erro; p.standardInput = entrada
        var ambiente = ProcessInfo.processInfo.environment
        ambiente["MYMAILFORAI_LANG"] = L.lang
        p.environment = ambiente
        do { try p.run() } catch { return Saida(status: -1, out: "", err: error.localizedDescription) }
        if let input {
            entrada.fileHandleForWriting.write(Data((input + "\n").utf8))
        }
        try? entrada.fileHandleForWriting.close()
        // Ler os dois canais em paralelo: um pipe cheio trava o processo filho,
        // e o app ficaria "carregando" para sempre numa caixa grande.
        var dadosSaida = Data(), dadosErro = Data()
        let grupo = DispatchGroup()
        grupo.enter(); DispatchQueue.global().async {
            dadosSaida = saida.fileHandleForReading.readDataToEndOfFile(); grupo.leave() }
        grupo.enter(); DispatchQueue.global().async {
            dadosErro = erro.fileHandleForReading.readDataToEndOfFile(); grupo.leave() }
        if grupo.wait(timeout: .now() + timeout) == .timedOut {
            p.terminate()
            return Saida(status: -2, out: "", err: L.t("demorou demais", "timed out"))
        }
        p.waitUntilExit()
        return Saida(status: p.terminationStatus,
                     out: String(data: dadosSaida, encoding: .utf8) ?? "",
                     err: String(data: dadosErro, encoding: .utf8) ?? "")
    }

    // ------------------------------------------------------------- ciclo

    func start() {
        guard rapido == nil else { return }
        refresh()
        refreshUnread()
        checkClaude()
        // 4s deixa a fila viva sem subir processo o tempo todo; os não lidos
        // custam uma conexão IMAP, então vão num relógio bem mais lento.
        rapido = Timer.scheduledTimer(withTimeInterval: 4, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
        lento = Timer.scheduledTimer(withTimeInterval: 120, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refreshUnread() }
        }
    }

    func refresh() { carregar(comNaoLidos: false) }
    func refreshUnread() { carregar(comNaoLidos: true) }

    private func carregar(comNaoLidos: Bool) {
        guard let cli = Store.cliPath() else { cliMissing = true; return }
        cliMissing = false
        let naoLidosAtuais = Dictionary(uniqueKeysWithValues: accounts.map { ($0.address, $0.unread) })
        Task.detached(priority: .utility) {
            let contas = Store.run(cli, ["accounts", "--json"] + (comNaoLidos ? ["--unread"] : []),
                                   timeout: comNaoLidos ? 120 : 30)
            let fila = Store.run(cli, ["pending", "--json"], timeout: 30)
            let decoder = JSONDecoder()
            let lista = (try? decoder.decode(AccountList.self, from: Data(contas.out.utf8)))
            let itens = (try? decoder.decode([QueueItem].self, from: Data(fila.out.utf8))) ?? []
            await MainActor.run {
                if var lista {
                    if !comNaoLidos {
                        // a leitura rápida não consulta o servidor: manter o
                        // número que já estava evita o painel piscar "—"
                        for i in lista.accounts.indices {
                            lista.accounts[i].unread = naoLidosAtuais[lista.accounts[i].address] ?? nil
                        }
                    }
                    self.accounts = lista.accounts
                    self.defaultAccount = lista.default
                }
                let novos = itens.filter { item in !self.pending.contains(where: { $0.id == item.id }) }
                let mudou = itens.count != self.pending.count
                self.pending = itens
                if mudou { NotificationCenter.default.post(name: Store.filaMudou, object: nil) }
                // O contador na barra só ajuda quem está olhando pra ela. Um
                // aviso é o que faz o envio parado não ficar parado a tarde toda.
                for item in novos { self.avisar(item) }
            }
        }
    }

    private func checkClaude() {
        guard let cli = Store.cliPath() else { return }
        Task.detached(priority: .background) {
            let r = Store.run(cli, ["connect", "--status", "--json"], timeout: 60)
            let ligado = r.out.contains("\"connected\": true")
            await MainActor.run { self.claudeConnected = ligado }
        }
    }

    private var jaPediuPermissao = false

    private func avisar(_ item: QueueItem) {
        let centro = UNUserNotificationCenter.current()
        if !jaPediuPermissao {
            jaPediuPermissao = true
            centro.requestAuthorization(options: [.alert, .badge]) { _, _ in }
        }
        let conteudo = UNMutableNotificationContent()
        conteudo.title = L.t("Esperando você", "Waiting for you")
        conteudo.subtitle = item.summary
        conteudo.body = L.t("Clique no ícone da barra para confirmar ou recusar.",
                            "Click the menu bar icon to confirm or reject.")
        centro.add(UNNotificationRequest(identifier: item.id, content: conteudo, trigger: nil))
    }

    // ------------------------------------------------------------- ações

    private func agir(_ args: [String], então: (@MainActor (Saida) -> Void)? = nil) {
        guard let cli = Store.cliPath() else { cliMissing = true; return }
        busy = true; error = nil
        Task.detached(priority: .userInitiated) {
            let r = Store.run(cli, args)
            await MainActor.run {
                self.busy = false
                if r.status != 0 {
                    self.error = Store.mensagemDeErro(r)
                }
                então?(r)
                self.refresh()
            }
        }
    }

    static func mensagemDeErro(_ r: Saida) -> String {
        let bruto = r.err.isEmpty ? r.out : r.err
        // o CLI manda `{"error": "..."}` no stderr quando é --json
        if let dado = bruto.data(using: .utf8),
           let obj = try? JSONSerialization.jsonObject(with: dado) as? [String: Any],
           let msg = obj["error"] as? String {
            return msg
        }
        return bruto.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func approve(_ id: String) { agir(["approve", id, "--json"]) }
    func reject(_ id: String) { agir(["reject", id, "--json"]) }

    func setMode(_ mode: String, account: String) {
        // otimista: o botão responde na hora, e o refresh confirma
        if let i = accounts.firstIndex(where: { $0.address == account }) {
            accounts[i].mode = mode
        }
        agir(["mode", mode, "--account", account, "--json"])
    }

    func setStrict(_ on: Bool, account: String) {
        if let i = accounts.firstIndex(where: { $0.address == account }) {
            accounts[i].askCoversMailbox = on
        }
        let modo = accounts.first(where: { $0.address == account })?.mode ?? "ask"
        agir(["mode", modo, "--account", account, on ? "--strict" : "--no-strict", "--json"])
    }

    func setDefault(_ account: String) { agir(["default", account, "--json"]) }

    func setSendAs(_ address: String, account: String) {
        if let i = accounts.firstIndex(where: { $0.address == account }) {
            accounts[i].sendAs = address
        }
        agir(["identities", "--send-as", address, "--account", account, "--json"])
    }

    /// Varrer a caixa custa uma conexão IMAP e alguns segundos: só quando pedem.
    func rescanIdentities(_ account: String) {
        agir(["identities", "--scan", "--account", account, "--json"])
    }

    func setLanguage(_ code: String) {
        L.escolher(code)
        langTick += 1
        // O CLI guarda a mesma escolha: terminal e painel falam o mesmo idioma.
        agir(["lang", code, "--json"])
    }

    func logout(_ account: String) { agir(["logout", account, "--json"]) }

    func connectClaude() {
        agir(["connect", "--json"]) { _ in self.claudeConnected = true }
    }

    func detect(_ address: String) async -> ProviderInfo? {
        guard let cli = Store.cliPath() else { return nil }
        let r = await Task.detached(priority: .userInitiated) {
            Store.run(cli, ["login", address, "--detect", "--json"], timeout: 20)
        }.value
        guard r.status == 0 else { return nil }
        return try? JSONDecoder().decode(ProviderInfo.self, from: Data(r.out.utf8))
    }

    func login(address: String, password: String, username: String?) async -> String? {
        guard let cli = Store.cliPath() else { return L.noCLI }
        busy = true; error = nil
        var args = ["login", address, "--password-stdin", "--no-open", "--json"]
        if let username, !username.isEmpty, username != address {
            args += ["--username", username]
        }
        let r = await Task.detached(priority: .userInitiated) {
            Store.run(cli, args, input: password, timeout: 120)
        }.value
        busy = false
        refresh()
        refreshUnread()
        return r.status == 0 ? nil : Store.mensagemDeErro(r)
    }

    func uninstall() {
        guard let cli = Store.cliPath() else { return }
        // síncrono de propósito: o CLI mora dentro do bundle que está sendo
        // removido, e sair antes da hora deixaria metade do trabalho feito
        _ = Store.run(cli, ["uninstall", "--yes", "--json"], timeout: 120)
        NSApp.terminate(nil)
    }
}
