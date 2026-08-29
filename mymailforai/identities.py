"""Os outros endereços da mesma caixa.

Uma conta do iCloud não é um endereço: é uma caixa que recebe por vários — o
Apple ID, os `@icloud.com`, o domínio próprio, os apelidos do Ocultar Meu E-mail.
Todos caem na MESMA pasta de entrada. Conectar cada um como "conta" mostraria a
mesma caixa N vezes; o que muda de verdade é **de qual endereço a mensagem sai**.

Detectar é olhar para a própria caixa, e há duas qualidades de prova:

- **provado**: o endereço aparece no `From:` de algo na pasta Enviados. O servidor
  já aceitou mandar por ele — não é palpite, é histórico;
- **recebe**: o endereço aparece no `To:`/`Delivered-To:` do que chegou. Prova que
  a caixa recebe por ele; não prova que o SMTP deixa enviar.
"""

import collections
import email as _email
import email.utils
from typing import Any, Dict, List

from . import imapc

# Endereço de relay do "Entrar com a Apple": recebe, mas o SMTP nunca deixa
# enviar por ele. Oferecer viraria erro na hora do envio.
IGNORAR_DOMINIOS = ("privaterelay.appleid.com", "noreply.github.com")
DOMINIOS_APPLE = ("icloud.com", "me.com", "mac.com")


def dominios_da_conta(account: Dict[str, Any]) -> set:
    """Os domínios que podem ser dele: o do endereço, o do usuário, e os da Apple."""
    dominios = {account["address"].rsplit("@", 1)[-1].lower()}
    usuario = (account.get("username") or "").lower()
    if "@" in usuario:
        dominios.add(usuario.rsplit("@", 1)[-1])
    if account.get("provider") == "icloud":
        dominios.update(DOMINIOS_APPLE)
    return dominios


def _colher(dados, campos, nomes=None) -> collections.Counter:
    achados: collections.Counter = collections.Counter()
    for item in dados or []:
        if not isinstance(item, tuple):
            continue
        cab = _email.message_from_bytes(item[1])
        for campo in campos:
            for nome, endereco in email.utils.getaddresses(cab.get_all(campo) or []):
                if "@" not in endereco:
                    continue
                endereco = endereco.lower().strip()
                achados[endereco] += 1
                # o nome que ele já usou nesse endereço vale mais que um palpite
                if nomes is not None and nome.strip():
                    nomes.setdefault(endereco, nome.strip())
    return achados


def scan(account: Dict[str, Any], limite_entrada: int = 800) -> List[Dict[str, Any]]:
    """Varre a caixa e devolve os endereços dela, do mais usado para o menos."""
    dominios = dominios_da_conta(account)
    enviados: collections.Counter = collections.Counter()
    recebidos: collections.Counter = collections.Counter()
    nomes: Dict[str, str] = {}

    with imapc.connect(account) as conn:
        pasta_enviados = imapc.special_folder(conn, "sent")
        if pasta_enviados:
            total = imapc.select(conn, pasta_enviados, readonly=True)
            if total:
                _, dados = conn.uid("FETCH", "1:*", "(BODY.PEEK[HEADER.FIELDS (FROM)])")
                enviados = _colher(dados, ("From",), nomes)

        total = imapc.select(conn, "INBOX", readonly=True)
        if total:
            # só o pedaço recente: a caixa dele tem milhares, e o que interessa
            # é quais endereços ainda estão em uso
            uids = imapc.search(conn, folder="INBOX", limit=limite_entrada)
            if uids:
                conjunto = ",".join(str(u) for u in uids)
                _, dados = conn.uid(
                    "FETCH", conjunto,
                    "(BODY.PEEK[HEADER.FIELDS (TO CC DELIVERED-TO X-ORIGINAL-TO)])")
                recebidos = _colher(dados, ("To", "Cc", "Delivered-To", "X-Original-To"))

    def nosso(endereco: str) -> bool:
        dominio = endereco.rsplit("@", 1)[-1]
        return dominio in dominios and not endereco.endswith(IGNORAR_DOMINIOS)

    saida: Dict[str, Dict[str, Any]] = {}
    for endereco, vezes in enviados.items():
        if nosso(endereco):
            saida[endereco] = {"address": endereco, "proven": True, "name": nomes.get(endereco, ""),
                               "sent": vezes, "received": 0}
    for endereco, vezes in recebidos.items():
        if not nosso(endereco):
            continue
        if endereco in saida:
            saida[endereco]["received"] = vezes
        else:
            saida[endereco] = {"address": endereco, "proven": False, "name": "",
                               "sent": 0, "received": vezes}

    # o endereço com que ele conectou é sempre a primeira opção
    principal = account["address"].lower()
    saida.setdefault(principal, {"address": principal, "proven": False, "name": "",
                                 "sent": 0, "received": 0})
    lista = sorted(saida.values(),
                   key=lambda i: (i["address"] != principal, not i["proven"],
                                  -(i["sent"] * 10 + i["received"])))
    return lista
