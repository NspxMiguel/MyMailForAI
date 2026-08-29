"""O que o agente pode fazer. Uma porta só, e o freio no meio dela.

CLI e MCP chamam daqui — nenhum dos dois fala IMAP direto. Assim o modo, o teto
diário e o histórico valem igual pelos dois caminhos, e não existe atalho que
escape do freio.
"""

import os
from typing import Any, Dict, List, Optional

from . import accounts as acc
from . import approvals, gate, identities, imapc, keychain, smtpc
from .i18n import T
from .paths import ensure_attach_dir


class ActionError(RuntimeError):
    pass


def _email_puro(valor: str) -> str:
    import email.utils
    return (email.utils.parseaddr(valor)[1] or valor).lower().strip()


def _conta(address: Optional[str]) -> Dict[str, Any]:
    return acc.get(address)


def _resumo_destino(payload: Dict[str, Any]) -> str:
    destinos = ", ".join(payload.get("to") or []) or "?"
    resumo = f"→ {destinos} · {payload.get('subject') or '(sem assunto)'}"
    # o remetente entra no resumo só quando não é o de sempre: ele precisa ver,
    # antes de confirmar, se a mensagem vai sair por outro endereço dele
    if payload.get("from"):
        resumo = f"{payload['from']} {resumo}"
    return resumo


def _remetente(conta: Dict[str, Any], pedido: Optional[str]) -> Optional[str]:
    """Confere o endereço escolhido contra os que a caixa tem de verdade.

    O servidor recusaria um From estranho no meio do envio, com uma mensagem
    de SMTP que não ajuda ninguém. Melhor recusar aqui, dizendo quais existem.
    """
    if not pedido:
        return conta.get("send_as")
    pedido = pedido.strip().lower()
    conhecidos = [i["address"] for i in (conta.get("identities") or [])]
    if not conhecidos or pedido in conhecidos:
        return pedido
    raise ActionError(T(
        f"'{pedido}' não é um endereço desta caixa. Ela tem: {', '.join(conhecidos)}. "
        "Rode 'mymailforai identities --scan' se você acabou de criar um.",
        f"'{pedido}' is not an address of this mailbox. It has: {', '.join(conhecidos)}. "
        "Run 'mymailforai identities --scan' if you just created one."))


# ------------------------------------------------------------------- leitura

def list_accounts(with_unread: bool = False) -> Dict[str, Any]:
    cfg = acc.load()
    saida = []
    for endereco in cfg.get("accounts", {}):
        conta = acc.get(endereco)
        nao_lidos = None
        if with_unread:
            try:
                with imapc.connect(conta) as conn:
                    nao_lidos = imapc.unread_count(conn, "INBOX")
            except (imapc.MailError, keychain.KeychainError):
                nao_lidos = None      # servidor fora do ar: "—", nunca zero
        saida.append({
            "address": endereco,
            "display_name": conta.get("display_name"),
            "provider": conta.get("provider"),
            "mode": conta.get("mode", "ask"),
            "ask_covers_mailbox": bool(conta.get("ask_covers_mailbox")),
            "unread": nao_lidos,
            "pending": len(approvals.pending(endereco)),
            "identities": conta.get("identities") or [],
            "send_as": conta.get("send_as") or endereco,
            "sent_today": approvals.sent_today(endereco),
            "daily_limit": int(conta.get("daily_limit", 50)),
            "is_default": endereco == cfg.get("default_account"),
        })
    return {"default": cfg.get("default_account"), "lang": cfg.get("lang"), "accounts": saida}


def list_folders(account: Optional[str] = None) -> List[Dict[str, Any]]:
    conta = _conta(account)
    with imapc.connect(conta) as conn:
        return imapc.folders(conn)


def list_inbox(account: Optional[str] = None, folder: str = "INBOX",
               limit: int = 20, unread: bool = False) -> List[Dict[str, Any]]:
    conta = _conta(account)
    with imapc.connect(conta) as conn:
        uids = imapc.search(conn, folder=folder, limit=limit, unread=unread)
        return imapc.summaries(conn, uids, folder=folder)


def search_email(account: Optional[str] = None, folder: str = "INBOX", limit: int = 25,
                 **criterios) -> List[Dict[str, Any]]:
    conta = _conta(account)
    with imapc.connect(conta) as conn:
        uids = imapc.search(conn, folder=folder, limit=limit, **criterios)
        return imapc.summaries(conn, uids, folder=folder)


def read_email(uid: int, account: Optional[str] = None, folder: str = "INBOX",
               mark_read: bool = False) -> Dict[str, Any]:
    conta = _conta(account)
    with imapc.connect(conta) as conn:
        return imapc.fetch(conn, int(uid), folder=folder, mark_read=mark_read)


def download_attachment(uid: int, filename: str, account: Optional[str] = None,
                        folder: str = "INBOX", dest: Optional[str] = None) -> Dict[str, Any]:
    conta = _conta(account)
    with imapc.connect(conta) as conn:
        nome, dados = imapc.fetch_attachment(conn, int(uid), filename, folder=folder)
    destino = os.path.expanduser(dest) if dest else str(ensure_attach_dir() / f"{uid}-{nome}")
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    with open(destino, "wb") as fh:
        fh.write(dados)
    return {"path": destino, "filename": nome, "bytes": len(dados)}


# -------------------------------------------------------------------- escrita

def _passar_pelo_freio(conta: Dict[str, Any], action: str, payload: Dict[str, Any],
                       summary: str, detail: str, agent: str) -> Dict[str, Any]:
    decisao, motivo = gate.decide(conta, action)
    if decisao == gate.REFUSE:
        approvals.log(conta["address"], action, "refused", summary, detail=motivo)
        raise ActionError(motivo)
    if decisao == gate.QUEUE:
        item = approvals.enqueue(conta["address"], action, summary, detail, payload, agent=agent)
        return {"status": "queued", "id": item["id"], "summary": summary,
                "message": T(f"na fila, id {item['id']} — confirme na barra de menus",
                             f"queued as {item['id']} — confirm it in the menu bar")}
    resultado = _executar(conta, payload)
    approvals.log(conta["address"], action, resultado.get("status", "done"), summary)
    return resultado


def _executar(conta: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """Faz de verdade. É o mesmo caminho para o que sai na hora e para o aprovado."""
    kind = payload["kind"]

    if kind in ("send", "draft"):
        msg = smtpc.build(
            conta, to=payload.get("to"), subject=payload.get("subject", ""),
            body=payload.get("body", ""), cc=payload.get("cc"),
            html=payload.get("html") or None, attachments=payload.get("attachments") or [],
            in_reply_to=payload.get("in_reply_to") or None,
            references=payload.get("references") or None,
            from_address=payload.get("from") or None)
        if kind == "draft":
            with imapc.connect(conta) as conn:
                pasta = imapc.special_folder(conn, "drafts") or "Drafts"
                imapc.append(conn, pasta, bytes(msg), flags="\\Draft")
            return {"status": "drafted", "folder": pasta,
                    "message": T(f"rascunho salvo em '{pasta}'", f"draft saved to '{pasta}'")}
        enderecos = smtpc.deliver(conta, msg, bcc=payload.get("bcc"))
        guardado = None
        if conta.get("append_to_sent", conta.get("provider") != "gmail"):
            # o Gmail já guarda o que sai pelo SMTP dele; nos outros, sem isto o
            # e-mail some da pasta Enviados e ele acha que nunca foi mandado
            try:
                with imapc.connect(conta) as conn:
                    guardado = imapc.special_folder(conn, "sent") or "Sent"
                    imapc.append(conn, guardado, bytes(msg), flags="\\Seen")
            except Exception:
                # Guardar a cópia em Enviados é conforto; o envio já aconteceu.
                # Deixar essa falha subir marcaria como "falhou" um e-mail que
                # saiu — e o agente mandaria de novo.
                guardado = None
        return {"status": "sent", "to": enderecos, "message_id": msg.get("Message-ID"),
                "saved_to": guardado,
                "message": T(f"enviado para {', '.join(enderecos)}",
                             f"sent to {', '.join(enderecos)}")}

    if kind == "flag":
        with imapc.connect(conta) as conn:
            imapc.store_flags(conn, int(payload["uid"]), payload.get("folder", "INBOX"),
                              add=payload.get("add"), remove=payload.get("remove"))
        return {"status": "flagged", "uid": payload["uid"],
                "message": T("marcado", "flagged")}

    if kind == "move":
        with imapc.connect(conta) as conn:
            destino = payload.get("target")
            if not destino and payload.get("role"):
                destino = imapc.special_folder(conn, payload["role"])
                if not destino:
                    raise ActionError(T(
                        f"esta conta não tem pasta de {payload['role']} — "
                        "use move --to-folder com o nome exato",
                        f"this account has no {payload['role']} folder — "
                        "use move --to-folder with the exact name"))
            imapc.move(conn, int(payload["uid"]), payload.get("folder", "INBOX"), destino)
        return {"status": "moved", "uid": payload["uid"], "to_folder": destino,
                "message": T(f"movido para '{destino}'", f"moved to '{destino}'")}

    raise ActionError(f"ação desconhecida: {kind}")


def send_email(to, subject: str, body: str, account: Optional[str] = None,
               cc=None, bcc=None, html: Optional[str] = None,
               attachments: Optional[List[str]] = None, from_address: Optional[str] = None,
               agent: str = "claude") -> Dict[str, Any]:
    conta = _conta(account)
    payload = {"kind": "send", "to": smtpc._lista(to), "cc": smtpc._lista(cc),
               "bcc": smtpc._lista(bcc), "subject": subject, "body": body,
               "html": html or "", "attachments": attachments or [],
               "from": _remetente(conta, from_address)}
    return _passar_pelo_freio(conta, "send", payload, _resumo_destino(payload),
                              (body or "")[:2000], agent)


def reply_email(uid: int, body: str, account: Optional[str] = None, folder: str = "INBOX",
                reply_all: bool = False, attachments: Optional[List[str]] = None,
                quote: bool = True, from_address: Optional[str] = None,
                agent: str = "claude") -> Dict[str, Any]:
    conta = _conta(account)
    with imapc.connect(conta) as conn:
        original = imapc.fetch(conn, int(uid), folder=folder)
    destino = original.get("reply_to") or original.get("from")
    # Responder por onde a mensagem chegou: se ela veio para miguel@nspx.dev,
    # responder como claude@nspx.dev confundiria quem está do outro lado.
    remetente = _remetente(conta, from_address)
    if not from_address and not conta.get("send_as"):
        meus = {i["address"] for i in (conta.get("identities") or [])}
        for endereco in smtpc._lista(original.get("to")) + smtpc._lista(original.get("cc")):
            limpo = _email_puro(endereco)
            if limpo in meus:
                remetente = limpo
                break
    cc = []
    if reply_all:
        meus_todos = {i["address"] for i in (conta.get("identities") or [])} or {conta["address"].lower()}
        cc = [e for e in smtpc._lista(original.get("to")) + smtpc._lista(original.get("cc"))
              if _email_puro(e) not in meus_todos]
    assunto = original.get("subject") or ""
    if not assunto.lower().startswith("re:"):
        assunto = f"Re: {assunto}"
    corpo = smtpc.quote_original(original, body) if quote else body
    payload = {"kind": "send", "to": smtpc._lista(destino), "cc": cc, "bcc": [],
               "subject": assunto, "body": corpo, "html": "",
               "attachments": attachments or [],
               "in_reply_to": original.get("message_id"),
               "references": original.get("references"), "from": remetente}
    return _passar_pelo_freio(conta, "reply", payload, _resumo_destino(payload),
                              (body or "")[:2000], agent)


def forward_email(uid: int, to, account: Optional[str] = None, folder: str = "INBOX",
                  body: str = "", from_address: Optional[str] = None,
                  agent: str = "claude") -> Dict[str, Any]:
    conta = _conta(account)
    with imapc.connect(conta) as conn:
        original = imapc.fetch(conn, int(uid), folder=folder)
    assunto = original.get("subject") or ""
    if not assunto.lower().startswith("fwd:"):
        assunto = f"Fwd: {assunto}"
    payload = {"kind": "send", "to": smtpc._lista(to), "cc": [], "bcc": [],
               "subject": assunto, "body": smtpc.forward_body(original, body),
               "html": "", "attachments": [], "from": _remetente(conta, from_address)}
    return _passar_pelo_freio(conta, "forward", payload, _resumo_destino(payload),
                              (body or "")[:2000], agent)


def save_draft(to, subject: str, body: str, account: Optional[str] = None,
               cc=None, from_address: Optional[str] = None,
               agent: str = "claude") -> Dict[str, Any]:
    conta = _conta(account)
    payload = {"kind": "draft", "to": smtpc._lista(to), "cc": smtpc._lista(cc),
               "subject": subject, "body": body,
               "from": _remetente(conta, from_address)}
    return _passar_pelo_freio(conta, "draft", payload, _resumo_destino(payload),
                              (body or "")[:2000], agent)


def mark_email(uid: int, account: Optional[str] = None, folder: str = "INBOX",
               read: Optional[bool] = None, starred: Optional[bool] = None,
               agent: str = "claude") -> Dict[str, Any]:
    conta = _conta(account)
    add, remove = [], []
    if read is True:
        add.append("\\Seen")
    elif read is False:
        remove.append("\\Seen")
    if starred is True:
        add.append("\\Flagged")
    elif starred is False:
        remove.append("\\Flagged")
    if not add and not remove:
        raise ActionError(T("nada para marcar — passe --read/--unread/--star/--unstar",
                            "nothing to mark — pass --read/--unread/--star/--unstar"))
    payload = {"kind": "flag", "uid": int(uid), "folder": folder, "add": add, "remove": remove}
    resumo = f"uid {uid} · {' '.join(add + ['-' + f for f in remove])}"
    return _passar_pelo_freio(conta, "flag", payload, resumo, "", agent)


def move_email(uid: int, to_folder: str, account: Optional[str] = None,
               folder: str = "INBOX", agent: str = "claude") -> Dict[str, Any]:
    conta = _conta(account)
    payload = {"kind": "move", "uid": int(uid), "folder": folder, "target": to_folder}
    return _passar_pelo_freio(conta, "move", payload, f"uid {uid} → {to_folder}", "", agent)


def archive_email(uid: int, account: Optional[str] = None, folder: str = "INBOX",
                  agent: str = "claude") -> Dict[str, Any]:
    conta = _conta(account)
    payload = {"kind": "move", "uid": int(uid), "folder": folder, "role": "archive"}
    return _passar_pelo_freio(conta, "archive", payload, f"uid {uid} → archive", "", agent)


def trash_email(uid: int, account: Optional[str] = None, folder: str = "INBOX",
                agent: str = "claude") -> Dict[str, Any]:
    """Lixeira é mover para a pasta Lixeira. Apagar de vez não existe aqui."""
    conta = _conta(account)
    payload = {"kind": "move", "uid": int(uid), "folder": folder, "role": "trash"}
    return _passar_pelo_freio(conta, "trash", payload, f"uid {uid} → trash", "", agent)


# ------------------------------------------------------------------ aprovação

def approve(item_id: str) -> Dict[str, Any]:
    item = approvals.get(item_id)
    if item["status"] != "pending":
        raise ActionError(T(f"o item {item_id} já foi {item['status']}",
                            f"item {item_id} was already {item['status']}"))
    conta = acc.get(item["account"])
    try:
        resultado = _executar(conta, item["payload"])
    except Exception as erro:
        approvals.finish(item_id, "failed", str(erro))
        approvals.log(item["account"], item["action"], "failed", item["summary"],
                      item_id=item_id, detail=str(erro))
        raise
    approvals.finish(item_id, "approved", resultado)
    approvals.log(item["account"], item["action"], resultado.get("status", "done"),
                  item["summary"], item_id=item_id)
    return {"id": item_id, **resultado}


def reject(item_id: str, reason: str = "") -> Dict[str, Any]:
    item = approvals.get(item_id)
    if item["status"] != "pending":
        raise ActionError(T(f"o item {item_id} já foi {item['status']}",
                            f"item {item_id} was already {item['status']}"))
    approvals.finish(item_id, "rejected", reason)
    approvals.log(item["account"], item["action"], "rejected", item["summary"],
                  item_id=item_id, detail=reason)
    return {"id": item_id, "status": "rejected", "reason": reason,
            "message": T("recusado — nada foi enviado", "rejected — nothing was sent")}


# ---------------------------------------------------------------- identidades

def scan_identities(account: Optional[str] = None) -> List[Dict[str, Any]]:
    """Descobre os outros endereços da caixa e guarda o que achou."""
    conta = _conta(account)
    achadas = identities.scan(conta)
    cfg = acc.load()
    cfg["accounts"][conta["address"]]["identities"] = achadas
    acc.save(cfg)
    return achadas


def set_send_as(address: str, account: Optional[str] = None,
                name: Optional[str] = None) -> Dict[str, Any]:
    conta = _conta(account)
    escolhido = _remetente(conta, address)
    cfg = acc.load()
    cfg["accounts"][conta["address"]]["send_as"] = escolhido
    if name is not None:
        lista = cfg["accounts"][conta["address"]].get("identities") or []
        for item in lista:
            if item["address"] == escolhido:
                item["name"] = name
                break
        else:
            lista.append({"address": escolhido, "name": name, "proven": False,
                          "sent": 0, "received": 0})
        cfg["accounts"][conta["address"]]["identities"] = lista
    acc.save(cfg)
    return {"account": conta["address"], "send_as": escolhido, "name": name}


# --------------------------------------------------------------------- login

def verify_credentials(conta: Dict[str, Any], password: str) -> Dict[str, Any]:
    """Só grava a senha depois que IMAP e SMTP aceitarem ela de verdade."""
    with imapc.connect(conta, password=password) as conn:
        pastas = imapc.folders(conn)
        nao_lidos = imapc.unread_count(conn, "INBOX")
    import smtplib
    import ssl as _ssl
    cfg = conta["smtp"]
    try:
        if cfg.get("ssl"):
            servidor = smtplib.SMTP_SSL(cfg["host"], int(cfg["port"]), timeout=30,
                                        context=_ssl.create_default_context())
        else:
            servidor = smtplib.SMTP(cfg["host"], int(cfg["port"]), timeout=30)
            if cfg.get("starttls", True):
                servidor.starttls(context=_ssl.create_default_context())
        with servidor:
            servidor.login(conta.get("username") or conta["address"], password)
    except Exception as erro:
        raise ActionError(T(
            f"o IMAP aceitou, mas o SMTP em {cfg['host']}:{cfg['port']} não: {erro}",
            f"IMAP accepted, but SMTP at {cfg['host']}:{cfg['port']} did not: {erro}")) from erro
    return {"folders": len(pastas), "unread": nao_lidos}
