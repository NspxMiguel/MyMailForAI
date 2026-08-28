"""A linha de comando — e a única porta que o app da barra de menus usa."""

import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__, accounts as acc, actions, approvals, imapc, keychain, providers
from .i18n import T, language, set_language
from .paths import HOME


# ------------------------------------------------------------------- saída

def _out(payload: Any, as_json: bool, texto: Optional[str] = None) -> int:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    elif texto is not None:
        print(texto)
    return 0


def _fail(mensagem: str, as_json: bool = False, code: int = 1) -> int:
    if as_json:
        print(json.dumps({"error": mensagem}, ensure_ascii=False), file=sys.stderr)
    else:
        print(mensagem, file=sys.stderr)
    return code


def _modo_legivel(modo: str) -> str:
    return {"auto": T("automático", "automatic"),
            "ask": T("pedir permissão", "ask permission"),
            "read": T("somente leitura", "read-only")}.get(modo, modo)


# -------------------------------------------------------------------- login

def cmd_login(args) -> int:
    endereco = args.address
    if not endereco:
        if args.json:
            return _fail("login precisa do endereço", True)
        endereco = input(T("endereço de e-mail: ", "email address: ")).strip()
    endereco = endereco.strip()
    if "@" not in endereco:
        return _fail(T(f"'{endereco}' não parece um e-mail", f"'{endereco}' is not an email"), args.json)

    try:
        conta = acc.build(endereco, provider=args.provider, username=args.username,
                          display_name=args.name, imap_host=args.imap_host,
                          imap_port=args.imap_port, smtp_host=args.smtp_host,
                          smtp_port=args.smtp_port, no_tls=args.no_tls)
    except acc.AccountError as erro:
        return _fail(str(erro), args.json)

    preset = providers.PROVIDERS[conta["provider"]]
    if args.detect:
        return _out({"address": endereco, "provider": conta["provider"],
                     "label": preset["label"], "password_url": preset.get("password_url", ""),
                     "password_hint": preset["password_hint"],
                     "username_hint": preset["username_hint"],
                     "username": conta["username"],
                     "imap": conta["imap"], "smtp": conta["smtp"]}, args.json,
                    f"{preset['label']} — {preset.get('password_url', '')}")
    if not args.json:
        print(T(f"Provedor: {preset['label']}", f"Provider: {preset['label']}"))
        print(f"  IMAP  {conta['imap']['host']}:{conta['imap']['port']}")
        print(f"  SMTP  {conta['smtp']['host']}:{conta['smtp']['port']}")
        print(T(f"  usuário: {preset['username_hint']}", f"  username: {preset['username_hint']}"))

    senha = ""
    if args.password_stdin:
        senha = sys.stdin.readline().rstrip("\n")
    else:
        url = preset.get("password_url")
        if url and not args.no_open:
            print(T(f"\nAbrindo {url}", f"\nOpening {url}"))
            print(T(f"  {preset['password_hint']}", f"  {preset['password_hint']}"))
            print(T("  Crie a senha lá, copie, e cole aqui embaixo.",
                    "  Create the password there, copy it, and paste it below."))
            try:
                webbrowser.open(url)
            except Exception:
                pass
        senha = getpass.getpass(T("\nsenha de aplicativo (não aparece na tela): ",
                                  "\napp password (hidden): "))
    senha = senha.strip().replace(" ", "")   # o Google mostra a senha em 4 blocos
    if not senha:
        return _fail(T("senha vazia — nada foi salvo", "empty password — nothing saved"), args.json)

    if not args.no_verify:
        try:
            prova = actions.verify_credentials(conta, senha)
        except (imapc.MailError, actions.ActionError) as erro:
            return _fail(str(erro), args.json)
    else:
        prova = {}

    try:
        onde = keychain.set_secret(endereco, senha)
    except keychain.KeychainError as erro:
        return _fail(str(erro), args.json)
    acc.add(conta, make_default=args.default or not acc.names())

    payload = {"address": endereco, "provider": conta["provider"], "keychain": onde,
               "mode": conta["mode"], "verified": not args.no_verify, **prova}
    if args.json:
        return _out(payload, True)
    print(T(f"\n✓ {endereco} conectado. Senha no {onde}, nunca em arquivo.",
            f"\n✓ {endereco} connected. Password in {onde}, never in a file."))
    if prova:
        print(T(f"  {prova['folders']} pastas, {prova['unread']} não lidos na entrada.",
                f"  {prova['folders']} folders, {prova['unread']} unread in the inbox."))
    print(T(f"  Modo: {_modo_legivel(conta['mode'])} — troque na barra de menus.",
            f"  Mode: {_modo_legivel(conta['mode'])} — change it in the menu bar."))
    return 0


def cmd_logout(args) -> int:
    if args.all:
        enderecos = acc.names()
    elif args.address:
        enderecos = [args.address]
    else:
        cfg = acc.load()
        enderecos = [cfg["default_account"]] if cfg.get("default_account") else []
    if not enderecos:
        return _fail(T("nenhuma conta conectada", "no account connected"), args.json)
    saiu = []
    for endereco in enderecos:
        keychain.delete_secret(endereco)
        approvals.forget_account(endereco)
        try:
            acc.remove(endereco)
        except acc.AccountError:
            pass
        approvals.log(endereco, "logout", "done", endereco)
        saiu.append(endereco)
    if args.json:
        return _out({"logged_out": saiu, "remaining": acc.names()}, True)
    for endereco in saiu:
        print(T(f"✓ saiu de {endereco} — senha apagada do chaveiro",
                f"✓ logged out of {endereco} — password deleted from the keychain"))
    return 0


def cmd_accounts(args) -> int:
    dados = actions.list_accounts(with_unread=args.unread)
    if args.json:
        return _out(dados, True)
    if not dados["accounts"]:
        print(T("nenhuma conta — rode: mymailforai login voce@gmail.com",
                "no account — run: mymailforai login you@gmail.com"))
        return 0
    for conta in dados["accounts"]:
        marca = "*" if conta["is_default"] else " "
        nao_lidos = "—" if conta["unread"] is None else conta["unread"]
        print(f"{marca} {conta['address']}  [{conta['provider']}]  "
              f"{_modo_legivel(conta['mode'])}  "
              + T(f"não lidos: {nao_lidos}  fila: {conta['pending']}  "
                  f"enviados 24h: {conta['sent_today']}/{conta['daily_limit']}",
                  f"unread: {nao_lidos}  queue: {conta['pending']}  "
                  f"sent 24h: {conta['sent_today']}/{conta['daily_limit']}"))
    return 0


def cmd_default(args) -> int:
    try:
        acc.set_default(args.address)
    except acc.AccountError as erro:
        return _fail(str(erro), args.json)
    return _out({"default": args.address}, args.json,
                T(f"conta padrão: {args.address}", f"default account: {args.address}"))


def cmd_mode(args) -> int:
    if not args.mode:
        dados = actions.list_accounts()
        if args.json:
            return _out({"accounts": [{"address": c["address"], "mode": c["mode"]}
                                      for c in dados["accounts"]]}, True)
        for conta in dados["accounts"]:
            print(f"{conta['address']}: {_modo_legivel(conta['mode'])}")
        return 0
    try:
        endereco = acc.set_mode(args.mode, args.account)
    except acc.AccountError as erro:
        return _fail(str(erro), args.json)
    if args.strict is not None:
        cfg = acc.load()
        cfg["accounts"][endereco]["ask_covers_mailbox"] = bool(args.strict)
        acc.save(cfg)
    approvals.log(endereco, "mode", "done", args.mode)
    return _out({"address": endereco, "mode": args.mode}, args.json,
                T(f"{endereco}: {_modo_legivel(args.mode)}",
                  f"{endereco}: {_modo_legivel(args.mode)}"))


# ------------------------------------------------------------------- leitura

def _linha(m: Dict[str, Any]) -> str:
    marca = "●" if m.get("unread") else " "
    estrela = "★" if m.get("flagged") else " "
    return (f"{marca}{estrela} {m['uid']:>7}  {(m.get('from') or '')[:34]:<34} "
            f"{(m.get('subject') or '')[:48]:<48} {(m.get('date') or '')[:16]}")


def cmd_folders(args) -> int:
    try:
        pastas = actions.list_folders(args.account)
    except Exception as erro:
        return _fail(str(erro), args.json)
    if args.json:
        return _out(pastas, True)
    for pasta in pastas:
        papel = f"  ({pasta['role']})" if pasta["role"] else ""
        print(f"  {pasta['name']}{papel}")
    return 0


def cmd_inbox(args) -> int:
    try:
        mensagens = actions.list_inbox(args.account, folder=args.folder,
                                       limit=args.number, unread=args.unread)
    except Exception as erro:
        return _fail(str(erro), args.json)
    if args.json:
        return _out(mensagens, True)
    if not mensagens:
        print(T("nada aqui", "nothing here"))
        return 0
    for m in mensagens:
        print(_linha(m))
    return 0


def cmd_search(args) -> int:
    try:
        mensagens = actions.search_email(
            args.account, folder=args.folder, limit=args.number,
            text=args.text, sender=args.sender, to=args.to, subject=args.subject,
            since=args.since, before=args.before, unread=args.unread, flagged=args.flagged)
    except Exception as erro:
        return _fail(str(erro), args.json)
    if args.json:
        return _out(mensagens, True)
    for m in mensagens:
        print(_linha(m))
    if not mensagens:
        print(T("nenhuma mensagem casou", "no message matched"))
    return 0


def cmd_read(args) -> int:
    try:
        m = actions.read_email(args.uid, args.account, folder=args.folder,
                               mark_read=args.mark_read)
    except Exception as erro:
        return _fail(str(erro), args.json)
    if args.json:
        return _out(m, True)
    print(f"De:      {m['from']}\nPara:    {m['to']}")
    if m.get("cc"):
        print(f"Cc:      {m['cc']}")
    print(f"Assunto: {m['subject']}\nData:    {m['date']}\nUID:     {m['uid']}")
    if m["attachments"]:
        nomes = ", ".join(f"{a['filename']} ({a['size']}B)" for a in m["attachments"])
        print(T(f"Anexos:  {nomes}", f"Attach:  {nomes}"))
    print("\n" + (m["body"] or T("(sem corpo de texto)", "(no text body)")))
    return 0


def cmd_attachment(args) -> int:
    try:
        r = actions.download_attachment(args.uid, args.filename, args.account,
                                        folder=args.folder, dest=args.out)
    except Exception as erro:
        return _fail(str(erro), args.json)
    return _out(r, args.json, T(f"salvo em {r['path']} ({r['bytes']} bytes)",
                                f"saved to {r['path']} ({r['bytes']} bytes)"))


# -------------------------------------------------------------------- escrita

def _resultado(r: Dict[str, Any], as_json: bool) -> int:
    return _out(r, as_json, r.get("message", json.dumps(r, ensure_ascii=False)))


def cmd_send(args) -> int:
    try:
        r = actions.send_email(args.to, args.subject, _corpo(args), args.account,
                               cc=args.cc, bcc=args.bcc, html=args.html,
                               attachments=args.attach, agent=args.agent)
    except Exception as erro:
        return _fail(str(erro), args.json)
    return _resultado(r, args.json)


def _corpo(args) -> str:
    if getattr(args, "body_file", None):
        return Path(os.path.expanduser(args.body_file)).read_text(encoding="utf-8")
    if args.body == "-":
        return sys.stdin.read()
    return args.body or ""


def cmd_reply(args) -> int:
    try:
        r = actions.reply_email(args.uid, _corpo(args), args.account, folder=args.folder,
                                reply_all=args.all, attachments=args.attach,
                                quote=not args.no_quote, agent=args.agent)
    except Exception as erro:
        return _fail(str(erro), args.json)
    return _resultado(r, args.json)


def cmd_forward(args) -> int:
    try:
        r = actions.forward_email(args.uid, args.to, args.account, folder=args.folder,
                                  body=_corpo(args), agent=args.agent)
    except Exception as erro:
        return _fail(str(erro), args.json)
    return _resultado(r, args.json)


def cmd_draft(args) -> int:
    try:
        r = actions.save_draft(args.to, args.subject, _corpo(args), args.account,
                               cc=args.cc, agent=args.agent)
    except Exception as erro:
        return _fail(str(erro), args.json)
    return _resultado(r, args.json)


def cmd_flag(args) -> int:
    leitura = True if args.read else (False if args.unread else None)
    estrela = True if args.star else (False if args.unstar else None)
    try:
        r = actions.mark_email(args.uid, args.account, folder=args.folder,
                               read=leitura, starred=estrela, agent=args.agent)
    except Exception as erro:
        return _fail(str(erro), args.json)
    return _resultado(r, args.json)


def cmd_move(args) -> int:
    try:
        r = actions.move_email(args.uid, args.to_folder, args.account,
                               folder=args.folder, agent=args.agent)
    except Exception as erro:
        return _fail(str(erro), args.json)
    return _resultado(r, args.json)


def cmd_archive(args) -> int:
    try:
        r = actions.archive_email(args.uid, args.account, folder=args.folder, agent=args.agent)
    except Exception as erro:
        return _fail(str(erro), args.json)
    return _resultado(r, args.json)


def cmd_trash(args) -> int:
    try:
        r = actions.trash_email(args.uid, args.account, folder=args.folder, agent=args.agent)
    except Exception as erro:
        return _fail(str(erro), args.json)
    return _resultado(r, args.json)


# ------------------------------------------------------------------ aprovação

def cmd_pending(args) -> int:
    itens = approvals.pending(args.account)
    if args.json:
        return _out(itens, True)
    if not itens:
        print(T("fila vazia", "queue empty"))
        return 0
    for item in itens:
        print(f"[{item['id']}] {item['account']}  {item['action']}  {item['summary']}")
        if item.get("detail"):
            for linha in item["detail"].splitlines()[:6]:
                print(f"        {linha}")
    return 0


def cmd_approve(args) -> int:
    try:
        r = actions.approve(args.id)
    except Exception as erro:
        return _fail(str(erro), args.json)
    return _resultado(r, args.json)


def cmd_reject(args) -> int:
    try:
        r = actions.reject(args.id, args.reason or "")
    except Exception as erro:
        return _fail(str(erro), args.json)
    return _resultado(r, args.json)


def cmd_history(args) -> int:
    registros = approvals.history(args.number, args.account)
    if args.json:
        return _out(registros, True)
    for r in registros:
        print(f"{r['at']}  {r['account']}  {r['action']:<8} {r['status']:<9} {r['summary']}")
    return 0


# ------------------------------------------------------------------ ambiente

def cli_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "bin" / "mymailforai")


def cmd_connect(args) -> int:
    binario = shutil.which("claude")
    if not binario:
        return _fail(T("o Claude Code não está instalado nesta máquina",
                       "Claude Code is not installed on this machine"), args.json)
    if args.status:
        listagem = subprocess.run([binario, "mcp", "list"], capture_output=True, timeout=60)
        ligado = "mymailforai" in listagem.stdout.decode(errors="replace")
        return _out({"connected": ligado}, args.json,
                    T("ligado", "connected") if ligado else T("não ligado", "not connected"))
    if args.remove:
        subprocess.run([binario, "mcp", "remove", "mymailforai", "-s", "user"],
                       capture_output=True, timeout=60)
        return _out({"connected": False}, args.json, T("desligado", "disconnected"))
    proc = subprocess.run(
        [binario, "mcp", "add", "mymailforai", "-s", "user", "--", cli_path(), "mcp"],
        capture_output=True, timeout=60)
    if proc.returncode != 0:
        return _fail(proc.stderr.decode(errors="replace").strip() or "falhou", args.json)
    return _out({"connected": True, "command": f"{cli_path()} mcp"}, args.json,
                T("ligado ao Claude Code — abra uma sessão nova para ele enxergar",
                  "connected to Claude Code — open a new session for it to show up"))


def cmd_doctor(args) -> int:
    relatorio: Dict[str, Any] = {"version": __version__, "home": str(HOME),
                                 "keychain": keychain.backend(), "accounts": []}
    for endereco in acc.names():
        conta = acc.get(endereco)
        item = {"address": endereco, "provider": conta["provider"], "mode": conta["mode"],
                "secret": keychain.has_secret(endereco), "imap": None, "smtp": None}
        try:
            with imapc.connect(conta) as conn:
                item["imap"] = f"ok, {len(imapc.folders(conn))} " + T("pastas", "folders")
        except Exception as erro:
            item["imap"] = f"erro: {erro}"
        relatorio["accounts"].append(item)
    binario = shutil.which("claude")
    if binario:
        listagem = subprocess.run([binario, "mcp", "list"], capture_output=True, timeout=60)
        relatorio["claude_code"] = "mymailforai" in listagem.stdout.decode(errors="replace")
    else:
        relatorio["claude_code"] = None
    if args.json:
        return _out(relatorio, True)
    print(f"MyMailForAI {__version__}")
    print(f"  {T('estado em', 'state in')} {HOME}")
    print(f"  {T('chaveiro', 'keychain')}: {relatorio['keychain']}")
    print(f"  Claude Code: {relatorio['claude_code']}")
    for item in relatorio["accounts"]:
        print(f"  {item['address']}  [{item['provider']}]  {_modo_legivel(item['mode'])}")
        print(f"     {T('senha no chaveiro', 'password in keychain')}: {item['secret']}")
        print(f"     IMAP: {item['imap']}")
    if not relatorio["accounts"]:
        print(T("  nenhuma conta conectada", "  no account connected"))
    return 0


def cmd_lang(args) -> int:
    if args.code:
        acc.set_lang(args.code)
        set_language(args.code)
    return _out({"lang": acc.get_lang() or language()}, args.json,
                f"{acc.get_lang() or language()}")


def cmd_uninstall(args) -> int:
    """Tira tudo: senha do chaveiro, estado, registro no Claude, app e symlink."""
    if not args.yes:
        return _fail(T("isto apaga contas, fila e o app. Confirme com --yes",
                       "this deletes accounts, queue and the app. Confirm with --yes"), args.json)
    removido: Dict[str, Any] = {"accounts": [], "state": False, "app": None, "cli": None}
    for endereco in acc.names():
        keychain.delete_secret(endereco)
        removido["accounts"].append(endereco)
    binario = shutil.which("claude")
    if binario:
        subprocess.run([binario, "mcp", "remove", "mymailforai", "-s", "user"],
                       capture_output=True, timeout=60)
    if HOME.exists():
        shutil.rmtree(HOME, ignore_errors=True)
        removido["state"] = True

    app = Path("/Applications/MyMailForAI.app")
    symlinks = [Path(p) / "mymailforai" for p in ("/opt/homebrew/bin", "/usr/local/bin",
                                                  str(Path.home() / ".local/bin"))]
    alvos = [str(p) for p in symlinks if p.exists() or p.is_symlink()]
    removido["cli"] = alvos
    removido["app"] = str(app) if app.exists() else None
    if not args.keep_app:
        # o próprio CLI mora dentro do app: apagar agora mataria este processo no
        # meio. Um shell solto faz a remoção um segundo depois que a gente sai.
        script = "sleep 1; " + "; ".join(
            [f"rm -rf '{app}'"] + [f"rm -f '{a}'" for a in alvos]
            + [f"pkill -f 'MyMailForAI.app' 2>/dev/null || true"])
        subprocess.Popen(["/bin/sh", "-c", script], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if args.json:
        return _out(removido, True)
    print(T("✓ desinstalado: senhas fora do chaveiro, estado apagado, app removido.",
            "✓ uninstalled: passwords out of the keychain, state deleted, app removed."))
    print(T("  Instalado pelo Homebrew? finalize com: brew uninstall --cask mymailforai",
            "  Installed via Homebrew? finish with: brew uninstall --cask mymailforai"))
    return 0


# --------------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mymailforai",
        description=T("A sua caixa de e-mail, com acesso total para o agente e o freio na barra de menus.",
                      "Your own mailbox, full access for the agent, and the brake in the menu bar."))
    p.add_argument("--version", action="version", version=f"mymailforai {__version__}")
    sub = p.add_subparsers(dest="cmd")

    def add(nome, funcao, ajuda, conta=True):
        s = sub.add_parser(nome, help=ajuda)
        s.set_defaults(func=funcao)
        s.add_argument("--json", action="store_true", help="saída em JSON / JSON output")
        if conta:
            s.add_argument("-a", "--account", help=T("qual conta", "which account"))
        return s

    s = add("login", cmd_login, T("conectar uma conta", "connect an account"), conta=False)
    s.add_argument("address", nargs="?")
    s.add_argument("--provider", choices=sorted(providers.PROVIDERS))
    s.add_argument("--username")
    s.add_argument("--name", help=T("nome que aparece no e-mail", "display name"))
    s.add_argument("--imap-host"); s.add_argument("--imap-port", type=int)
    s.add_argument("--smtp-host"); s.add_argument("--smtp-port", type=int)
    s.add_argument("--no-tls", action="store_true")
    s.add_argument("--password-stdin", action="store_true",
                   help=T("lê a senha da primeira linha do stdin", "read password from stdin"))
    s.add_argument("--no-open", action="store_true",
                   help=T("não abrir a página do provedor", "do not open the provider page"))
    s.add_argument("--no-verify", action="store_true")
    s.add_argument("--default", action="store_true")
    s.add_argument("--detect", action="store_true",
                   help=T("só descobrir o provedor e a página da senha",
                          "only detect the provider and the app-password page"))

    s = add("logout", cmd_logout, T("sair de uma conta", "log out of an account"), conta=False)
    s.add_argument("address", nargs="?")
    s.add_argument("--all", action="store_true")

    s = add("accounts", cmd_accounts, T("contas conectadas", "connected accounts"), conta=False)
    s.add_argument("--unread", action="store_true",
                   help=T("também consultar não lidos (mais lento)",
                          "also query unread counts (slower)"))

    s = add("default", cmd_default, T("trocar a conta padrão", "change the default account"), conta=False)
    s.add_argument("address")

    s = add("mode", cmd_mode, T("automático, pedir permissão, somente leitura",
                                "automatic, ask permission, read-only"))
    s.add_argument("mode", nargs="?", choices=list(acc.MODES))
    s.add_argument("--strict", dest="strict", action="store_true", default=None,
                   help=T("em 'ask', pedir também para mover/arquivar/lixeira",
                          "in 'ask', also ask for move/archive/trash"))
    s.add_argument("--no-strict", dest="strict", action="store_false")

    add("folders", cmd_folders, T("as pastas da conta", "the account folders"))

    s = add("inbox", cmd_inbox, T("as últimas da entrada", "latest in the inbox"))
    s.add_argument("-n", "--number", type=int, default=20)
    s.add_argument("-f", "--folder", default="INBOX")
    s.add_argument("--unread", action="store_true")

    s = add("search", cmd_search, T("procurar", "search"))
    s.add_argument("text", nargs="?")
    s.add_argument("--from", dest="sender"); s.add_argument("--to", dest="to")
    s.add_argument("--subject"); s.add_argument("--since"); s.add_argument("--before")
    s.add_argument("--unread", action="store_true"); s.add_argument("--flagged", action="store_true")
    s.add_argument("-f", "--folder", default="INBOX"); s.add_argument("-n", "--number", type=int, default=25)

    s = add("read", cmd_read, T("ler uma mensagem inteira", "read a whole message"))
    s.add_argument("uid", type=int); s.add_argument("-f", "--folder", default="INBOX")
    s.add_argument("--mark-read", action="store_true")

    s = add("attachment", cmd_attachment, T("baixar um anexo", "download an attachment"))
    s.add_argument("uid", type=int); s.add_argument("filename")
    s.add_argument("-f", "--folder", default="INBOX"); s.add_argument("-o", "--out")

    def escrita(s):
        s.add_argument("--agent", default="claude")
        return s

    s = escrita(add("send", cmd_send, T("enviar", "send")))
    s.add_argument("-t", "--to", required=True); s.add_argument("-s", "--subject", default="")
    s.add_argument("-b", "--body", default=""); s.add_argument("--body-file")
    s.add_argument("--cc"); s.add_argument("--bcc"); s.add_argument("--html")
    s.add_argument("--attach", action="append")

    s = escrita(add("reply", cmd_reply, T("responder", "reply")))
    s.add_argument("uid", type=int); s.add_argument("-b", "--body", default="")
    s.add_argument("--body-file"); s.add_argument("-f", "--folder", default="INBOX")
    s.add_argument("--all", action="store_true"); s.add_argument("--no-quote", action="store_true")
    s.add_argument("--attach", action="append")

    s = escrita(add("forward", cmd_forward, T("encaminhar", "forward")))
    s.add_argument("uid", type=int); s.add_argument("-t", "--to", required=True)
    s.add_argument("-b", "--body", default=""); s.add_argument("--body-file")
    s.add_argument("-f", "--folder", default="INBOX")

    s = escrita(add("draft", cmd_draft, T("salvar rascunho", "save a draft")))
    s.add_argument("-t", "--to", required=True); s.add_argument("-s", "--subject", default="")
    s.add_argument("-b", "--body", default=""); s.add_argument("--body-file"); s.add_argument("--cc")

    s = escrita(add("flag", cmd_flag, T("marcar lido/estrela", "mark read/starred")))
    s.add_argument("uid", type=int); s.add_argument("-f", "--folder", default="INBOX")
    s.add_argument("--read", action="store_true"); s.add_argument("--unread", action="store_true")
    s.add_argument("--star", action="store_true"); s.add_argument("--unstar", action="store_true")

    s = escrita(add("move", cmd_move, T("mover para outra pasta", "move to another folder")))
    s.add_argument("uid", type=int); s.add_argument("--to-folder", required=True)
    s.add_argument("-f", "--folder", default="INBOX")

    s = escrita(add("archive", cmd_archive, T("arquivar", "archive")))
    s.add_argument("uid", type=int); s.add_argument("-f", "--folder", default="INBOX")

    s = escrita(add("trash", cmd_trash, T("mandar para a lixeira", "move to trash")))
    s.add_argument("uid", type=int); s.add_argument("-f", "--folder", default="INBOX")

    add("pending", cmd_pending, T("o que espera confirmação", "what is waiting for confirmation"))

    s = add("approve", cmd_approve, T("confirmar um item da fila", "confirm a queued item"), conta=False)
    s.add_argument("id")
    s = add("reject", cmd_reject, T("recusar um item da fila", "reject a queued item"), conta=False)
    s.add_argument("id"); s.add_argument("--reason")

    s = add("history", cmd_history, T("o que já aconteceu", "what already happened"))
    s.add_argument("-n", "--number", type=int, default=30)

    s = add("connect", cmd_connect, T("ligar ao Claude Code", "connect to Claude Code"), conta=False)
    s.add_argument("--status", action="store_true"); s.add_argument("--remove", action="store_true")

    add("doctor", cmd_doctor, T("o que está de pé", "what is up"), conta=False)

    s = add("lang", cmd_lang, T("idioma", "language"), conta=False)
    s.add_argument("code", nargs="?", choices=["pt", "en"])

    s = add("uninstall", cmd_uninstall, T("apagar tudo", "delete everything"), conta=False)
    s.add_argument("--yes", action="store_true")
    s.add_argument("--keep-app", action="store_true")

    s = sub.add_parser("mcp", help=T("servidor MCP em stdio", "MCP server over stdio"))
    s.set_defaults(func=lambda a: __import__("mymailforai.mcp", fromlist=["serve"]).serve())

    return p


def main(argv: Optional[List[str]] = None) -> int:
    set_language(acc.get_lang())
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except (acc.AccountError, keychain.KeychainError) as erro:
        return _fail(str(erro), getattr(args, "json", False))
