#!/usr/bin/env python3
"""Servidor SMTP e IMAP de mentira, para testar o app inteiro sem conta real.

Existe porque a única parte que nunca dava para testar era a que mais importa:
o caminho em que tudo dá certo. Com um servidor de verdade do outro lado, o
teste cobre login, envio, leitura e resposta sem depender de provedor nenhum.

Fala o suficiente dos dois protocolos para o MailForAI funcionar — não é um
servidor de e-mail, é um dublê.

    python3 tests/fake_mail_server.py --smtp 2525 --imap 1143 \
        --user claude@teste.dev --password segredo123
"""

import argparse
import email
import email.message
import email.utils
import socketserver
import threading
from typing import Dict, List

CAIXA: List[Dict] = []       # mensagens que o "servidor" entrega ao cliente
ENVIADAS: List[str] = []     # o que o cliente mandou, cru
CREDENCIAL = {"user": "", "password": ""}


def semear(remetente: str, destinatario: str, assunto: str, corpo: str) -> None:
    """Põe uma mensagem na caixa, como se tivesse chegado."""
    mensagem = email.message.EmailMessage()
    mensagem["From"] = remetente
    mensagem["To"] = destinatario
    mensagem["Subject"] = assunto
    mensagem["Date"] = email.utils.formatdate(localtime=True)
    mensagem["Message-ID"] = email.utils.make_msgid(domain="teste.dev")
    mensagem.set_content(corpo)
    CAIXA.append({"uid": len(CAIXA) + 1, "raw": bytes(mensagem), "seen": False})


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
        self.responder("* OK [CAPABILITY IMAP4rev1 AUTH=PLAIN] dubl.teste.dev")
        autenticado = False
        while True:
            linha = self.rfile.readline()
            if not linha:
                return
            texto = linha.decode(errors="replace").strip()
            partes = texto.split(" ", 2)
            if len(partes) < 2:
                continue
            etiqueta, comando = partes[0], partes[1].upper()
            resto = partes[2] if len(partes) > 2 else ""

            if comando == "CAPABILITY":
                self.responder("* CAPABILITY IMAP4rev1 AUTH=PLAIN")
                self.responder(f"{etiqueta} OK CAPABILITY done")
            elif comando == "LOGIN":
                usuario, senha = self._par(resto)
                if usuario == CREDENCIAL["user"] and senha == CREDENCIAL["password"]:
                    autenticado = True
                    self.responder(f"{etiqueta} OK LOGIN done")
                else:
                    self.responder(f"{etiqueta} NO [AUTHENTICATIONFAILED] Authentication Failed")
            elif not autenticado:
                self.responder(f"{etiqueta} NO Not authenticated")
            elif comando in ("SELECT", "EXAMINE"):
                self.responder(f"* {len(CAIXA)} EXISTS")
                self.responder("* 0 RECENT")
                self.responder("* FLAGS (\\Seen)")
                self.responder(f"{etiqueta} OK [READ-WRITE] SELECT done")
            elif comando == "SEARCH":
                criterio = resto.upper()
                itens = [m for m in CAIXA if not m["seen"]] if "UNSEEN" in criterio else CAIXA
                self.responder("* SEARCH " + " ".join(str(m["uid"]) for m in itens))
                self.responder(f"{etiqueta} OK SEARCH done")
            elif comando == "FETCH":
                self._fetch(etiqueta, resto)
            elif comando == "STORE":
                uid = int(resto.split(" ", 1)[0])
                for item in CAIXA:
                    if item["uid"] == uid:
                        item["seen"] = True
                self.responder(f"{etiqueta} OK STORE done")
            elif comando == "LOGOUT":
                self.responder("* BYE")
                self.responder(f"{etiqueta} OK LOGOUT done")
                return
            elif comando == "CLOSE":
                self.responder(f"{etiqueta} OK CLOSE done")
            else:
                self.responder(f"{etiqueta} OK {comando} done")

    @staticmethod
    def _par(resto: str):
        pedacos = resto.replace('"', "").split(" ")
        return (pedacos[0], pedacos[1]) if len(pedacos) >= 2 else ("", "")

    def _fetch(self, etiqueta: str, resto: str) -> None:
        uid_texto, itens = resto.split(" ", 1)
        uid = int(uid_texto)
        mensagem = next((m for m in CAIXA if m["uid"] == uid), None)
        if mensagem is None:
            self.responder(f"{etiqueta} NO no such message")
            return
        flags = "\\Seen" if mensagem["seen"] else ""
        # o cliente pede o cabeçalho na listagem e a mensagem toda ao abrir
        if "HEADER" in itens.upper():
            corpo = mensagem["raw"].split(b"\r\n\r\n")[0] + b"\r\n\r\n"
            rotulo = "BODY[HEADER]"
        else:
            corpo = mensagem["raw"]
            rotulo = "BODY[]"
        self.wfile.write(
            f"* {uid} FETCH (FLAGS ({flags}) {rotulo} {{{len(corpo)}}}\r\n".encode())
        self.wfile.write(corpo)
        self.wfile.write(b")\r\n")
        self.wfile.flush()
        self.responder(f"{etiqueta} OK FETCH done")


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
