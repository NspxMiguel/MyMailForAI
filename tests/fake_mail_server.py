#!/usr/bin/env python3
"""Servidor SMTP e IMAP de mentira, para testar o app inteiro sem conta real.

Existe porque a única parte que nunca dava para testar era a que mais importa:
o caminho em que tudo dá certo. Com um servidor de verdade do outro lado, o
teste cobre login, envio, leitura e resposta sem depender de provedor nenhum.

Fala o suficiente dos dois protocolos para o MailForAI e o MyMailForAI
funcionarem — não é um servidor de e-mail, é um dublê.

    python3 tests/fake_mail_server.py --smtp 2525 --imap 1143 \
        --user claude@teste.dev --password segredo123
"""

import argparse
import datetime
import email
import email.message
import email.utils
import re
import socketserver
import threading
from typing import Dict, List, Optional, Set, Tuple

# pastas em memória; CAIXA continua sendo a INBOX, como no MailForAI
_MESES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_ORDEM_FLAGS = ("\\Seen", "\\Answered", "\\Flagged", "\\Deleted", "\\Draft")
_CAPACIDADES = "IMAP4rev1 AUTH=PLAIN UIDPLUS MOVE"


def _nova_pasta(especial: Optional[str] = None) -> Dict:
    return {"msgs": [], "uidnext": 1, "uidvalidity": 1, "especial": especial}


PASTAS: Dict[str, Dict] = {
    "INBOX": _nova_pasta(),
    "Sent": _nova_pasta("\\Sent"),
    "Drafts": _nova_pasta("\\Drafts"),
    "Archive": _nova_pasta("\\Archive"),
    "Trash": _nova_pasta("\\Trash"),
}
CAIXA: List[Dict] = PASTAS["INBOX"]["msgs"]   # mensagens que o "servidor" entrega ao cliente
ENVIADAS: List[str] = []                      # o que o cliente mandou, cru
CREDENCIAL = {"user": "", "password": ""}
TRAVA = threading.Lock()


def _crlf(bruto: bytes) -> bytes:
    return bruto.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def _fmt_internaldate(dt: datetime.datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    off = dt.strftime("%z") or "+0000"
    return ("%02d-%s-%04d %02d:%02d:%02d %s" % (
        dt.day, _MESES[dt.month - 1], dt.year,
        dt.hour, dt.minute, dt.second, off))


def _internaldate_de(mensagem: email.message.EmailMessage) -> str:
    bruto = mensagem.get("Date")
    dt = None
    if bruto:
        try:
            dt = email.utils.parsedate_to_datetime(bruto)
        except (TypeError, ValueError, IndexError):
            dt = None
    if dt is None:
        dt = datetime.datetime.now(datetime.timezone.utc)
    return _fmt_internaldate(dt)


def _montar(remetente: str, destinatario: str, assunto: str, corpo: str) -> email.message.EmailMessage:
    mensagem = email.message.EmailMessage()
    mensagem["From"] = remetente
    mensagem["To"] = destinatario
    mensagem["Subject"] = assunto
    mensagem["Date"] = email.utils.formatdate(localtime=True)
    mensagem["Message-ID"] = email.utils.make_msgid(domain="teste.dev")
    mensagem.set_content(corpo)
    return mensagem


def _norm_flag(flag: str) -> str:
    flag = flag.strip()
    mapa = {
        "\\seen": "\\Seen", "\\answered": "\\Answered",
        "\\flagged": "\\Flagged", "\\deleted": "\\Deleted", "\\draft": "\\Draft",
    }
    return mapa.get(flag.lower(), flag)


def _fmt_flags(flags: Set[str]) -> str:
    conhecidas = [f for f in _ORDEM_FLAGS if f in flags]
    extras = sorted(f for f in flags if f not in _ORDEM_FLAGS)
    return " ".join(conhecidas + extras)


def _tem_flag(msg: Dict, flag: str) -> bool:
    return _norm_flag(flag) in msg["flags"]


def _marcar_seen(msg: Dict) -> None:
    msg["flags"].add("\\Seen")
    msg["seen"] = True


def _achar_pasta(nome: str) -> Tuple[Optional[str], Optional[Dict]]:
    nome = _desquote(nome.strip())
    if not nome:
        return None, None
    for chave, pasta in PASTAS.items():
        if chave.lower() == nome.lower():
            return chave, pasta
    return None, None


def _garantir_pasta(nome: str) -> Dict:
    chave, pasta = _achar_pasta(nome)
    if pasta is not None:
        return pasta
    PASTAS[nome] = _nova_pasta()
    return PASTAS[nome]


def _desquote(nome: str) -> str:
    nome = nome.strip()
    if len(nome) >= 2 and nome[0] == '"' and nome[-1] == '"':
        return nome[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return nome


def _tokens(texto: str) -> List[str]:
    """Parte uma linha IMAP respeitando aspas e parênteses."""
    saida: List[str] = []
    i, n = 0, len(texto)
    while i < n:
        while i < n and texto[i] in " \t":
            i += 1
        if i >= n:
            break
        if texto[i] == '"':
            i += 1
            buf: List[str] = []
            while i < n:
                if texto[i] == "\\":
                    i += 1
                    if i < n:
                        buf.append(texto[i])
                        i += 1
                elif texto[i] == '"':
                    i += 1
                    break
                else:
                    buf.append(texto[i])
                    i += 1
            saida.append("".join(buf))
        elif texto[i] == "(":
            profundidade = 0
            inicio = i
            while i < n:
                if texto[i] == "(":
                    profundidade += 1
                elif texto[i] == ")":
                    profundidade -= 1
                    if profundidade == 0:
                        i += 1
                        break
                i += 1
            saida.append(texto[inicio:i])
        else:
            inicio = i
            while i < n and texto[i] not in " \t":
                i += 1
            saida.append(texto[inicio:i])
    return saida


def _flags_de(texto: str) -> List[str]:
    texto = texto.strip()
    if texto.startswith("(") and texto.endswith(")"):
        texto = texto[1:-1]
    return [_norm_flag(p) for p in texto.split() if p]


def _parse_imap_date(texto: str) -> Optional[datetime.date]:
    texto = texto.strip().strip('"')
    partes = texto.split("-")
    if len(partes) != 3:
        return None
    try:
        dia = int(partes[0])
        mes = _MESES.index(partes[1][:3].title()) + 1
        ano = int(partes[2])
        return datetime.date(ano, mes, dia)
    except (ValueError, IndexError):
        return None


def _data_msg(msg: Dict) -> datetime.date:
    try:
        return _parse_imap_date(msg["internaldate"].split(" ")[0]) or datetime.date.today()
    except (IndexError, TypeError):
        return datetime.date.today()


def _uids_do_conjunto(conjunto: str, msgs: List[Dict]) -> List[Dict]:
    """Aceita 1,3,5 e 1:* (e intervalos 1:5, *)."""
    if not msgs or not conjunto:
        return []
    por_uid = {m["uid"]: m for m in msgs}
    max_uid = max(por_uid)
    saida: List[Dict] = []
    vistos: Set[int] = set()
    for pedaco in conjunto.split(","):
        pedaco = pedaco.strip()
        if not pedaco:
            continue
        try:
            if ":" in pedaco:
                a, b = pedaco.split(":", 1)
                inicio = max_uid if a == "*" else int(a)
                fim = max_uid if b == "*" else int(b)
                if inicio > fim:
                    inicio, fim = fim, inicio
                for uid in range(inicio, fim + 1):
                    if uid in por_uid and uid not in vistos:
                        saida.append(por_uid[uid])
                        vistos.add(uid)
            else:
                uid = max_uid if pedaco == "*" else int(pedaco)
                if uid in por_uid and uid not in vistos:
                    saida.append(por_uid[uid])
                    vistos.add(uid)
        except ValueError:
            continue
    return saida


def _seqs_do_conjunto(conjunto: str, msgs: List[Dict]) -> List[Tuple[int, Dict]]:
    """Conjunto de números de sequência (1-based), devolve (seq, msg)."""
    n = len(msgs)
    if n == 0 or not conjunto:
        return []
    saida: List[Tuple[int, Dict]] = []
    vistos: Set[int] = set()
    for pedaco in conjunto.split(","):
        pedaco = pedaco.strip()
        if not pedaco:
            continue
        try:
            if ":" in pedaco:
                a, b = pedaco.split(":", 1)
                inicio = n if a == "*" else int(a)
                fim = n if b == "*" else int(b)
                if inicio > fim:
                    inicio, fim = fim, inicio
                for seq in range(max(1, inicio), min(n, fim) + 1):
                    if seq not in vistos:
                        saida.append((seq, msgs[seq - 1]))
                        vistos.add(seq)
            else:
                seq = n if pedaco == "*" else int(pedaco)
                if 1 <= seq <= n and seq not in vistos:
                    saida.append((seq, msgs[seq - 1]))
                    vistos.add(seq)
        except ValueError:
            continue
    return saida


def _cabecalho(raw: bytes, nome: str) -> str:
    try:
        return str(email.message_from_bytes(raw).get(nome, "") or "")
    except Exception:
        return ""


def _filtrar(msgs: List[Dict], resto: str) -> List[Dict]:
    tokens = _tokens(resto)
    exige_unseen = False
    exige_seen = False
    exige_flagged = False
    from_ = to = subject = text = None
    since = None
    i = 0
    while i < len(tokens):
        t = tokens[i].upper()
        if t == "CHARSET":
            i += 2
            continue
        if t in ("ALL", "AND", "UID"):
            i += 1
            continue
        if t == "UNSEEN":
            exige_unseen = True
            i += 1
            continue
        if t == "SEEN":
            exige_seen = True
            i += 1
            continue
        if t == "FLAGGED":
            exige_flagged = True
            i += 1
            continue
        if t in ("FROM", "TO", "SUBJECT", "TEXT", "SINCE"):
            i += 1
            valor = tokens[i] if i < len(tokens) else ""
            i += 1
            if t == "FROM":
                from_ = valor
            elif t == "TO":
                to = valor
            elif t == "SUBJECT":
                subject = valor
            elif t == "TEXT":
                text = valor
            elif t == "SINCE":
                since = _parse_imap_date(valor)
            continue
        i += 1

    def casa(msg: Dict) -> bool:
        if exige_unseen and _tem_flag(msg, "\\Seen"):
            return False
        if exige_seen and not _tem_flag(msg, "\\Seen"):
            return False
        if exige_flagged and not _tem_flag(msg, "\\Flagged"):
            return False
        if from_ is not None and from_.lower() not in _cabecalho(msg["raw"], "From").lower():
            return False
        if to is not None and to.lower() not in _cabecalho(msg["raw"], "To").lower():
            return False
        if subject is not None and subject.lower() not in _cabecalho(msg["raw"], "Subject").lower():
            return False
        if text is not None and text.lower() not in msg["raw"].decode(errors="replace").lower():
            return False
        if since is not None and _data_msg(msg) < since:
            return False
        return True

    return [m for m in msgs if casa(m)]


def semear(remetente: str, destinatario: str, assunto: str, corpo: str) -> None:
    """Põe uma mensagem na caixa, como se tivesse chegado."""
    semear_em("INBOX", remetente, destinatario, assunto, corpo)


def semear_em(pasta: str, remetente: str, destinatario: str, assunto: str, corpo: str) -> None:
    """Põe uma mensagem numa pasta qualquer, como se tivesse chegado lá."""
    mensagem = _montar(remetente, destinatario, assunto, corpo)
    item = {
        "uid": 0,
        "raw": _crlf(bytes(mensagem)),
        "flags": set(),
        "seen": False,
        "internaldate": _internaldate_de(mensagem),
    }
    with TRAVA:
        destino = _garantir_pasta(pasta)
        item["uid"] = destino["uidnext"]
        destino["uidnext"] += 1
        destino["msgs"].append(item)


# ---------------------------------------------------------------- SMTP


class SMTPHandler(socketserver.StreamRequestHandler):
    def responder(self, texto: str) -> None:
        self.wfile.write((texto + "\r\n").encode())
        self.wfile.flush()

    def handle(self) -> None:
        self.responder("220 dubl.teste.dev ESMTP")
        autenticado = False
        while True:
            linha = self.rfile.readline()
            if not linha:
                return
            comando = linha.decode(errors="replace").strip()
            alto = comando.upper()

            if alto.startswith("EHLO") or alto.startswith("HELO"):
                self.responder("250-dubl.teste.dev")
                self.responder("250-AUTH PLAIN LOGIN")
                self.responder("250 OK")
            elif alto.startswith("AUTH LOGIN"):
                import base64
                self.responder("334 VXNlcm5hbWU6")
                usuario = base64.b64decode(self.rfile.readline().strip()).decode()
                self.responder("334 UGFzc3dvcmQ6")
                senha = base64.b64decode(self.rfile.readline().strip()).decode()
                if usuario == CREDENCIAL["user"] and senha == CREDENCIAL["password"]:
                    autenticado = True
                    self.responder("235 2.7.0 Authentication successful")
                else:
                    self.responder("535 5.7.8 Error: authentication failed")
            elif alto.startswith("AUTH PLAIN"):
                import base64
                pedaco = comando.split(" ", 2)
                bruto = pedaco[2] if len(pedaco) > 2 else self.rfile.readline().decode().strip()
                partes = base64.b64decode(bruto).decode().split("\x00")
                if len(partes) == 3 and partes[1] == CREDENCIAL["user"] \
                        and partes[2] == CREDENCIAL["password"]:
                    autenticado = True
                    self.responder("235 2.7.0 Authentication successful")
                else:
                    self.responder("535 5.7.8 Error: authentication failed")
            elif alto.startswith("MAIL FROM") or alto.startswith("RCPT TO"):
                self.responder("250 OK" if autenticado else "530 5.7.0 Authentication required")
            elif alto == "DATA":
                if not autenticado:
                    self.responder("530 5.7.0 Authentication required")
                    continue
                self.responder("354 End data with <CR><LF>.<CR><LF>")
                corpo = []
                while True:
                    pedaco = self.rfile.readline()
                    if not pedaco or pedaco.strip() == b".":
                        break
                    corpo.append(pedaco.decode(errors="replace"))
                ENVIADAS.append("".join(corpo))
                self.responder("250 2.0.0 Ok: queued")
            elif alto == "QUIT":
                self.responder("221 Bye")
                return
            elif alto == "RSET":
                self.responder("250 OK")
            else:
                self.responder("250 OK")


# ---------------------------------------------------------------- IMAP


class IMAPHandler(socketserver.StreamRequestHandler):
    def responder(self, texto: str) -> None:
        self.wfile.write((texto + "\r\n").encode())
        self.wfile.flush()

    def handle(self) -> None:
        self.responder(f"* OK [CAPABILITY {_CAPACIDADES}] dubl.teste.dev")
        autenticado = False
        self.pasta_atual: Optional[str] = None
        self.somente_leitura = False
        while True:
            linha = self.rfile.readline()
            if not linha:
                return
            texto = linha.decode(errors="replace").strip()
            if not texto:
                continue
            partes = texto.split(" ", 2)
            if len(partes) < 2:
                continue
            etiqueta, comando = partes[0], partes[1].upper()
            resto = partes[2] if len(partes) > 2 else ""
            tamanho = _tamanho_literal(texto)

            if comando == "CAPABILITY":
                self.responder(f"* CAPABILITY {_CAPACIDADES}")
                self.responder(f"{etiqueta} OK CAPABILITY done")
            elif comando == "LOGIN":
                usuario, senha = self._par(resto)
                if usuario == CREDENCIAL["user"] and senha == CREDENCIAL["password"]:
                    autenticado = True
                    self.responder(f"* CAPABILITY {_CAPACIDADES}")
                    self.responder(f"{etiqueta} OK LOGIN done")
                else:
                    self.responder(f"{etiqueta} NO [AUTHENTICATIONFAILED] Authentication Failed")
            elif comando == "LOGOUT":
                self.responder("* BYE")
                self.responder(f"{etiqueta} OK LOGOUT done")
                return
            elif comando == "NOOP":
                self.responder(f"{etiqueta} OK NOOP done")
            elif not autenticado:
                self.responder(f"{etiqueta} NO Not authenticated")
            elif comando == "LIST" or comando == "LSUB":
                self._list(etiqueta, resto, comando)
            elif comando in ("SELECT", "EXAMINE"):
                self._select(etiqueta, resto, comando == "EXAMINE")
            elif comando == "STATUS":
                self._status(etiqueta, resto)
            elif comando == "APPEND":
                self._append(etiqueta, resto, tamanho)
            elif comando == "CLOSE":
                self.pasta_atual = None
                self.somente_leitura = False
                self.responder(f"{etiqueta} OK CLOSE done")
            elif comando == "UID":
                self._uid(etiqueta, resto)
            elif comando == "SEARCH":
                self._search(etiqueta, resto, por_uid=False)
            elif comando == "FETCH":
                self._fetch_cmd(etiqueta, resto, por_uid=False)
            elif comando == "STORE":
                self._store(etiqueta, resto, por_uid=False)
            elif comando == "COPY":
                self._copy_ou_move(etiqueta, resto, mover=False, por_uid=False)
            elif comando == "MOVE":
                self._copy_ou_move(etiqueta, resto, mover=True, por_uid=False)
            else:
                self.responder(f"{etiqueta} OK {comando} done")

    @staticmethod
    def _par(resto: str):
        pedacos = resto.replace('"', "").split(" ")
        return (pedacos[0], pedacos[1]) if len(pedacos) >= 2 else ("", "")

    def _msgs(self) -> List[Dict]:
        if not self.pasta_atual:
            return []
        with TRAVA:
            pasta = PASTAS.get(self.pasta_atual)
            return list(pasta["msgs"]) if pasta else []

    def _list(self, etiqueta: str, resto: str, comando: str) -> None:
        tokens = _tokens(resto)
        padrao = tokens[1] if len(tokens) > 1 else "*"
        with TRAVA:
            itens = list(PASTAS.items())
        for nome, pasta in itens:
            if padrao not in ("*", "%") and padrao.lower() not in (nome.lower(),):
                continue
            flags = ["\\HasNoChildren"]
            if pasta.get("especial"):
                flags.append(pasta["especial"])
            self.responder(f'* {comando} ({" ".join(flags)}) "/" "{nome}"')
        self.responder(f"{etiqueta} OK {comando} done")

    def _select(self, etiqueta: str, resto: str, examinar: bool) -> None:
        nome = _desquote(resto.split(" ")[0] if resto else "INBOX")
        with TRAVA:
            chave, pasta = _achar_pasta(nome)
            if pasta is None:
                self.pasta_atual = None
                self.responder(f"{etiqueta} NO mailbox does not exist")
                return
            msgs = list(pasta["msgs"])
            uidnext = pasta["uidnext"]
            uidvalidity = pasta["uidvalidity"]
        self.pasta_atual = chave
        self.somente_leitura = examinar
        n = len(msgs)
        unseen_seq = next((i + 1 for i, m in enumerate(msgs) if not _tem_flag(m, "\\Seen")), None)
        self.responder("* FLAGS (\\Answered \\Flagged \\Deleted \\Seen \\Draft)")
        self.responder("* OK [PERMANENTFLAGS (\\Answered \\Flagged \\Deleted \\Seen \\Draft \\*)] Flags permitted")
        self.responder(f"* {n} EXISTS")
        self.responder("* 0 RECENT")
        if unseen_seq is not None:
            self.responder(f"* OK [UNSEEN {unseen_seq}] First unseen")
        self.responder(f"* OK [UIDVALIDITY {uidvalidity}] UIDs valid")
        self.responder(f"* OK [UIDNEXT {uidnext}] Predicted next UID")
        modo = "READ-ONLY" if examinar else "READ-WRITE"
        verbo = "EXAMINE" if examinar else "SELECT"
        self.responder(f"{etiqueta} OK [{modo}] {verbo} done")

    def _status(self, etiqueta: str, resto: str) -> None:
        tokens = _tokens(resto)
        nome = tokens[0] if tokens else "INBOX"
        pedido = (tokens[1] if len(tokens) > 1 else "(MESSAGES UNSEEN)").upper()
        with TRAVA:
            chave, pasta = _achar_pasta(nome)
            if pasta is None:
                self.responder(f"{etiqueta} NO mailbox does not exist")
                return
            msgs = list(pasta["msgs"])
            nome_real = chave or nome
        n = len(msgs)
        unseen = sum(1 for m in msgs if not _tem_flag(m, "\\Seen"))
        pedacos = []
        if "MESSAGES" in pedido or pedido.strip("()") == "":
            pedacos.append(f"MESSAGES {n}")
        if "UNSEEN" in pedido:
            pedacos.append(f"UNSEEN {unseen}")
        if "UIDNEXT" in pedido:
            with TRAVA:
                pedacos.append(f"UIDNEXT {pasta['uidnext']}")
        if "UIDVALIDITY" in pedido:
            pedacos.append(f"UIDVALIDITY {pasta['uidvalidity']}")
        if not pedacos:
            pedacos = [f"MESSAGES {n}", f"UNSEEN {unseen}"]
        self.responder(f'* STATUS "{nome_real}" ({" ".join(pedacos)})')
        self.responder(f"{etiqueta} OK STATUS done")

    def _uid(self, etiqueta: str, resto: str) -> None:
        if not self.pasta_atual:
            self.responder(f"{etiqueta} NO [CLIENTBUG] select a mailbox first")
            return
        partes = resto.split(" ", 1)
        sub = partes[0].upper() if partes else ""
        miolo = partes[1] if len(partes) > 1 else ""
        if sub == "SEARCH":
            self._search(etiqueta, miolo, por_uid=True)
        elif sub == "FETCH":
            self._fetch_cmd(etiqueta, miolo, por_uid=True)
        elif sub == "STORE":
            self._store(etiqueta, miolo, por_uid=True)
        elif sub == "COPY":
            self._copy_ou_move(etiqueta, miolo, mover=False, por_uid=True)
        elif sub == "MOVE":
            self._copy_ou_move(etiqueta, miolo, mover=True, por_uid=True)
        elif sub == "EXPUNGE":
            self.responder(f"{etiqueta} OK UID EXPUNGE done")
        else:
            self.responder(f"{etiqueta} BAD unknown UID command")

    def _search(self, etiqueta: str, resto: str, por_uid: bool) -> None:
        msgs = self._msgs()
        casadas = _filtrar(msgs, resto)
        if por_uid:
            ids = [str(m["uid"]) for m in casadas]
        else:
            ids = [str(msgs.index(m) + 1) for m in casadas]
        self.responder("* SEARCH" + ((" " + " ".join(ids)) if ids else ""))
        self.responder(f"{etiqueta} OK SEARCH done")

    def _pares_conjunto(self, conjunto: str, por_uid: bool) -> List[Tuple[int, Dict]]:
        msgs = self._msgs()
        if por_uid:
            escolhidas = _uids_do_conjunto(conjunto, msgs)
            pares = []
            for m in escolhidas:
                try:
                    pares.append((msgs.index(m) + 1, m))
                except ValueError:
                    continue
            return pares
        return _seqs_do_conjunto(conjunto, msgs)

    def _fetch_cmd(self, etiqueta: str, resto: str, por_uid: bool) -> None:
        tokens = _tokens(resto)
        if not tokens:
            self.responder(f"{etiqueta} BAD FETCH needs a set")
            return
        conjunto, itens = tokens[0], " ".join(tokens[1:])
        for seq, msg in self._pares_conjunto(conjunto, por_uid):
            self._emitir_fetch(seq, msg, itens)
        self.responder(f"{etiqueta} OK FETCH done")

    def _emitir_fetch(self, seq: int, msg: Dict, itens: str) -> None:
        itens_u = itens.upper()
        peek = "BODY.PEEK[" in itens_u
        quer_header = "HEADER" in itens_u
        quer_body = ("BODY[" in itens_u) or peek
        quer_rfc822 = bool(re.search(r"(^|[\s(])RFC822([\s)]|$)", itens_u))
        quer_size = "RFC822.SIZE" in itens_u
        quer_flags = "FLAGS" in itens_u
        quer_date = "INTERNALDATE" in itens_u
        marcar = (quer_rfc822 or (quer_body and not peek and not quer_header)) \
            and not self.somente_leitura
        if marcar:
            with TRAVA:
                _marcar_seen(msg)

        partes = [f"UID {msg['uid']}"]
        if quer_flags or marcar or not (quer_body or quer_rfc822 or quer_header):
            partes.append(f"FLAGS ({_fmt_flags(msg['flags'])})")
        if quer_size:
            partes.append(f"RFC822.SIZE {len(msg['raw'])}")
        if quer_date:
            partes.append(f'INTERNALDATE "{msg["internaldate"]}"')

        corpo = None
        rotulo = None
        if quer_header:
            corpo = msg["raw"].split(b"\r\n\r\n")[0] + b"\r\n\r\n"
            # o imaplib só precisa do literal; o cliente casa FLAGS/UID no prefixo
            rotulo = "BODY[HEADER.FIELDS (FROM TO CC SUBJECT DATE MESSAGE-ID)]"
            if "HEADER.FIELDS" not in itens_u:
                rotulo = "BODY[HEADER]"
        elif quer_rfc822:
            corpo = msg["raw"]
            rotulo = "RFC822"
        elif quer_body:
            corpo = msg["raw"]
            rotulo = "BODY[]"

        if corpo is None:
            self.responder(f"* {seq} FETCH ({' '.join(partes)})")
            return
        partes.append(f"{rotulo} {{{len(corpo)}}}")
        self.wfile.write(f"* {seq} FETCH ({' '.join(partes)}\r\n".encode())
        self.wfile.write(corpo)
        self.wfile.write(b")\r\n")
        self.wfile.flush()

    def _store(self, etiqueta: str, resto: str, por_uid: bool) -> None:
        tokens = _tokens(resto)
        if len(tokens) < 2:
            self.responder(f"{etiqueta} BAD STORE needs flags")
            return
        conjunto, op = tokens[0], tokens[1].upper()
        flags = _flags_de(tokens[2] if len(tokens) > 2 else "")
        somar = op.startswith("+FLAGS")
        tirar = op.startswith("-FLAGS")
        silencioso = "SILENT" in op
        for seq, msg in self._pares_conjunto(conjunto, por_uid):
            with TRAVA:
                if tirar:
                    for f in flags:
                        msg["flags"].discard(f)
                elif somar:
                    for f in flags:
                        msg["flags"].add(f)
                else:
                    msg["flags"] = set(flags)
                msg["seen"] = "\\Seen" in msg["flags"]
            if not silencioso:
                self.responder(
                    f"* {seq} FETCH (UID {msg['uid']} FLAGS ({_fmt_flags(msg['flags'])}))")
        self.responder(f"{etiqueta} OK STORE done")

    def _copy_ou_move(self, etiqueta: str, resto: str, mover: bool, por_uid: bool) -> None:
        tokens = _tokens(resto)
        if len(tokens) < 2:
            self.responder(f"{etiqueta} BAD {'MOVE' if mover else 'COPY'} needs mailbox")
            return
        conjunto, destino_nome = tokens[0], tokens[1]
        with TRAVA:
            origem = PASTAS.get(self.pasta_atual or "")
            if origem is None:
                self.responder(f"{etiqueta} NO no mailbox selected")
                return
            msgs = list(origem["msgs"])
            chave_dest, dest = _achar_pasta(destino_nome)
            if dest is None:
                self.responder(f"{etiqueta} NO mailbox does not exist")
                return
            escolhidas = _uids_do_conjunto(conjunto, msgs) if por_uid \
                else [m for _, m in _seqs_do_conjunto(conjunto, msgs)]
            if not escolhidas:
                self.responder(f"{etiqueta} OK {'MOVE' if mover else 'COPY'} done")
                return
            src_uids, dest_uids, seqs = [], [], []
            for m in escolhidas:
                seqs.append(msgs.index(m) + 1)
                novo = {
                    "uid": dest["uidnext"],
                    "raw": m["raw"],
                    "flags": set(m["flags"]),
                    "seen": m.get("seen", False),
                    "internaldate": m["internaldate"],
                }
                dest["uidnext"] += 1
                dest["msgs"].append(novo)
                src_uids.append(m["uid"])
                dest_uids.append(novo["uid"])
            copyuid = f"{dest['uidvalidity']} {_faixa(src_uids)} {_faixa(dest_uids)}"
            if mover:
                # EXPUNGE de trás pra frente pra o número de sequência bater
                for m in reversed(escolhidas):
                    if m in origem["msgs"]:
                        origem["msgs"].remove(m)
        verbo = "MOVE" if mover else "COPY"
        if mover:
            self.responder(f"* OK [COPYUID {copyuid}]")
            for seq in sorted(seqs, reverse=True):
                self.responder(f"* {seq} EXPUNGE")
        else:
            self.responder(f"* OK [COPYUID {copyuid}]")
        self.responder(f"{etiqueta} OK [COPYUID {copyuid}] UID {verbo} done")

    def _append(self, etiqueta: str, resto: str, tamanho: Optional[int]) -> None:
        if tamanho is None:
            self.responder(f"{etiqueta} BAD APPEND needs a literal")
            return
        tokens = [t for t in _tokens(resto) if not re.fullmatch(r"\{\d+\}", t)]
        nome = tokens[0] if tokens else "INBOX"
        flags: Set[str] = set()
        data = None
        for tok in tokens[1:]:
            if tok.startswith("("):
                flags = set(_flags_de(tok))
            else:
                data = tok.strip('"')
        self.wfile.write(b"+\r\n")
        self.wfile.flush()
        bruto = self.rfile.read(tamanho)
        with TRAVA:
            chave, pasta = _achar_pasta(nome)
            if pasta is None:
                self.responder(f"{etiqueta} NO mailbox does not exist")
                return
            uid = pasta["uidnext"]
            pasta["uidnext"] += 1
            pasta["msgs"].append({
                "uid": uid,
                "raw": _crlf(bruto),
                "flags": set(flags),
                "seen": "\\Seen" in flags,
                "internaldate": data or _fmt_internaldate(
                    datetime.datetime.now(datetime.timezone.utc)),
            })
            uidvalidity = pasta["uidvalidity"]
        self.responder(f"{etiqueta} OK [APPENDUID {uidvalidity} {uid}] APPEND done")


def _tamanho_literal(texto: str) -> Optional[int]:
    casou = re.search(r"\{(\d+)\}\s*$", texto)
    return int(casou.group(1)) if casou else None


def _faixa(uids: List[int]) -> str:
    if not uids:
        return ""
    if len(uids) == 1:
        return str(uids[0])
    if uids == list(range(uids[0], uids[-1] + 1)):
        return f"{uids[0]}:{uids[-1]}"
    return ",".join(str(u) for u in uids)


class Servidor(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smtp", type=int, default=2525)
    parser.add_argument("--imap", type=int, default=1143)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--seed", action="store_true",
                        help="põe algumas mensagens na caixa")
    args = parser.parse_args()

    CREDENCIAL["user"] = args.user
    CREDENCIAL["password"] = args.password

    if args.seed:
        semear("suporte@jogo-exemplo.com", args.user,
               "Chamado 4471 — precisamos do seu ID",
               "Ola,\n\nPara seguir com o reembolso, confirme o seu ID de jogador.\n\nAbracos,\nSuporte")
        semear("promo@loja-exemplo.com", args.user, "MEGA PROMOCAO 70% OFF",
               "Aproveite nossa liquidacao. Clique aqui e compre agora!")

    smtp = Servidor(("127.0.0.1", args.smtp), SMTPHandler)
    imap = Servidor(("127.0.0.1", args.imap), IMAPHandler)
    threading.Thread(target=smtp.serve_forever, daemon=True).start()
    threading.Thread(target=imap.serve_forever, daemon=True).start()
    print(f"SMTP em 127.0.0.1:{args.smtp} · IMAP em 127.0.0.1:{args.imap} · "
          f"usuário {args.user} · {len(CAIXA)} mensagens", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
