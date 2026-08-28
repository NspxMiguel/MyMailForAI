#!/usr/bin/env python3
"""O caminho inteiro do MyMailForAI contra um servidor de verdade — o dublê.

O que este teste cobre é justamente o que não dá para testar com mock: o modo
segurando um envio, o botão soltando ele, o e-mail chegando do outro lado, e a
leitura continuando liberada em todos os modos.

    python3 tests/test_fluxo.py
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import fake_mail_server as dublê  # noqa: E402

CONTA = "teste@mymailforai.local"
SENHA = "senha-de-teste-123"
CLI = str(RAIZ / "bin" / "mymailforai")

falhas = []
passos = []


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def ok(nome: str, condicao: bool, detalhe: str = "") -> None:
    passos.append((nome, condicao))
    if condicao:
        print(f"  ok   {nome}")
    else:
        falhas.append(f"{nome} — {detalhe}")
        print(f"  FALHA {nome} — {detalhe}")


def rodar(*args, entrada=None, esperar_sucesso=True):
    proc = subprocess.run([sys.executable, CLI, *args], capture_output=True,
                          input=(entrada + "\n").encode() if entrada else None,
                          env=AMBIENTE, timeout=90)
    saida = proc.stdout.decode()
    if esperar_sucesso and proc.returncode != 0:
        raise AssertionError(f"{' '.join(args)} saiu {proc.returncode}: {proc.stderr.decode()}")
    return proc.returncode, saida, proc.stderr.decode()


def js(*args, **kwargs):
    _, saida, _ = rodar(*args, "--json", **kwargs)
    return json.loads(saida)


# ------------------------------------------------------------------ o dublê

SMTP_PORT, IMAP_PORT = porta_livre(), porta_livre()
dublê.CREDENCIAL["user"] = CONTA
dublê.CREDENCIAL["password"] = SENHA
dublê.semear("suporte@jogo.dev", CONTA, "Chamado 4471 — confirme o seu ID",
             "Ola,\n\nPara seguir com o reembolso, confirme o seu ID.\n\nSuporte")
dublê.semear("promo@loja.dev", CONTA, "MEGA PROMOCAO 70% OFF",
             "Aproveite nossa liquidacao.")

smtp = dublê.Servidor(("127.0.0.1", SMTP_PORT), dublê.SMTPHandler)
imap = dublê.Servidor(("127.0.0.1", IMAP_PORT), dublê.IMAPHandler)
threading.Thread(target=smtp.serve_forever, daemon=True).start()
threading.Thread(target=imap.serve_forever, daemon=True).start()

CASA = tempfile.mkdtemp(prefix="mymailforai-teste-")
AMBIENTE = dict(os.environ)
AMBIENTE.update({
    "MYMAILFORAI_HOME": CASA,
    "MYMAILFORAI_LANG": "en",
    # sem chaveiro: a senha vem por variável, que é o caminho de CI e contêiner
    "MYMAILFORAI_KEYCHAIN": "none",
    "MYMAILFORAI_SECRET_TESTE_MYMAILFORAI_LOCAL": SENHA,
})

print(f"dublê: SMTP {SMTP_PORT} · IMAP {IMAP_PORT} · casa {CASA}\n")

# ------------------------------------------------------------------- login

print("login")
# Sem chaveiro o `login` recusa gravar, e é isso que tem que acontecer: senha
# em arquivo seria pior que não conectar. O restante do teste usa a variável.
codigo, _, erro = rodar("login", CONTA, "--provider", "custom",
                        "--imap-host", "127.0.0.1", "--imap-port", str(IMAP_PORT),
                        "--smtp-host", "127.0.0.1", "--smtp-port", str(SMTP_PORT),
                        "--no-tls", "--password-stdin", "--json",
                        entrada=SENHA, esperar_sucesso=False)
ok("login valida IMAP e SMTP antes de gravar",
   "chaveiro" in erro or codigo == 0, f"código {codigo}: {erro[:200]}")

# monta a conta direto, que é o que o login faria se houvesse chaveiro
sys.path.insert(0, str(RAIZ))
os.environ["MYMAILFORAI_HOME"] = CASA
import importlib  # noqa: E402
from mymailforai import accounts as acc  # noqa: E402
importlib.reload(acc)
conta = acc.build(CONTA, provider="custom", imap_host="127.0.0.1", imap_port=IMAP_PORT,
                  smtp_host="127.0.0.1", smtp_port=SMTP_PORT, no_tls=True)
acc.add(conta)
ok("conta gravada sem senha no arquivo",
   SENHA not in Path(CASA, "config.json").read_text(), "a senha vazou para o config")

# ------------------------------------------------------------------ leitura

print("\nleitura")
pastas = js("folders")
nomes = {p["name"] for p in pastas}
ok("lista as pastas", {"INBOX", "Sent", "Drafts", "Trash"} <= nomes, str(nomes))
papeis = {p["role"] for p in pastas if p["role"]}
ok("reconhece o papel de cada pasta", {"sent", "drafts", "trash"} <= papeis, str(papeis))

entrada = js("inbox", "-n", "10")
ok("lê a entrada", len(entrada) == 2, f"{len(entrada)} mensagens")
ok("traz remetente e assunto",
   any("Chamado 4471" in (m["subject"] or "") for m in entrada), str(entrada[:1]))

achados = js("search", "--subject", "PROMOCAO")
ok("busca por assunto", len(achados) == 1, f"{len(achados)} resultados")
ok("busca por remetente", len(js("search", "--from", "suporte@jogo.dev")) == 1)
ok("busca por não lidos", len(js("search", "--unread")) == 2)

uid = entrada[-1]["uid"]
corpo = js("read", str(uid))
ok("lê o corpo inteiro", "reembolso" in corpo["body"], corpo["body"][:80])
ok("não marca como lida sem pedir", corpo["unread"] is True)

# --------------------------------------------------------------- os modos

print("\nmodos")
ok("nasce em 'pedir permissão'", js("mode")["accounts"][0]["mode"] == "ask")

fila = js("send", "-t", "gente@fora.dev", "-s", "assunto", "-b", "corpo")
ok("em 'ask' o envio entra na fila", fila["status"] == "queued", str(fila))
ok("nada saiu ainda", len(dublê.ENVIADAS) == 0, f"{len(dublê.ENVIADAS)} enviadas")
ok("a fila mostra para quem e o quê", "gente@fora.dev" in js("pending")[0]["summary"])

item = js("pending")[0]["id"]
enviado = js("approve", item)
ok("o botão solta o envio", enviado["status"] == "sent", str(enviado))
ok("o e-mail chegou no servidor", len(dublê.ENVIADAS) == 1, f"{len(dublê.ENVIADAS)}")
ok("o corpo chegou inteiro", "corpo" in dublê.ENVIADAS[-1])
ok("guardou cópia em Enviados", len(dublê.PASTAS["Sent"]["msgs"]) == 1)
ok("a fila esvaziou", js("pending") == [])

fila2 = js("send", "-t", "outro@fora.dev", "-s", "recusar", "-b", "x")
js("reject", fila2["id"], "--reason", "não")
ok("recusar não envia", len(dublê.ENVIADAS) == 1, f"{len(dublê.ENVIADAS)}")

rodar("mode", "read", "--json")
codigo, _, erro = rodar("send", "-t", "x@y.dev", "-s", "a", "-b", "b", "--json",
                        esperar_sucesso=False)
ok("'somente leitura' recusa escrever", codigo != 0 and "read-only" in erro, erro[:120])
ok("'somente leitura' continua lendo", len(js("inbox", "-n", "5")) == 2)

rodar("mode", "auto", "--json")
direto = js("send", "-t", "auto@fora.dev", "-s", "sai na hora", "-b", "z")
ok("'automático' envia sem perguntar", direto["status"] == "sent", str(direto))
ok("chegou no servidor", len(dublê.ENVIADAS) == 2, f"{len(dublê.ENVIADAS)}")

# ------------------------------------------------------------- caixa inteira

print("\nescrita na caixa")
resposta = js("reply", str(uid), "-b", "Segue o ID: 4471.")
ok("responde", resposta["status"] == "sent", str(resposta))
ok("a resposta cita o original", "reembolso" in dublê.ENVIADAS[-1])
ok("a resposta fica na mesma conversa", "In-Reply-To:" in dublê.ENVIADAS[-1])
ok("o assunto vira Re:", "Subject: Re: Chamado" in dublê.ENVIADAS[-1].replace("\r", ""))

js("flag", str(uid), "--read", "--star")
depois = js("read", str(uid))
ok("marca como lida", depois["unread"] is False)
ok("marca com estrela", depois["flagged"] is True)

js("draft", "-t", "rascunho@fora.dev", "-s", "pensando", "-b", "depois eu mando")
ok("salva rascunho sem enviar", len(dublê.PASTAS["Drafts"]["msgs"]) == 1)
ok("rascunho não virou envio", len(dublê.ENVIADAS) == 3, f"{len(dublê.ENVIADAS)}")

js("archive", str(uid))
ok("arquiva", len(dublê.PASTAS["Archive"]["msgs"]) == 1)
ok("saiu da entrada", len(js("inbox", "-n", "10")) == 1)

sobrou = js("inbox", "-n", "10")[0]["uid"]
js("trash", str(sobrou))
ok("manda para a lixeira", len(dublê.PASTAS["Trash"]["msgs"]) == 1)
ok("a entrada ficou vazia", js("inbox", "-n", "10") == [])

# ------------------------------------------------------------------ o teto

print("\nfreios")
cfg = json.loads(Path(CASA, "config.json").read_text())
cfg["accounts"][CONTA]["daily_limit"] = 3
Path(CASA, "config.json").write_text(json.dumps(cfg))
codigo, _, erro = rodar("send", "-t", "muitos@fora.dev", "-s", "a", "-b", "b", "--json",
                        esperar_sucesso=False)
ok("o teto diário vale mesmo em 'automático'", codigo != 0 and "cap" in erro, erro[:120])

# --------------------------------------------------------------------- MCP

print("\nMCP")
pedidos = "\n".join([
    json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
    json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
    json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": "list_inbox", "arguments": {"limit": 5}}}),
])
proc = subprocess.run([sys.executable, CLI, "mcp"], input=pedidos.encode(),
                      capture_output=True, env=AMBIENTE, timeout=90)
respostas = [json.loads(l) for l in proc.stdout.decode().splitlines() if l.strip()]
ok("o MCP responde o handshake", respostas[0]["result"]["serverInfo"]["name"] == "mymailforai")
nomes_mcp = {t["name"] for t in respostas[1]["result"]["tools"]}
ok("expõe as ferramentas de leitura e escrita",
   {"list_inbox", "read_email", "send_email", "trash_email"} <= nomes_mcp, str(nomes_mcp))
ok("não expõe apagar de vez",
   not any("delete" in n or "expunge" in n for n in nomes_mcp), str(nomes_mcp))
ok("uma chamada de ferramenta funciona", respostas[2]["result"]["isError"] is False,
   str(respostas[2])[:200])

# ------------------------------------------------------------------ logout

print("\nlogout")
js("logout", CONTA)
ok("a conta sai da lista", js("accounts")["accounts"] == [])

# ------------------------------------------------------------------- fecho

print()
if falhas:
    print(f"{len(falhas)} de {len(passos)} falharam:")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print(f"{len(passos)} passos, todos passaram.")
