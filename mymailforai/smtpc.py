"""Escrita: montar a mensagem e entregar por SMTP."""

import email.utils
import mimetypes
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any, Dict, List, Optional

from . import keychain
from .i18n import T


class SendError(RuntimeError):
    pass


def _lista(valor) -> List[str]:
    if not valor:
        return []
    if isinstance(valor, str):
        # aceita "a@x.com, b@y.com" e também ponto-e-vírgula, que é o que sai
        # de quem copiou de um cliente de e-mail
        return [p.strip() for p in valor.replace(";", ",").split(",") if p.strip()]
    return [str(p).strip() for p in valor if str(p).strip()]


def build(account: Dict[str, Any], to, subject: str, body: str,
          cc=None, bcc=None, html: Optional[str] = None,
          attachments: Optional[List[str]] = None,
          in_reply_to: Optional[str] = None, references: Optional[str] = None,
          ) -> EmailMessage:
    msg = EmailMessage()
    remetente = account["address"]
    nome = account.get("display_name") or ""
    msg["From"] = email.utils.formataddr((nome, remetente)) if nome else remetente
    destinos = _lista(to)
    if not destinos:
        raise SendError(T("sem destinatário", "no recipient"))
    msg["To"] = ", ".join(destinos)
    if cc:
        msg["Cc"] = ", ".join(_lista(cc))
    msg["Subject"] = subject or ""
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=remetente.rsplit("@", 1)[-1])
    if in_reply_to:
        # é isto que faz a resposta aparecer na mesma conversa, e não solta
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = (references + " " + in_reply_to).strip() if references else in_reply_to
    msg.set_content(body or "")
    if html:
        msg.add_alternative(html, subtype="html")
    limite = int(account.get("max_attachment_mb", 20)) * 1024 * 1024
    total = 0
    for caminho in attachments or []:
        expandido = os.path.expanduser(caminho)
        if not os.path.isfile(expandido):
            raise SendError(T(f"anexo não encontrado: {caminho}",
                              f"attachment not found: {caminho}"))
        with open(expandido, "rb") as fh:
            dados = fh.read()
        total += len(dados)
        if total > limite:
            raise SendError(T(
                f"anexos passam do teto de {account.get('max_attachment_mb', 20)} MB",
                f"attachments exceed the {account.get('max_attachment_mb', 20)} MB cap"))
        tipo, _ = mimetypes.guess_type(expandido)
        maintype, subtype = (tipo or "application/octet-stream").split("/", 1)
        msg.add_attachment(dados, maintype=maintype, subtype=subtype,
                           filename=os.path.basename(expandido))
    return msg


def deliver(account: Dict[str, Any], msg: EmailMessage, bcc=None,
            password: Optional[str] = None) -> List[str]:
    cfg = account["smtp"]
    host, port = cfg["host"], int(cfg["port"])
    senha = password if password is not None else keychain.get_secret(account["address"])
    destinos = _lista(msg.get("To")) + _lista(msg.get("Cc")) + _lista(bcc)
    # o servidor quer só o endereço; "Nome <a@b.com>" faz ele recusar o RCPT
    enderecos = [email.utils.parseaddr(d)[1] or d for d in destinos]
    contexto = ssl.create_default_context()
    try:
        if cfg.get("ssl"):
            servidor = smtplib.SMTP_SSL(host, port, timeout=30, context=contexto)
        else:
            servidor = smtplib.SMTP(host, port, timeout=30)
            if cfg.get("starttls", True):
                servidor.starttls(context=contexto)
        with servidor:
            servidor.login(account.get("username") or account["address"], senha)
            servidor.send_message(msg, to_addrs=enderecos)
    except smtplib.SMTPAuthenticationError as erro:
        raise SendError(T(f"o servidor recusou a senha de {account['address']}: {erro}",
                          f"the server refused the password for {account['address']}: {erro}")) from erro
    except (OSError, smtplib.SMTPException) as erro:
        raise SendError(T(f"não consegui enviar por {host}:{port} — {erro}",
                          f"could not send through {host}:{port} — {erro}")) from erro
    return enderecos


def quote_original(original: Dict[str, Any], corpo: str) -> str:
    """O corpo da resposta com o original citado embaixo, como um cliente faria."""
    citado = "\n".join("> " + linha for linha in (original.get("body") or "").splitlines())
    cabecalho = T(
        f"\n\nEm {original.get('date', '')}, {original.get('from', '')} escreveu:\n",
        f"\n\nOn {original.get('date', '')}, {original.get('from', '')} wrote:\n")
    return (corpo or "") + cabecalho + citado


def forward_body(original: Dict[str, Any], corpo: str = "") -> str:
    cabecalho = T("---------- Mensagem encaminhada ----------",
                  "---------- Forwarded message ----------")
    campos = [f"From: {original.get('from', '')}", f"Date: {original.get('date', '')}",
              f"Subject: {original.get('subject', '')}", f"To: {original.get('to', '')}"]
    return f"{corpo}\n\n{cabecalho}\n" + "\n".join(campos) + "\n\n" + (original.get("body") or "")
