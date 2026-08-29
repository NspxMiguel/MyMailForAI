import Foundation

/// Um endereço da mesma caixa. Não é outra conta: a entrada é a mesma, o que
/// muda é por qual endereço a mensagem sai.
struct Identity: Codable, Identifiable, Equatable {
    var address: String
    var name: String?
    var proven: Bool
    var sent: Int
    var received: Int
    var id: String { address }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        address = try c.decode(String.self, forKey: .address)
        name = try c.decodeIfPresent(String.self, forKey: .name)
        proven = try c.decodeIfPresent(Bool.self, forKey: .proven) ?? false
        sent = try c.decodeIfPresent(Int.self, forKey: .sent) ?? 0
        received = try c.decodeIfPresent(Int.self, forKey: .received) ?? 0
    }
}

struct Account: Codable, Identifiable, Equatable {
    var address: String
    var displayName: String?
    var provider: String
    var mode: String
    var askCoversMailbox: Bool
    var unread: Int?
    var pending: Int
    var sentToday: Int
    var dailyLimit: Int
    var isDefault: Bool
    var identities: [Identity]
    var sendAs: String

    var id: String { address }

    enum CodingKeys: String, CodingKey {
        case address
        case displayName = "display_name"
        case provider, mode
        case askCoversMailbox = "ask_covers_mailbox"
        case unread, pending
        case sentToday = "sent_today"
        case dailyLimit = "daily_limit"
        case isDefault = "is_default"
        case identities
        case sendAs = "send_as"
    }

    /// Decodificação tolerante: uma config gravada por uma versão anterior não
    /// tem `identities` nem `send_as`, e o painel inteiro ficaria em branco por
    /// causa de duas chaves ausentes.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        address = try c.decode(String.self, forKey: .address)
        displayName = try c.decodeIfPresent(String.self, forKey: .displayName)
        provider = try c.decodeIfPresent(String.self, forKey: .provider) ?? "custom"
        mode = try c.decodeIfPresent(String.self, forKey: .mode) ?? "ask"
        askCoversMailbox = try c.decodeIfPresent(Bool.self, forKey: .askCoversMailbox) ?? false
        unread = try c.decodeIfPresent(Int.self, forKey: .unread)
        pending = try c.decodeIfPresent(Int.self, forKey: .pending) ?? 0
        sentToday = try c.decodeIfPresent(Int.self, forKey: .sentToday) ?? 0
        dailyLimit = try c.decodeIfPresent(Int.self, forKey: .dailyLimit) ?? 50
        isDefault = try c.decodeIfPresent(Bool.self, forKey: .isDefault) ?? false
        identities = try c.decodeIfPresent([Identity].self, forKey: .identities) ?? []
        sendAs = try c.decodeIfPresent(String.self, forKey: .sendAs) ?? address
    }
}

struct AccountList: Codable {
    var `default`: String?
    var lang: String?
    var accounts: [Account]
}

struct QueueItem: Codable, Identifiable, Equatable {
    var id: String
    var account: String
    var action: String
    var createdAt: String
    var summary: String
    var detail: String?

    enum CodingKeys: String, CodingKey {
        case id, account, action, summary, detail
        case createdAt = "created_at"
    }
}

/// O que `login --detect` devolve: dá para mostrar o provedor e abrir a página
/// da senha antes de pedir qualquer coisa ao usuário.
struct ProviderInfo: Codable {
    var address: String
    var provider: String
    var label: String
    var passwordUrl: String
    var passwordHint: String
    var usernameHint: String

    enum CodingKeys: String, CodingKey {
        case address, provider, label
        case passwordUrl = "password_url"
        case passwordHint = "password_hint"
        case usernameHint = "username_hint"
    }
}
