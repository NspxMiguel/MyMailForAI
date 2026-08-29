# MyMailForAI

Your own mailbox, full access for your agent, and the brake in the menu bar.

Giving an AI agent a mailbox of its own is one problem. Giving it *yours* is a
different one, and the hard part is not access — it is the brake. MyMailForAI
connects the account you already use, hands the agent everything in it, and puts
the one control that matters where you can reach it without opening anything: a
menu bar item that holds every outgoing message until you press the button.

```bash
brew install --cask nspxmiguel/tap/mymailforai
mymailforai login you@gmail.com
```

That is the whole setup. `login` reads the domain, works out the provider (by MX
record when the domain is your own), opens the page where the app password is
created, checks IMAP **and** SMTP before storing anything, and puts the password
in the macOS Keychain. It never touches a file.

## What the agent gets

Full access, and full means full: folders, search on the server, whole message
bodies, attachments, send, reply in-thread, forward, drafts, read/starred flags,
move, archive and trash. Seventeen MCP tools, one command to wire them up:

```bash
mymailforai connect      # registers the MCP server with Claude Code
```

There is deliberately **no permanent-delete tool.** Trash means moving to the
Trash folder, which you can undo. An agent should not be holding an operation
with no way back.

## One mailbox, several addresses

An iCloud account is not an address — it is a mailbox that receives on several:
the Apple ID, the `@icloud.com` ones, your own domain, the Hide My Email
aliases. They all land in the same inbox, so connecting each as a separate
account would show you the same mail three times. What actually differs is
**which address the message goes out as**.

`login` scans the mailbox and tells you what it found, and there is a picker in
the panel:

```bash
mymailforai identities                       # what this mailbox answers to
mymailforai identities --send-as you@yourdomain.com --name "Your Name"
mymailforai send --from other@you.com -t a@b.com -s "..." -b "..."
```

Two grades of evidence, and the difference matters: an address in the `From:`
of something in your Sent folder is **proven** — the server has already accepted
sending as it. An address that only shows up in `To:`/`Delivered-To:` is known
to **receive**, which is not the same as being allowed to send. The list says
which is which instead of guessing.

Replies pick the identity on their own: a message that arrived for
`you@yourdomain.com` is answered from `you@yourdomain.com`, not from whichever
address you happened to log in with.

## What the agent sees

A mailbox that receives on several addresses is also, unavoidably, one IMAP
connection. Opening "the agent's mailbox" and opening **your personal mail** are
the same connection, so without a limit the very first `list_inbox` hands the
agent fifteen hundred messages that were never meant for it.

Every account is therefore created **scoped to the address you connected with**.
The agent sees what came to that address, and nothing else:

```bash
mymailforai scope                          # what it sees today
mymailforai scope --add other@you.com
mymailforai scope --all                    # the whole mailbox, when you decide
mymailforai scope --only agent@you.com     # close it again
```

The limit holds on both sides: the server-side search is filtered before results
exist, and reading by UID checks again — a UID can come from anywhere, including
a guess. The panel shows the current scope and says so in orange when the whole
mailbox is open.

## The brake

Every account has a mode, the same three a coding agent has:

| Mode | Reading | Sending, replying, forwarding |
| --- | --- | --- |
| **Automatic** | yes | goes out immediately |
| **Ask permission** (default) | yes | queues, and waits for your button |
| **Read-only** | yes | refused, with the reason |

Reading is never gated — that is the point of the product. What `ask` holds is
what leaves the machine. Moving and flagging keep running, because they are
reversible and a queue full of "mark as read" would bury the send that actually
needs your eye. Flip that with the checkbox in the panel if you want everything
held.

Two limits ignore the mode entirely, because they are safety rather than
permission: a daily send cap (50 by default), and an attachment size ceiling. No
mode can switch them off — they are what stops a loop from mailing a thousand
people while you are asleep.

## The menu bar item

There is no window. Clicking the icon gives you the queue with **Confirm send**
and **Reject** on each message, the mode switch per account, the unread and
daily-cap counters, buttons to connect another mailbox or log one out, the
language, and uninstall. The icon carries the number of things waiting, and a
notification fires when something new lands in the queue.

Multiple accounts run side by side, each with its own mode. Logging out deletes
that account's password from the Keychain and drops whatever it had queued.

## Providers

iCloud (including a custom domain), Gmail, Outlook, Yahoo, Fastmail, Zoho,
Migadu, or any IMAP/SMTP host with `--imap-host` and `--smtp-host`.

Why app passwords instead of OAuth: Gmail only hands the mail scopes to an
application that has been through Google's verification, and in an unverified
app the refresh token dies after seven days — "log in once" would become "log in
every week". An app password is revocable, tied to this machine, and does not
expire. iCloud does not offer OAuth to third parties at all.

## Privacy

The password lives in the macOS Keychain (libsecret on Linux), or in
`MYMAILFORAI_SECRET_<ACCOUNT>` where there is no keychain. Configuration,
queue and history sit in `~/.mymailforai/`, readable only by you. Mail goes
straight from your machine to your provider — there is no server of ours in the
path, and there is nothing to sign up for.

`~/.mymailforai/history.jsonl` is append-only: every action, approved, rejected
or refused, with a timestamp.

## From the terminal

Everything the panel does is a command, because the panel *is* these commands —
the app never speaks IMAP itself, so the two can never disagree.

```bash
mymailforai inbox -n 20                     # latest, without marking anything read
mymailforai search --from boss@work.com --since 7d
mymailforai read 19654 --mark-read
mymailforai send -t a@b.com -s "Subject" -b "Body"
mymailforai pending                          # what is waiting for you
mymailforai approve <id>   |   reject <id>
mymailforai mode ask                         # auto | ask | read
mymailforai accounts --unread
mymailforai logout you@gmail.com   |   logout --all
mymailforai doctor
```

Add `--json` to any of them.

## Install from source

```bash
git clone https://github.com/NspxMiguel/MyMailForAI.git
cd MyMailForAI
./install.sh          # links bin/mymailforai into ~/.local/bin
mymailforai login you@gmail.com
cd mac && ./build_app.sh && open MyMailForAI.app
```

Python 3.9+ standard library, nothing to `pip install`. macOS 13+ for the app;
the CLI and the MCP server run anywhere Python does.

## Tests

```bash
python3 tests/test_fluxo.py
```

An IMAP4rev1 and SMTP stand-in runs in-process and the CLI talks to it unchanged,
so the tests cover the path that mocks cannot: the mode holding a send, the
approval releasing it, and the message arriving on the other side.

## Language

Portuguese and English, in the CLI and in the app. The system language picks the
default, the panel switches it, `MYMAILFORAI_LANG=pt` forces it, and
`mymailforai lang pt` saves the choice for both.

## MyMailForAI or MailForAI?

[MailForAI](https://github.com/NspxMiguel/MailForAI) gives the agent a mailbox of
its own with a short leash: a separate address, a recipient allowlist, a daily
cap. Use it when the agent needs to talk to the outside world under a name that
is not yours.

MyMailForAI is the opposite trade. It is your mailbox, the agent reads all of it,
and the control is a mode you flip from the menu bar rather than a list of
addresses you maintain.

## Uninstall

```bash
brew uninstall --cask mymailforai
```

Or from the panel: the menu at the bottom right has **Uninstall**, which clears
the Keychain entries, deletes `~/.mymailforai`, unregisters the MCP server and
removes the app.

## License

MIT.
