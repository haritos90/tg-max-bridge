# tg-max-bridge

Relays text between two people across Telegram and Max: what one user writes
to the bot on one messenger reaches the other user on the other messenger, and back.

One process runs both bots over long polling. Four accounts take part: user 1
and user 2 on each messenger:

| From | To |
|---|---|
| user 1 on Telegram | user 2 on Max |
| user 1 on Max | user 2 on Telegram |
| user 2 on Telegram | user 1 on Max |
| user 2 on Max | user 1 on Telegram |

Supports text, pictures and voice messages.

The bridge is managed by the admin user in Telegram.

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
| `/status` | Connection table (a row per user, a checkbox per messenger); re-sends the waiting requests with their buttons |
| `/approve <request>` | Connect the requesting account to the one free seat on its messenger |
| `/approve <request> <1\|2>` | Connect it as user 1 (the admin) or user 2 (the other person) |
| `/deny <request>` | Ignore the requesting account |
| `/unbind <tg\|max> <1\|2>` | Disconnect a seat bound at runtime; configured seats stay |
| `/bots` | The usernames of the two bot accounts |
| `/help` | The command list |

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

## License

MIT. See LICENSE.
