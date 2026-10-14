# tg-max-bridge

Relays text between two people across Telegram and Max: what user 1 writes
to the bot on one messenger reaches user 2 on the other, and back.

One process runs both bots over long polling. Four accounts take part: user 1
and user 2 on each messenger. Messages cross messengers, never stay on one:

| From | To |
|---|---|
| user 1 on Telegram | user 2 on Max |
| user 1 on Max | user 2 on Telegram |
| user 2 on Telegram | user 1 on Max |
| user 2 on Max | user 1 on Telegram |

Version 0.1.0 relays text only; a message with other content tells the sender
so and relays its caption, if any.

## Requirements

- Python 3.11 or newer; no third-party packages.
- A Telegram bot token and a Max bot token.
- The root certificate of the Max platform host, as a PEM file, when it is
  not in the system trust store (see Configuration).

## Installation

    git clone https://github.com/haritos90/tg-max-bridge.git
    cd tg-max-bridge

Write the environment file (see Configuration), then start:

    set -a; . /etc/tg-max-bridge.env; set +a
    python3 -m tg_max_bridge

For a permanent service copy deploy/tg-max-bridge.service to
/etc/systemd/system/, adjust its paths, and enable it.

## Usage

The admin commands work from any account bound as user 1, on either
messenger:

| Command | Effect |
|---|---|
| `/status` | The four slots and the pending requests |
| `/approve <request> <1\|2>` | Bind the requesting account to a slot |
| `/deny <request>` | Ignore the requesting account |
| `/unbind <tg\|max> <1\|2>` | Clear a slot bound at runtime; configured slots stay |
| `/bots` | The usernames of the two bot accounts |
| `/help` | The command list |

Bindings and denials are persisted in the state file; pending requests live
in memory and are recreated by the next message from that account. A request
that arrives before the admin is bound on Telegram is shown to the admin on
binding. Any other text from a bound account is relayed. The pairing flow is
described under Configuration.

## Configuration

Environment variables, read once at start:

| Option | Default | Description |
|---|---|---|
| `TG_BOT_TOKEN` | required | Telegram bot token |
| `MAX_BOT_TOKEN` | required | Max bot token |
| `TG_ADMIN` | required | Telegram username or numeric id of user 1, the admin; `TG_ADMIN_ID` is accepted as an alias |
| `TG_USER_2` | unset | Telegram username or id of user 2; bound on the first message, no approval |
| `MAX_USER_1`, `MAX_USER_2` | unset | Max ids of the two users, when known; take precedence over the state file |
| `MAX_API_URL` | `https://platform-api2.max.ru` | Max platform API base URL |
| `MAX_CA_FILE` | unset | PEM file with the root certificate of the Max API host, added to the trust store |
| `STATE_FILE` | `$XDG_STATE_HOME/tg-max-bridge/state.json` | Bindings and denials; `~/.local/state` when `XDG_STATE_HOME` is unset |
| `LOG_LEVEL` | `INFO` | Python logging level |

The setup runs in this order:

1. The environment file names the admin. `TG_ADMIN` is the admin's Telegram
   username (set in the Telegram profile, 5 to 32 letters, digits and
   underscores, with or without the leading `@`) or the numeric Telegram id.
   An account without a username needs its id, which a bot such as
   `@userinfobot` reports.
2. The admin opens the Telegram bot and sends any message. A username is
   pinned to the account's numeric id on that first message and stored in
   the state file; from then on the id is authoritative, because a username
   can be changed or taken over while the id cannot. A pinned username binds
   no second account: a later account with the same username is treated as
   unknown.
3. Both Max accounts contact the Max bot: press Start or send any message.
   Each contact reaches the admin on Telegram as a numbered request with the
   account's name and id, and the admin answers from Telegram with
   `/approve <request> 1` for the admin's own Max account and
   `/approve <request> 2` for user 2. The same flow binds user 2 on
   Telegram, unless `TG_USER_2` is set.
4. Every other account is ignored. Before a messenger's two slots are bound,
   an unknown account gets a one-line reply and the admin gets the request to
   approve or deny; once both slots are bound, an unknown account gets no
   reply and no request is raised. A denied account stays ignored.

The Max platform host presents a certificate chain whose root is absent from
common trust stores; the platform's developer documentation names the root
certificate to install. Save it as a PEM file and set `MAX_CA_FILE`. Max is
reached at `platform-api2.max.ru` with the token in the `Authorization`
header, as the platform requires since 2026.

## Development

    python3 -m venv .venv && . .venv/bin/activate
    pip install -r requirements-dev.txt
    ruff check . && pytest -q

Tests run with fake messengers and no network. Contribution terms:
CONTRIBUTING.md. Releases are `v*` tags on main; the version is in
tg_max_bridge/__init__.py and pyproject.toml, with the changes in
CHANGELOG.md.

## License

MIT. See LICENSE.
