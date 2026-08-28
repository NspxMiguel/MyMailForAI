"""Servidores e página de senha de aplicativo de cada provedor.

Por que senha de aplicativo e não OAuth: o Gmail só entrega os escopos de
leitura de e-mail a um app que passou pela verificação da Google, e num app
não verificado o refresh token morre em sete dias — "loga uma vez e cabum"
viraria "loga toda semana". A senha de aplicativo é revogável, presa a esta
máquina, e não expira. O iCloud, esse, nem oferece OAuth para terceiros.
"""

from .i18n import T

PROVIDERS = {
    "icloud": {
        "label": "iCloud / Apple Mail",
        "smtp": {"host": "smtp.mail.me.com", "port": 587, "starttls": True},
        "imap": {"host": "imap.mail.me.com", "port": 993, "ssl": True},
        # o iCloud autentica pelo Apple ID, não pelo alias de domínio próprio
        "username_hint": T("seu Apple ID completo (ex.: voce@icloud.com)",
                           "your full Apple ID (e.g. you@icloud.com)"),
        "password_url": "https://account.apple.com/account/manage",
        "password_hint": T("Entrar e Segurança > Senhas de aplicativo > +",
                           "Sign-In and Security > App-Specific Passwords > +"),
    },
    "gmail": {
        "label": "Gmail / Google Workspace",
        "smtp": {"host": "smtp.gmail.com", "port": 587, "starttls": True},
        "imap": {"host": "imap.gmail.com", "port": 993, "ssl": True},
        "username_hint": T("o endereço completo do Gmail", "the full Gmail address"),
        "password_url": "https://myaccount.google.com/apppasswords",
        "password_hint": T("exige verificação em duas etapas ligada na conta",
                           "requires 2-Step Verification enabled on the account"),
    },
    "outlook": {
        "label": "Outlook / Microsoft 365",
        "smtp": {"host": "smtp-mail.outlook.com", "port": 587, "starttls": True},
        "imap": {"host": "outlook.office365.com", "port": 993, "ssl": True},
        "username_hint": T("o endereço completo", "the full address"),
        "password_url": "https://account.live.com/proofs/AppPassword",
        "password_hint": T("só existe com verificação em duas etapas ligada",
                           "only exists with two-step verification on"),
    },
    "yahoo": {
        "label": "Yahoo Mail",
        "smtp": {"host": "smtp.mail.yahoo.com", "port": 587, "starttls": True},
        "imap": {"host": "imap.mail.yahoo.com", "port": 993, "ssl": True},
        "username_hint": T("o endereço completo", "the full address"),
        "password_url": "https://login.yahoo.com/account/security/app-passwords",
        "password_hint": T("Segurança da conta > Gerar senha de app",
                           "Account Security > Generate app password"),
    },
    "fastmail": {
        "label": "Fastmail",
        "smtp": {"host": "smtp.fastmail.com", "port": 587, "starttls": True},
        "imap": {"host": "imap.fastmail.com", "port": 993, "ssl": True},
        "username_hint": T("o endereço completo", "the full address"),
        "password_url": "https://app.fastmail.com/settings/security/apps",
        "password_hint": T("New app password, com acesso a Mail",
                           "New app password, with Mail access"),
    },
    "zoho": {
        "label": "Zoho Mail",
        "smtp": {"host": "smtp.zoho.com", "port": 587, "starttls": True},
        "imap": {"host": "imap.zoho.com", "port": 993, "ssl": True},
        "username_hint": T("o endereço completo", "the full address"),
        "password_url": "https://accounts.zoho.com/home#security/apppassword",
        "password_hint": T("Segurança > Senhas específicas de aplicativo",
                           "Security > App passwords"),
    },
    "migadu": {
        "label": "Migadu",
        "smtp": {"host": "smtp.migadu.com", "port": 587, "starttls": True},
        "imap": {"host": "imap.migadu.com", "port": 993, "ssl": True},
        "username_hint": T("o endereço completo da caixa", "the full mailbox address"),
        "password_url": "https://admin.migadu.com/",
        "password_hint": T("Mailboxes > a caixa > senha",
                           "Mailboxes > the mailbox > password"),
    },
    "custom": {
        "label": T("Outro servidor (host e porta na mão)",
                   "Another server (host and port by hand)"),
        "smtp": {"host": "", "port": 587, "starttls": True},
        "imap": {"host": "", "port": 993, "ssl": True},
        "username_hint": T("o usuário que o servidor espera",
                           "the username the server expects"),
        "password_url": "",
        "password_hint": T("a senha dessa caixa", "that mailbox's password"),
    },
}

_POR_DOMINIO = {
    "icloud.com": "icloud", "me.com": "icloud", "mac.com": "icloud",
    "gmail.com": "gmail", "googlemail.com": "gmail",
    "outlook.com": "outlook", "hotmail.com": "outlook", "live.com": "outlook",
    "msn.com": "outlook",
    "yahoo.com": "yahoo", "yahoo.com.br": "yahoo", "ymail.com": "yahoo",
    "fastmail.com": "fastmail", "fastmail.fm": "fastmail",
    "zoho.com": "zoho",
}


def guess(address: str) -> str:
    """Chuta o preset pelo domínio. Devolve 'custom' quando não conhece."""
    return _POR_DOMINIO.get(address.rsplit("@", 1)[-1].lower(), "custom")


def guess_by_mx(address: str) -> str:
    """Segunda tentativa, para domínio próprio: quem recebe o e-mail do domínio.

    `miguel@nspx.dev` não diz nada pelo nome, mas o MX aponta para o iCloud —
    e é o iCloud que vai pedir a senha. Só roda quando `dig` existe; sem ele,
    devolve 'custom' e o usuário informa o provedor.
    """
    import shutil
    import subprocess
    if not shutil.which("dig"):
        return "custom"
    domain = address.rsplit("@", 1)[-1].lower()
    try:
        saida = subprocess.run(["dig", "+short", "MX", domain],
                               capture_output=True, timeout=6).stdout.decode().lower()
    except (OSError, subprocess.SubprocessError):
        return "custom"
    for agulha, nome in (("icloud.com", "icloud"), ("apple.com", "icloud"),
                         ("google.com", "gmail"), ("googlemail.com", "gmail"),
                         ("outlook.com", "outlook"), ("microsoft.com", "outlook"),
                         ("messagingengine.com", "fastmail"),
                         ("zoho.com", "zoho"), ("migadu.com", "migadu"),
                         ("yahoodns.net", "yahoo")):
        if agulha in saida:
            return nome
    return "custom"
