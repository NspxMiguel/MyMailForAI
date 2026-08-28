"""O freio. Decide se uma ação sai agora, entra na fila, ou é recusada.

O modo é a permissão; o teto diário e o tamanho de anexo são segurança e valem
em qualquer modo — um deles impede a IA de mandar mil e-mails num laço, e
nenhum modo devia poder desligar isso.
"""

from typing import Any, Dict, Tuple

from . import approvals
from .i18n import T

# O que sai da máquina. É o que o modo `ask` sempre segura.
OUTBOUND = ("send", "reply", "forward")
# O que muda a caixa mas não sai da máquina, e é reversível.
MAILBOX = ("draft", "flag", "move", "archive", "trash")
WRITE = OUTBOUND + MAILBOX

RUN, QUEUE, REFUSE = "run", "queue", "refuse"


def decide(account: Dict[str, Any], action: str) -> Tuple[str, str]:
    """Devolve (decisão, motivo)."""
    if action not in WRITE:
        return RUN, ""                      # ler é sempre liberado: é o "acesso total"

    modo = account.get("mode", "ask")
    if modo == "read":
        return REFUSE, T(
            f"a conta {account['address']} está em modo somente leitura. "
            "Troque na barra de menus, ou rode: mymailforai mode ask",
            f"account {account['address']} is in read-only mode. "
            "Change it in the menu bar, or run: mymailforai mode ask")

    if action in OUTBOUND:
        teto = int(account.get("daily_limit", 50))
        se_ja = approvals.sent_today(account["address"])
        if teto and se_ja >= teto:
            return REFUSE, T(
                f"teto de {teto} mensagens em 24h já foi atingido ({se_ja}). "
                "Isto vale em qualquer modo — é o freio contra laço de IA.",
                f"the {teto}-message cap in 24h is already reached ({se_ja}). "
                "This holds in any mode — it is the brake against an AI loop.")

    if modo == "auto":
        return RUN, ""

    # modo ask: segura o que sai da máquina. Mover e marcar continuam correndo,
    # porque são reversíveis e uma fila cheia de "marcar como lido" esconderia
    # justamente o envio que precisa do olho dele.
    if action in OUTBOUND or account.get("ask_covers_mailbox"):
        return QUEUE, T("esperando você confirmar na barra de menus",
                        "waiting for you to confirm in the menu bar")
    return RUN, ""
