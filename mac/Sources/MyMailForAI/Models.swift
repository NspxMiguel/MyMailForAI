import Foundation

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
