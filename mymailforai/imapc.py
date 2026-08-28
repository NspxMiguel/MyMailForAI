"""Leitura: IMAP pelo imaplib da stdlib.

Todo o "acesso total" do pedido passa por aqui — pastas, busca, corpo, anexos,
marcar, mover, arquivar, lixeira e rascunho. O que NÃO existe neste arquivo, de
propósito, é apagar de verdade: mover para a Lixeira é reversível, `EXPUNGE`
cego não é, e uma IA não devia ter na mão uma operação sem volta.
"""

import datetime
import email
import email.header
import email.utils
import imaplib
import re
import ssl
from contextlib import contextmanager
from email.message import Message
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import keychain
from .i18n import T

# Caixa grande devolve linha grande; o padrão do imaplib corta e a sessão morre
# com "got more than 10000 bytes" em vez de dizer o que houve.
imaplib._MAXLINE = max(getattr(imaplib, "_MAXLINE", 0), 10_000_000)


class MailError(RuntimeError):
    pass


# ------------------------------------------------------------ UTF-7 modificado
# Nome de pasta em IMAP não é UTF-8: é o UTF-7 modificado da RFC 3501. Sem isto,
# "Rascunhos" funciona e "Mensagens Enviadas" com acento vira lixo.

def _b64_imap(texto: str) -> str:
    import base64
    bruto = texto.encode("utf-16-be")
    return base64.b64encode(bruto).decode("ascii").rstrip("=").replace("/", ",")


def _unb64_imap(pedaco: str) -> str:
    import base64
    pedaco = pedaco.replace(",", "/")
    pedaco += "=" * (-len(pedaco) % 4)
    return base64.b64decode(pedaco).decode("utf-16-be")


def encode_folder(nome: str) -> str:
    saida, buffer = [], []
    for ch in nome:
        if ch == "&":
            if buffer:
                saida.append("&" + _b64_imap("".join(buffer)) + "-")
                buffer = []
            saida.append("&-")
        elif 0x20 <= ord(ch) <= 0x7E:
            if buffer:
                saida.append("&" + _b64_imap("".join(buffer)) + "-")
                buffer = []
            saida.append(ch)
        else:
            buffer.append(ch)
    if buffer:
        saida.append("&" + _b64_imap("".join(buffer)) + "-")
    return "".join(saida)


def decode_folder(nome: str) -> str:
    saida, i = [], 0
    while i < len(nome):
        if nome[i] == "&":
            fim = nome.find("-", i)
            if fim < 0:
                saida.append(nome[i:])
                break
            miolo = nome[i + 1:fim]
            saida.append("&" if miolo == "" else _unb64_imap(miolo))
            i = fim + 1
        else:
            saida.append(nome[i])
            i += 1
    return "".join(saida)


def _quote(nome: str) -> str:
    return '"%s"' % encode_folder(nome).replace("\\", "\\\\").replace('"', '\\"')


# ------------------------------------------------------------------- conexão

@contextmanager
def connect(account: Dict[str, Any], password: Optional[str] = None):
    cfg = account["imap"]
    host, port = cfg["host"], int(cfg["port"])
    senha = password if password is not None else keychain.get_secret(account["address"])
    try:
        if cfg.get("ssl", True):
            conn = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context())
        else:
            conn = imaplib.IMAP4(host, port)
            if cfg.get("starttls"):
                conn.starttls(ssl.create_default_context())
    except (OSError, imaplib.IMAP4.error) as erro:
        raise MailError(T(f"não consegui falar com {host}:{port} — {erro}",
                          f"could not reach {host}:{port} — {erro}")) from erro
    try:
        conn.login(account.get("username") or account["address"], senha)
    except imaplib.IMAP4.error as erro:
        detalhe = erro.args[0].decode() if erro.args and isinstance(erro.args[0], bytes) else str(erro)
        conn.logout()
        raise MailError(T(f"o servidor recusou a senha de {account['address']}: {detalhe}",
                          f"the server refused the password for {account['address']}: {detalhe}")) from erro
    try:
        yield conn
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def _ok(resposta: Tuple[str, Any], oque: str) -> Any:
    status, dados = resposta
    if status != "OK":
        detalhe = dados[0].decode(errors="replace") if dados and isinstance(dados[0], bytes) else dados
        raise MailError(f"{oque}: {detalhe}")
    return dados


# -------------------------------------------------------------------- pastas

_LIST_RE = re.compile(rb'\((?P<flags>[^)]*)\)\s+(?P<sep>"[^"]*"|NIL)\s+(?P<nome>.*)')

# Nem todo servidor anuncia SPECIAL-USE; quando não anuncia, o nome entrega.
_NOMES_ESPECIAIS = {
    "sent": ("sent", "sent messages", "sent mail", "[gmail]/sent mail",
             "enviados", "e-mails enviados", "mensagens enviadas", "itens enviados"),
    "drafts": ("drafts", "[gmail]/drafts", "rascunhos"),
    "trash": ("trash", "deleted messages", "[gmail]/trash", "lixeira", "itens excluídos"),
    "archive": ("archive", "all mail", "[gmail]/all mail", "arquivo", "arquivar",
                "todos os e-mails"),
    "junk": ("junk", "spam", "[gmail]/spam", "lixo eletrônico", "lixo eletronico"),
}
_FLAG_ESPECIAL = {
    rb"\\Sent": "sent", rb"\\Drafts": "drafts", rb"\\Trash": "trash",
    rb"\\Archive": "archive", rb"\\Junk": "junk", rb"\\All": "archive",
}


def folders(conn) -> List[Dict[str, Any]]:
    dados = _ok(conn.list(), "LIST")
    saida: List[Dict[str, Any]] = []
    for linha in dados:
        if isinstance(linha, tuple):        # nome veio como literal
            linha = linha[0] + b'"' + linha[1] + b'"'
        if not isinstance(linha, bytes):
            continue
        casou = _LIST_RE.match(linha)
        if not casou:
            continue
        flags = casou.group("flags").decode(errors="replace")
        bruto = casou.group("nome").decode(errors="replace").strip()
        if bruto.startswith('"') and bruto.endswith('"'):
            bruto = bruto[1:-1]
        if "\\Noselect" in flags:
            continue
        papel = None
        for flag, nome in _FLAG_ESPECIAL.items():
            if re.search(flag, casou.group("flags")):
                papel = nome
                break
        nome_legivel = decode_folder(bruto)
        if papel is None:
            baixo = nome_legivel.lower()
            for nome, apelidos in _NOMES_ESPECIAIS.items():
                if baixo in apelidos:
                    papel = nome
                    break
        saida.append({"name": nome_legivel, "role": papel,
                      "inbox": nome_legivel.upper() == "INBOX"})
    return saida


def special_folder(conn, role: str) -> Optional[str]:
    """A pasta que faz esse papel nesta conta ('sent', 'trash', ...)."""
    for pasta in folders(conn):
        if pasta["role"] == role:
            return pasta["name"]
    return None


def select(conn, folder: str = "INBOX", readonly: bool = True) -> int:
    status, dados = conn.select(_quote(folder), readonly=readonly)
    if status != "OK":
        detalhe = dados[0].decode(errors="replace") if dados and isinstance(dados[0], bytes) else dados
        raise MailError(T(f"pasta '{folder}' não abriu: {detalhe}",
                          f"could not open folder '{folder}': {detalhe}"))
    try:
        return int(dados[0])
    except (TypeError, ValueError, IndexError):
        return 0


def unread_count(conn, folder: str = "INBOX") -> int:
    status, dados = conn.status(_quote(folder), "(UNSEEN)")
    if status != "OK" or not dados:
        return 0
    casou = re.search(rb"UNSEEN\s+(\d+)", dados[0])
    return int(casou.group(1)) if casou else 0


# --------------------------------------------------------------------- busca

def _criteria(text: Optional[str] = None, sender: Optional[str] = None,
              to: Optional[str] = None, subject: Optional[str] = None,
              since: Optional[str] = None, before: Optional[str] = None,
              unread: bool = False, flagged: bool = False) -> List[str]:
    crit: List[str] = []
    if unread:
        crit.append("UNSEEN")
    if flagged:
        crit.append("FLAGGED")
    for chave, valor in (("FROM", sender), ("TO", to), ("SUBJECT", subject), ("TEXT", text)):
        if valor:
            crit += [chave, '"%s"' % valor.replace('\\', '\\\\').replace('"', '\\"')]
    for chave, valor in (("SINCE", since), ("BEFORE", before)):
        if valor:
            crit += [chave, _imap_date(valor)]
    return crit or ["ALL"]


def _imap_date(valor: str) -> str:
    """Aceita '2026-08-01', '7d' (últimos 7 dias) e o formato do próprio IMAP."""
    valor = valor.strip()
    casou = re.fullmatch(r"(\d+)\s*d", valor, re.I)
    if casou:
        dia = datetime.date.today() - datetime.timedelta(days=int(casou.group(1)))
        return dia.strftime("%d-%b-%Y")
    try:
        return datetime.date.fromisoformat(valor).strftime("%d-%b-%Y")
    except ValueError:
        return valor


def search(conn, folder: str = "INBOX", limit: int = 25, **kwargs) -> List[int]:
    select(conn, folder, readonly=True)
    crit = _criteria(**kwargs)
    tem_acento = any(any(ord(c) > 127 for c in parte) for parte in crit)
    try:
        if tem_acento:
            args = [p.encode("utf-8") for p in crit]
            status, dados = conn.uid("SEARCH", "CHARSET", "UTF-8", *args)
        else:
            status, dados = conn.uid("SEARCH", None, *crit)
    except imaplib.IMAP4.error:
        # servidor sem CHARSET: tenta cru, é melhor que devolver erro
        status, dados = conn.uid("SEARCH", None, *[p.encode("utf-8", "replace").decode("latin-1")
                                                   for p in crit])
    if status != "OK":
        raise MailError(T("a busca falhou no servidor", "the search failed on the server"))
    uids = [int(x) for x in (dados[0] or b"").split()]
    uids.sort(reverse=True)          # mais novo primeiro, que é o que se quer ver
    return uids[:limit] if limit else uids


# ------------------------------------------------------------------- leitura

_ITEM_RE = re.compile(rb"UID\s+(\d+)")
_FLAGS_RE = re.compile(rb"FLAGS\s+\(([^)]*)\)")


def _decode_header(valor: Optional[str]) -> str:
    if not valor:
        return ""
    partes = []
    for texto, charset in email.header.decode_header(valor):
        if isinstance(texto, bytes):
            partes.append(texto.decode(charset or "utf-8", errors="replace"))
        else:
            partes.append(texto)
    return "".join(partes).strip()


def summaries(conn, uids: Iterable[int], folder: str = "INBOX") -> List[Dict[str, Any]]:
    uids = list(uids)
    if not uids:
        return []
    select(conn, folder, readonly=True)
    conjunto = ",".join(str(u) for u in uids)
    status, dados = conn.uid(
        "FETCH", conjunto,
        "(UID FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS "
        "(FROM TO CC SUBJECT DATE MESSAGE-ID)])")
    if status != "OK":
        raise MailError(T("não consegui ler os cabeçalhos", "could not read the headers"))
    por_uid: Dict[int, Dict[str, Any]] = {}
    for item in dados:
        if not isinstance(item, tuple):
            continue
        prefixo, corpo = item[0], item[1]
        casou = _ITEM_RE.search(prefixo)
        if not casou:
            continue
        uid = int(casou.group(1))
        flags = _FLAGS_RE.search(prefixo)
        flags_txt = flags.group(1).decode(errors="replace") if flags else ""
        tamanho = re.search(rb"RFC822\.SIZE\s+(\d+)", prefixo)
        cab = email.message_from_bytes(corpo)
        por_uid[uid] = {
            "uid": uid,
            "folder": folder,
            "from": _decode_header(cab.get("From")),
            "to": _decode_header(cab.get("To")),
            "cc": _decode_header(cab.get("Cc")),
            "subject": _decode_header(cab.get("Subject")),
            "date": _decode_header(cab.get("Date")),
            "message_id": (cab.get("Message-ID") or "").strip(),
            "unread": "\\Seen" not in flags_txt,
            "flagged": "\\Flagged" in flags_txt,
            "size": int(tamanho.group(1)) if tamanho else None,
        }
    return [por_uid[u] for u in uids if u in por_uid]


def _body_text(msg: Message) -> Tuple[str, str]:
    """Devolve (texto, html). Prefere text/plain; sem ele, entrega o HTML cru."""
    texto, html = "", ""
    if msg.is_multipart():
        for parte in msg.walk():
            if parte.get_content_maintype() == "multipart":
                continue
            if parte.get_filename():
                continue
            tipo = parte.get_content_type()
            try:
                conteudo = parte.get_payload(decode=True) or b""
            except Exception:
                continue
            charset = parte.get_content_charset() or "utf-8"
            decodificado = conteudo.decode(charset, errors="replace")
            if tipo == "text/plain" and not texto:
                texto = decodificado
            elif tipo == "text/html" and not html:
                html = decodificado
    else:
        conteudo = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        decodificado = conteudo.decode(charset, errors="replace")
        if msg.get_content_type() == "text/html":
            html = decodificado
        else:
            texto = decodificado
    return texto.strip(), html.strip()


def _strip_html(html: str) -> str:
    sem_script = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    sem_tag = re.sub(r"(?s)<[^>]+>", " ", sem_script)
    import html as _html
    return re.sub(r"[ \t]*\n\s*\n\s*", "\n\n", re.sub(r"[ \t]+", " ", _html.unescape(sem_tag))).strip()


def fetch(conn, uid: int, folder: str = "INBOX", mark_read: bool = False) -> Dict[str, Any]:
    select(conn, folder, readonly=not mark_read)
    parte = "BODY[]" if mark_read else "BODY.PEEK[]"
    status, dados = conn.uid("FETCH", str(uid), f"(UID FLAGS {parte})")
    if status != "OK" or not dados or not isinstance(dados[0], tuple):
        raise MailError(T(f"mensagem {uid} não existe em '{folder}'",
                          f"message {uid} does not exist in '{folder}'"))
    prefixo, bruto = dados[0][0], dados[0][1]
    msg = email.message_from_bytes(bruto)
    texto, html = _body_text(msg)
    anexos = []
    for p in msg.walk():
        nome = p.get_filename()
        if not nome:
            continue
        try:
            corpo = p.get_payload(decode=True) or b""
        except Exception:
            corpo = b""
        anexos.append({"filename": _decode_header(nome),
                       "content_type": p.get_content_type(),
                       "size": len(corpo)})
    flags = _FLAGS_RE.search(prefixo)
    flags_txt = flags.group(1).decode(errors="replace") if flags else ""
    return {
        "uid": uid,
        "folder": folder,
        "from": _decode_header(msg.get("From")),
        "to": _decode_header(msg.get("To")),
        "cc": _decode_header(msg.get("Cc")),
        "reply_to": _decode_header(msg.get("Reply-To")),
        "subject": _decode_header(msg.get("Subject")),
        "date": _decode_header(msg.get("Date")),
        "message_id": (msg.get("Message-ID") or "").strip(),
        "references": (msg.get("References") or "").strip(),
        "unread": "\\Seen" not in flags_txt,
        "flagged": "\\Flagged" in flags_txt,
        "body": texto or _strip_html(html),
        "body_is_html_stripped": not texto and bool(html),
        "html": html if not texto else "",
        "attachments": anexos,
        "raw_size": len(bruto),
    }


def fetch_attachment(conn, uid: int, filename: str, folder: str = "INBOX") -> Tuple[str, bytes]:
    select(conn, folder, readonly=True)
    status, dados = conn.uid("FETCH", str(uid), "(BODY.PEEK[])")
    if status != "OK" or not dados or not isinstance(dados[0], tuple):
        raise MailError(T(f"mensagem {uid} não existe em '{folder}'",
                          f"message {uid} does not exist in '{folder}'"))
    msg = email.message_from_bytes(dados[0][1])
    alvo = filename.lower()
    for p in msg.walk():
        nome = _decode_header(p.get_filename() or "")
        if nome and (nome.lower() == alvo or alvo in nome.lower()):
            return nome, (p.get_payload(decode=True) or b"")
    disponiveis = [_decode_header(p.get_filename() or "") for p in msg.walk() if p.get_filename()]
    raise MailError(T(f"anexo '{filename}' não está nessa mensagem (tem: {disponiveis})",
                      f"attachment '{filename}' is not in that message (has: {disponiveis})"))


# -------------------------------------------------------------------- escrita

def store_flags(conn, uid: int, folder: str, add: List[str] = None,
                remove: List[str] = None) -> None:
    select(conn, folder, readonly=False)
    if add:
        _ok(conn.uid("STORE", str(uid), "+FLAGS", "(%s)" % " ".join(add)), "STORE +FLAGS")
    if remove:
        _ok(conn.uid("STORE", str(uid), "-FLAGS", "(%s)" % " ".join(remove)), "STORE -FLAGS")


def move(conn, uid: int, folder: str, destino: str) -> None:
    """MOVE quando o servidor tem; senão COPY + \\Deleted, e UID EXPUNGE se der.

    O EXPUNGE cego é evitado de propósito: ele apagaria de vez qualquer outra
    mensagem já marcada na pasta, inclusive as que não são nossas.
    """
    select(conn, folder, readonly=False)
    tem = conn.capabilities
    if "MOVE" in tem:
        _ok(conn.uid("MOVE", str(uid), _quote(destino)), "MOVE")
        return
    _ok(conn.uid("COPY", str(uid), _quote(destino)), "COPY")
    _ok(conn.uid("STORE", str(uid), "+FLAGS", "(\\Deleted)"), "STORE \\Deleted")
    if "UIDPLUS" in tem:
        conn.uid("EXPUNGE", str(uid))


def append(conn, folder: str, bruto: bytes, flags: str = "") -> None:
    import time
    marca = "(%s)" % flags if flags else None
    # time.time(), não datetime.now(): o Time2Internaldate recusa datetime sem
    # fuso ("date_time must be aware") e derrubava o APPEND na pasta Enviados.
    _ok(conn.append(_quote(folder), marca, imaplib.Time2Internaldate(time.time()), bruto),
        f"APPEND {folder}")
