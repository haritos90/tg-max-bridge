# Changelog

Format: [Keep a Changelog](https://keepachangelog.com), versions follow
[Semantic Versioning](https://semver.org).

## [0.1.7] - 2026-10-14

### Changed

- Links are relayed again, unchanged; previews stay disabled.

## [0.1.6] - 2026-10-14

### Changed

- An approval and `/status` show a connection table: one row per user, a
  checkbox per messenger.

## [0.1.5] - 2026-10-14

### Changed

- Links in relayed text are replaced by a marker and the sender is told;
  link previews are disabled on both messengers.

## [0.1.4] - 2026-10-14

### Changed

- A message to an unconnected seat says which bot the other person has to
  open and press Start.

## [0.1.3] - 2026-10-14

### Fixed

- Connections try IPv4 first with a short connect timeout, so a black-holed
  IPv6 route no longer stalls startup and polling.

## [0.1.2] - 2026-10-14

### Added

- Command menu on both bots: `start` for everyone, the admin commands in
  the admin's Telegram chat only. A typed `/start` on Max counts as Start.

## [0.1.1] - 2026-10-14

### Added

- `TG_ADMIN` takes a Telegram username as well as an id; the admin is bound
  on the first message, and requests reach the bound account.
- `/unbind` and `/bots` admin commands.
- Requests arrive on Telegram with buttons; `/approve <request>` without a
  seat number takes the one free seat.
- Pending requests are stored in the state file and re-sent to the admin
  at startup and on `/status`.

### Changed

- Replies and `/status` name the seats as the admin and the other person.
- A configured username binds a slot once; the stored id is authoritative.
- An unknown account on a messenger whose two slots are bound is ignored
  silently.

## [0.1.0] - 2026-10-14

### Added

- Text relay between user 1 and user 2 across Telegram and Max, in all four
  directions, over long polling on both APIs.
- Pairing by admin approval: `/status`, `/approve`, `/deny`, `/help`, and an
  optional Telegram username for user 2.
- Configuration from environment variables; bindings persisted in a JSON
  state file.
- systemd unit, CI and release workflows.
