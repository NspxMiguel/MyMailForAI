"""Português e inglês para tudo que o CLI imprime.

O idioma do sistema decide o padrão, `MYMAILFORAI_LANG` força um dos dois, e
`mymailforai lang <pt|en>` salva a escolha na configuração.
"""

import locale
import os
from typing import Optional

_ESCOLHIDO: Optional[str] = None


def set_language(code: Optional[str]) -> None:
    global _ESCOLHIDO
    _ESCOLHIDO = code if code in ("pt", "en") else None


def language() -> str:
    forcado = os.environ.get("MYMAILFORAI_LANG")
    if forcado and forcado[:2].lower() in ("pt", "en"):
        return forcado[:2].lower()
    if _ESCOLHIDO:
        return _ESCOLHIDO
    for variavel in ("LC_ALL", "LC_MESSAGES", "LANG"):
        valor = os.environ.get(variavel)
        if valor:
            return "pt" if valor.lower().startswith("pt") else "en"
    try:
        atual = locale.getlocale()[0] or ""
    except ValueError:
        atual = ""
    return "pt" if atual.lower().startswith("pt") else "en"


def T(pt: str, en: str) -> str:
    """O texto no idioma corrente. Curto de propósito: aparece muito."""
    return pt if language() == "pt" else en
