"""Senha de aplicativo: chaveiro do sistema, nunca em arquivo.

macOS usa o Keychain (`security`), Linux usa libsecret (`secret-tool`). Em
qualquer sistema, MYMAILFORAI_SECRET_<CONTA> tem prioridade — é o caminho para
CI e contêiner, onde não existe chaveiro.
"""

import os
import platform
import re
import shutil
import subprocess

SERVICE = "mymailforai"


class KeychainError(RuntimeError):
    pass


def env_var_name(account: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", account).strip("_").upper()
    return f"MYMAILFORAI_SECRET_{slug}"


def backend() -> str:
    if os.environ.get("MYMAILFORAI_KEYCHAIN") == "none":
        return "none"
    if platform.system() == "Darwin" and shutil.which("security"):
        return "macos"
    if shutil.which("secret-tool"):
        return "libsecret"
    return "none"


def set_secret(account: str, secret: str) -> str:
    kind = backend()
    if kind == "macos":
        # -U atualiza a entrada existente em vez de duplicar
        subprocess.run(
            ["security", "add-generic-password", "-U", "-s", SERVICE,
             "-a", account, "-w", secret],
            check=True, capture_output=True,
        )
        return "macos-keychain"
    if kind == "libsecret":
        subprocess.run(
            ["secret-tool", "store", "--label", f"{SERVICE}:{account}",
             "service", SERVICE, "account", account],
            input=secret.encode(), check=True, capture_output=True,
        )
        return "libsecret"
    raise KeychainError(
        "nenhum chaveiro disponível — exporte a senha em "
        f"{env_var_name(account)} antes de usar a conta"
    )


def get_secret(account: str) -> str:
    from_env = os.environ.get(env_var_name(account))
    if from_env:
        return from_env
    kind = backend()
    if kind == "macos":
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", SERVICE, "-a", account, "-w"],
            capture_output=True,
        )
        if proc.returncode == 0:
            return proc.stdout.decode().rstrip("\n")
    elif kind == "libsecret":
        proc = subprocess.run(
            ["secret-tool", "lookup", "service", SERVICE, "account", account],
            capture_output=True,
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout.decode().rstrip("\n")
    raise KeychainError(
        f"senha da conta '{account}' não encontrada — rode "
        f"'mymailforai login {account}' ou exporte {env_var_name(account)}"
    )


def has_secret(account: str) -> bool:
    try:
        get_secret(account)
        return True
    except KeychainError:
        return False


def delete_secret(account: str) -> None:
    kind = backend()
    if kind == "macos":
        subprocess.run(["security", "delete-generic-password", "-s", SERVICE, "-a", account],
                       capture_output=True)
    elif kind == "libsecret":
        subprocess.run(["secret-tool", "clear", "service", SERVICE, "account", account],
                       capture_output=True)
