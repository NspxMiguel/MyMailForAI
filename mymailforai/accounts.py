"""Contas configuradas — várias ao mesmo tempo, com uma padrão."""

import datetime
import json
from typing import Any, Dict, List, Optional

from . import providers
from .paths import CONFIG_FILE, ensure_home

MODES = ("auto", "ask", "read")
DEFAULT_MODE = "ask"
DEFAULT_DAILY_LIMIT = 50
DEFAULT_MAX_ATTACH_MB = 20


class AccountError(RuntimeError):
    pass


def _empty() -> Dict[str, Any]:
    return {"version": 1, "lang": None, "default_account": None, "accounts": {}}


def load() -> Dict[str, Any]:
    if not CONFIG_FILE.exists():
        return _empty()
    try:
        with CONFIG_FILE.open(encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError) as erro:
        raise AccountError(f"config ilegível em {CONFIG_FILE}: {erro}") from erro
    base = _empty()
    base.update(cfg)
    return base


def save(cfg: Dict[str, Any]) -> None:
    ensure_home()
    tmp = CONFIG_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    tmp.replace(CONFIG_FILE)
    try:
        CONFIG_FILE.chmod(0o600)
    except OSError:
        pass


def names() -> List[str]:
    return list(load().get("accounts", {}))


def get(address: Optional[str] = None) -> Dict[str, Any]:
    cfg = load()
    address = address or cfg.get("default_account")
    if not address:
        raise AccountError("nenhuma conta conectada — rode 'mymailforai login <email>'")
    contas = cfg.get("accounts", {})
    if address not in contas:
        # o endereço pode estar escrito com outra caixa: e-mail não diferencia
        for conhecido in contas:
            if conhecido.lower() == address.lower():
                address = conhecido
                break
        else:
            conhecidas = ", ".join(contas) or "nenhuma"
            raise AccountError(f"conta '{address}' não está conectada (conectadas: {conhecidas})")
    conta = dict(contas[address])
    conta.setdefault("address", address)
    conta.setdefault("mode", DEFAULT_MODE)
    conta.setdefault("daily_limit", DEFAULT_DAILY_LIMIT)
    conta.setdefault("max_attachment_mb", DEFAULT_MAX_ATTACH_MB)
    conta.setdefault("username", address)
    conta.setdefault("display_name", address.split("@")[0])
    return conta


def build(address: str, provider: Optional[str] = None, username: Optional[str] = None,
          display_name: Optional[str] = None, imap_host: Optional[str] = None,
          imap_port: Optional[int] = None, smtp_host: Optional[str] = None,
          smtp_port: Optional[int] = None, no_tls: bool = False) -> Dict[str, Any]:
    provider = provider or providers.guess(address)
    if provider == "custom" and not imap_host:
        # domínio próprio: quem recebe o e-mail do domínio é quem pede a senha
        provider = providers.guess_by_mx(address)
    preset = providers.PROVIDERS.get(provider)
    if preset is None:
        raise AccountError(f"provedor '{provider}' desconhecido")
    imap = dict(preset["imap"])
    smtp = dict(preset["smtp"])
    if imap_host:
        imap["host"] = imap_host
    if imap_port:
        imap["port"] = int(imap_port)
    if smtp_host:
        smtp["host"] = smtp_host
    if smtp_port:
        smtp["port"] = int(smtp_port)
    if no_tls:
        # servidor sem criptografia só faz sentido em teste, e é explícito
        # justamente para não virar padrão por descuido
        imap["ssl"] = False
        smtp["starttls"] = False
    if not imap["host"] or not smtp["host"]:
        raise AccountError(
            f"não sei os servidores de '{address}' — passe --imap-host e --smtp-host")
    return {
        "address": address,
        "display_name": display_name or address.split("@")[0],
        "provider": provider,
        "username": username or address,
        "imap": imap,
        "smtp": smtp,
        "mode": DEFAULT_MODE,
        "daily_limit": DEFAULT_DAILY_LIMIT,
        "max_attachment_mb": DEFAULT_MAX_ATTACH_MB,
        "added_at": datetime.datetime.now(datetime.timezone.utc)
                    .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def add(account: Dict[str, Any], make_default: bool = True) -> None:
    cfg = load()
    cfg.setdefault("accounts", {})[account["address"]] = account
    if make_default or not cfg.get("default_account"):
        cfg["default_account"] = account["address"]
    save(cfg)


def remove(address: str) -> None:
    cfg = load()
    contas = cfg.get("accounts", {})
    if address not in contas:
        raise AccountError(f"conta '{address}' não está conectada")
    del contas[address]
    if cfg.get("default_account") == address:
        # a próxima da lista vira padrão; sem lista, nenhuma
        cfg["default_account"] = next(iter(contas), None)
    save(cfg)


def set_default(address: str) -> None:
    cfg = load()
    if address not in cfg.get("accounts", {}):
        raise AccountError(f"conta '{address}' não está conectada")
    cfg["default_account"] = address
    save(cfg)


def set_mode(mode: str, address: Optional[str] = None) -> str:
    if mode not in MODES:
        raise AccountError(f"modo '{mode}' não existe — use {', '.join(MODES)}")
    cfg = load()
    address = address or cfg.get("default_account")
    if not address or address not in cfg.get("accounts", {}):
        raise AccountError("nenhuma conta conectada")
    cfg["accounts"][address]["mode"] = mode
    save(cfg)
    return address


def get_lang() -> Optional[str]:
    try:
        return load().get("lang")
    except AccountError:
        return None


def set_lang(code: Optional[str]) -> None:
    cfg = load()
    cfg["lang"] = code if code in ("pt", "en") else None
    save(cfg)
