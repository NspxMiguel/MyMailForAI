"""A fila: o que o agente quer fazer e ainda não foi confirmado."""

import datetime
import json
import secrets
from typing import Any, Dict, List, Optional

from .paths import HISTORY_FILE, QUEUE_FILE, ensure_home

STATUS = ("pending", "approved", "rejected", "failed")


def agora() -> str:
    return (datetime.datetime.now(datetime.timezone.utc)
            .replace(microsecond=0).isoformat().replace("+00:00", "Z"))


def _load() -> Dict[str, Any]:
    if not QUEUE_FILE.exists():
        return {"version": 1, "items": []}
    try:
        with QUEUE_FILE.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"version": 1, "items": []}


def _save(fila: Dict[str, Any]) -> None:
    ensure_home()
    tmp = QUEUE_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(fila, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    tmp.replace(QUEUE_FILE)
    try:
        QUEUE_FILE.chmod(0o600)
    except OSError:
        pass


def enqueue(account: str, action: str, summary: str, detail: str,
            payload: Dict[str, Any], agent: str = "claude",
            sender: Optional[str] = None) -> Dict[str, Any]:
    fila = _load()
    item = {
        "id": secrets.token_hex(3),
        "account": account,
        "action": action,
        "created_at": agora(),
        "agent": agent,
        # por qual endereço da caixa a mensagem sai — ele confirma olhando isto
        "from": sender or account,
        "summary": summary,
        "detail": detail,
        "payload": payload,
        "status": "pending",
        "result": None,
    }
    fila["items"].append(item)
    _save(fila)
    log(account, action, "queued", summary, item_id=item["id"])
    return item


def pending(account: Optional[str] = None) -> List[Dict[str, Any]]:
    itens = [i for i in _load()["items"] if i["status"] == "pending"]
    if account:
        itens = [i for i in itens if i["account"] == account]
    return itens


def get(item_id: str) -> Dict[str, Any]:
    for item in _load()["items"]:
        if item["id"] == item_id:
            return item
    raise KeyError(item_id)


def finish(item_id: str, status: str, result: Any = None) -> Dict[str, Any]:
    fila = _load()
    for item in fila["items"]:
        if item["id"] == item_id:
            item["status"] = status
            item["result"] = result
            item["closed_at"] = agora()
            _save(fila)
            return item
    raise KeyError(item_id)


def purge(before_days: int = 30) -> int:
    """Tira da fila o que já foi fechado há tempo. O histórico continua inteiro."""
    fila = _load()
    corte = (datetime.datetime.now(datetime.timezone.utc)
             - datetime.timedelta(days=before_days)).isoformat()
    antes = len(fila["items"])
    fila["items"] = [i for i in fila["items"]
                     if i["status"] == "pending" or i.get("closed_at", "9") > corte]
    _save(fila)
    return antes - len(fila["items"])


def forget_account(address: str) -> int:
    """Ao sair de uma conta, o que estava na fila dela sai junto."""
    fila = _load()
    antes = len(fila["items"])
    fila["items"] = [i for i in fila["items"] if i["account"] != address]
    _save(fila)
    return antes - len(fila["items"])


# ------------------------------------------------------------------ histórico

def log(account: str, action: str, status: str, summary: str,
        item_id: Optional[str] = None, detail: str = "") -> None:
    """Append-only: é a prova do que aconteceu, e ninguém reescreve."""
    ensure_home()
    linha = {"at": agora(), "account": account, "action": action,
             "status": status, "summary": summary, "id": item_id, "detail": detail}
    with HISTORY_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(linha, ensure_ascii=False) + "\n")
    try:
        HISTORY_FILE.chmod(0o600)
    except OSError:
        pass


def history(limit: int = 30, account: Optional[str] = None) -> List[Dict[str, Any]]:
    if not HISTORY_FILE.exists():
        return []
    linhas = []
    with HISTORY_FILE.open(encoding="utf-8") as fh:
        for linha in fh:
            linha = linha.strip()
            if not linha:
                continue
            try:
                registro = json.loads(linha)
            except ValueError:
                continue
            if account and registro.get("account") != account:
                continue
            linhas.append(registro)
    return linhas[-limit:][::-1] if limit else linhas[::-1]


OUTBOUND = ("send", "reply", "forward")


def sent_today(account: str) -> int:
    """Quantas mensagens saíram desta conta nas últimas 24h — o teto usa isto."""
    corte = (datetime.datetime.now(datetime.timezone.utc)
             - datetime.timedelta(hours=24)).isoformat().replace("+00:00", "Z")
    total = 0
    for registro in history(limit=0, account=account):
        if registro.get("action") in OUTBOUND and registro.get("status") == "sent" \
                and registro.get("at", "") >= corte:
            total += 1
    return total
