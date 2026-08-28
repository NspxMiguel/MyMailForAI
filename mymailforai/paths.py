"""Onde o MyMailForAI guarda estado. Senha nunca mora aqui — vai no chaveiro."""

import os
from pathlib import Path

HOME = Path(os.environ.get("MYMAILFORAI_HOME") or (Path.home() / ".mymailforai"))
CONFIG_FILE = HOME / "config.json"
QUEUE_FILE = HOME / "queue.json"
HISTORY_FILE = HOME / "history.jsonl"
ATTACH_DIR = HOME / "attachments"


def ensure_home() -> Path:
    HOME.mkdir(parents=True, exist_ok=True)
    # a config guarda endereços e nomes de servidor: só o dono lê
    try:
        HOME.chmod(0o700)
    except OSError:
        pass
    return HOME


def ensure_attach_dir() -> Path:
    ensure_home()
    ATTACH_DIR.mkdir(parents=True, exist_ok=True)
    return ATTACH_DIR
