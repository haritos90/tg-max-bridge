# Changelog

Format: [Keep a Changelog](https://keepachangelog.com), versions follow
[Semantic Versioning](https://semver.org).

## [0.1.0] - 2026-10-14

### Added

- Text relay between user 1 and user 2 across Telegram and Max, in all four
  directions, over long polling on both APIs.
- Pairing by admin approval: `/status`, `/approve`, `/deny`, `/help`, and an
  optional Telegram username for user 2.
- Configuration from environment variables; bindings persisted in a JSON
  state file.
- systemd unit, CI and release workflows.
