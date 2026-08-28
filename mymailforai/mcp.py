"""Servidor MCP (stdio) — é por aqui que o Claude enxerga a caixa.

JSON-RPC 2.0, uma mensagem por linha. Sem dependência: o protocolo cabe na
stdlib, e assim o servidor roda em qualquer máquina com python3.

As ferramentas de escrita **não** falham quando o modo é `ask`: elas devolvem
"na fila, id X". A diferença importa — um erro faria o agente tentar de novo, e
a resposta certa é ele saber que a intenção ficou registrada esperando o dono.
"""

import json
import sys
import traceback
from typing import Any, Dict

from . import __version__, accounts as acc, actions, approvals, imapc, keychain, smtpc
from .i18n import set_language

PROTOCOL_VERSION = "2025-06-18"

_CONTA = {"type": "string", "description": "endereço da conta; omita para a padrão"}
_PASTA = {"type": "string", "default": "INBOX", "description": "pasta IMAP"}
_UID = {"type": "integer", "description": "o UID que a listagem devolveu"}

TOOLS = [
    {"name": "mailbox_status",
     "description": "Onde as coisas estão antes de agir: contas conectadas, o modo de cada "
                    "uma (automatic / ask / read-only), quantos itens esperam confirmação e "
                    "quanto do teto diário de envio já foi usado. Consulte antes de escrever "
                    "a primeira mensagem — é o que diz se um envio vai sair na hora ou entrar "
                    "na fila do dono.",
     "inputSchema": {"type": "object", "properties": {
         "with_unread": {"type": "boolean", "default": False,
                         "description": "também consultar o servidor pelo número de não lidos"}}}},

    {"name": "list_accounts",
     "description": "Só os endereços conectados, sem tocar no servidor.",
     "inputSchema": {"type": "object", "properties": {}}},

    {"name": "list_folders",
     "description": "As pastas da conta, com o papel de cada uma (sent, drafts, trash, "
                    "archive, junk) quando o servidor informa.",
     "inputSchema": {"type": "object", "properties": {"account": _CONTA}}},

    {"name": "list_inbox",
     "description": "As mensagens mais recentes de uma pasta: UID, remetente, assunto, data "
                    "e se está sem ler. Não marca nada como lido.",
     "inputSchema": {"type": "object", "properties": {
         "limit": {"type": "integer", "default": 20}, "folder": _PASTA,
         "unread_only": {"type": "boolean", "default": False}, "account": _CONTA}}},

    {"name": "search_email",
     "description": "Procura no servidor (IMAP SEARCH), sem baixar a caixa. Combine os "
                    "campos: text procura no corpo e cabeçalho, since aceita '2026-08-01' "
                    "ou '7d' para os últimos sete dias.",
     "inputSchema": {"type": "object", "properties": {
         "text": {"type": "string"}, "from": {"type": "string"}, "to": {"type": "string"},
         "subject": {"type": "string"}, "since": {"type": "string"}, "before": {"type": "string"},
         "unread_only": {"type": "boolean", "default": False},
         "flagged_only": {"type": "boolean", "default": False},
         "folder": _PASTA, "limit": {"type": "integer", "default": 25}, "account": _CONTA}}},

    {"name": "read_email",
     "description": "O corpo inteiro de uma mensagem, mais a lista de anexos. Por padrão NÃO "
                    "marca como lida — passe mark_read só quando o dono souber que você leu.",
     "inputSchema": {"type": "object", "properties": {
         "uid": _UID, "folder": _PASTA, "mark_read": {"type": "boolean", "default": False},
         "account": _CONTA}, "required": ["uid"]}},

    {"name": "download_attachment",
     "description": "Salva um anexo em disco e devolve o caminho, para você abrir com outra "
                    "ferramenta.",
     "inputSchema": {"type": "object", "properties": {
         "uid": _UID, "filename": {"type": "string"}, "folder": _PASTA,
         "dest": {"type": "string", "description": "caminho de destino; omita para ~/.mymailforai/attachments"},
         "account": _CONTA}, "required": ["uid", "filename"]}},

    {"name": "send_email",
     "description": "Manda uma mensagem nova. Em modo 'ask' ela NÃO sai: entra na fila e o "
                    "dono confirma na barra de menus — a resposta traz o id da fila, e isso "
                    "é sucesso, não erro. Não invente assinatura: o remetente já vai no "
                    "cabeçalho.",
     "inputSchema": {"type": "object", "properties": {
         "to": {"type": "string", "description": "destinatários separados por vírgula"},
         "subject": {"type": "string"}, "body": {"type": "string", "description": "texto puro"},
         "cc": {"type": "string"}, "bcc": {"type": "string"},
         "attachments": {"type": "array", "items": {"type": "string"},
                         "description": "caminhos de arquivo locais"},
         "account": _CONTA}, "required": ["to", "subject", "body"]}},

    {"name": "reply_email",
     "description": "Responde uma mensagem pelo UID, já na mesma conversa (In-Reply-To e "
                    "References) e com o original citado embaixo. reply_all inclui quem "
                    "estava em cópia. Mesmo freio do send_email.",
     "inputSchema": {"type": "object", "properties": {
         "uid": _UID, "body": {"type": "string"}, "folder": _PASTA,
         "reply_all": {"type": "boolean", "default": False},
         "quote": {"type": "boolean", "default": True}, "account": _CONTA},
         "required": ["uid", "body"]}},

    {"name": "forward_email",
     "description": "Encaminha uma mensagem para outro endereço, com um comentário opcional "
                    "em cima. Mesmo freio do send_email.",
     "inputSchema": {"type": "object", "properties": {
         "uid": _UID, "to": {"type": "string"}, "body": {"type": "string"},
         "folder": _PASTA, "account": _CONTA}, "required": ["uid", "to"]}},

    {"name": "save_draft",
     "description": "Escreve na pasta de Rascunhos, sem enviar nada. É o caminho quando o "
                    "dono quer reler e mandar do celular depois.",
     "inputSchema": {"type": "object", "properties": {
         "to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"},
         "cc": {"type": "string"}, "account": _CONTA}, "required": ["to", "subject", "body"]}},

    {"name": "mark_email",
     "description": "Marca como lida/não lida e com/sem estrela.",
     "inputSchema": {"type": "object", "properties": {
         "uid": _UID, "folder": _PASTA, "read": {"type": "boolean"},
         "starred": {"type": "boolean"}, "account": _CONTA}, "required": ["uid"]}},

    {"name": "move_email",
     "description": "Move para outra pasta, pelo nome exato que o list_folders devolveu.",
     "inputSchema": {"type": "object", "properties": {
         "uid": _UID, "to_folder": {"type": "string"}, "folder": _PASTA, "account": _CONTA},
         "required": ["uid", "to_folder"]}},

    {"name": "archive_email",
     "description": "Tira da entrada e põe no arquivo da conta.",
     "inputSchema": {"type": "object", "properties": {
         "uid": _UID, "folder": _PASTA, "account": _CONTA}, "required": ["uid"]}},

    {"name": "trash_email",
     "description": "Move para a Lixeira. É reversível de propósito: não existe ferramenta "
                    "de apagar de vez, e não adianta procurar.",
     "inputSchema": {"type": "object", "properties": {
         "uid": _UID, "folder": _PASTA, "account": _CONTA}, "required": ["uid"]}},

    {"name": "list_pending",
     "description": "O que você já pediu e ainda espera a confirmação do dono na barra de "
                    "menus. Consulte antes de repetir um envio — a mensagem provavelmente "
                    "está aqui, não perdida.",
     "inputSchema": {"type": "object", "properties": {"account": _CONTA}}},
]


def _json(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, indent=2, default=str)


def _call(name: str, args: Dict[str, Any]) -> str:
    conta = args.get("account")

    if name == "mailbox_status":
        return _json(actions.list_accounts(with_unread=bool(args.get("with_unread"))))
    if name == "list_accounts":
        cfg = acc.load()
        return _json({"default": cfg.get("default_account"), "accounts": list(cfg.get("accounts", {}))})
    if name == "list_folders":
        return _json(actions.list_folders(conta))
    if name == "list_inbox":
        return _json(actions.list_inbox(conta, folder=args.get("folder", "INBOX"),
                                        limit=int(args.get("limit", 20)),
                                        unread=bool(args.get("unread_only"))))
    if name == "search_email":
        return _json(actions.search_email(
            conta, folder=args.get("folder", "INBOX"), limit=int(args.get("limit", 25)),
            text=args.get("text"), sender=args.get("from"), to=args.get("to"),
            subject=args.get("subject"), since=args.get("since"), before=args.get("before"),
            unread=bool(args.get("unread_only")), flagged=bool(args.get("flagged_only"))))
    if name == "read_email":
        return _json(actions.read_email(int(args["uid"]), conta,
                                        folder=args.get("folder", "INBOX"),
                                        mark_read=bool(args.get("mark_read"))))
    if name == "download_attachment":
        return _json(actions.download_attachment(int(args["uid"]), args["filename"], conta,
                                                 folder=args.get("folder", "INBOX"),
                                                 dest=args.get("dest")))
    if name == "send_email":
        return _json(actions.send_email(args["to"], args.get("subject", ""), args.get("body", ""),
                                        conta, cc=args.get("cc"), bcc=args.get("bcc"),
                                        attachments=args.get("attachments")))
    if name == "reply_email":
        return _json(actions.reply_email(int(args["uid"]), args.get("body", ""), conta,
                                         folder=args.get("folder", "INBOX"),
                                         reply_all=bool(args.get("reply_all")),
                                         quote=args.get("quote", True)))
    if name == "forward_email":
        return _json(actions.forward_email(int(args["uid"]), args["to"], conta,
                                           folder=args.get("folder", "INBOX"),
                                           body=args.get("body", "")))
    if name == "save_draft":
        return _json(actions.save_draft(args["to"], args.get("subject", ""), args.get("body", ""),
                                        conta, cc=args.get("cc")))
    if name == "mark_email":
        return _json(actions.mark_email(int(args["uid"]), conta, folder=args.get("folder", "INBOX"),
                                        read=args.get("read"), starred=args.get("starred")))
    if name == "move_email":
        return _json(actions.move_email(int(args["uid"]), args["to_folder"], conta,
                                        folder=args.get("folder", "INBOX")))
    if name == "archive_email":
        return _json(actions.archive_email(int(args["uid"]), conta, folder=args.get("folder", "INBOX")))
    if name == "trash_email":
        return _json(actions.trash_email(int(args["uid"]), conta, folder=args.get("folder", "INBOX")))
    if name == "list_pending":
        return _json(approvals.pending(conta))
    raise ValueError(f"ferramenta desconhecida: {name}")


def _handle(message: Dict[str, Any]) -> Dict[str, Any]:
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "mymailforai", "version": __version__}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        nome = params.get("name")
        try:
            texto, erro = _call(nome, params.get("arguments") or {}), False
        except (actions.ActionError, imapc.MailError, smtpc.SendError,
                acc.AccountError, keychain.KeychainError, KeyError, ValueError) as exc:
            texto, erro = str(exc), True
        except Exception as exc:   # uma ferramenta quebrada não derruba a sessão da IA
            texto, erro = f"{type(exc).__name__}: {exc}", True
        return {"jsonrpc": "2.0", "id": msg_id,
                "result": {"content": [{"type": "text", "text": texto}], "isError": erro}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if msg_id is None:
        return {}
    return {"jsonrpc": "2.0", "id": msg_id,
            "error": {"code": -32601, "message": f"método não suportado: {method}"}}


def serve() -> int:
    try:
        set_language(acc.get_lang())
    except Exception:
        pass
    for linha in sys.stdin:
        linha = linha.strip()
        if not linha:
            continue
        try:
            mensagem = json.loads(linha)
        except json.JSONDecodeError:
            continue
        try:
            resposta = _handle(mensagem)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            resposta = {"jsonrpc": "2.0", "id": mensagem.get("id"),
                        "error": {"code": -32603, "message": "erro interno"}}
        if resposta:
            sys.stdout.write(json.dumps(resposta, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0
