# Contributing to tg-max-bridge

Contributions are welcome. This guide covers how to prepare a change and the
terms under which it is submitted.

## Making a change

- Keep a change small and focused on a single purpose.
- Match the style of the surrounding code; a comment states the why in a
  few words.
- Add no runtime dependencies: the bridge runs on the standard library.
- When behavior or configuration changes, update README.md and CHANGELOG.md
  in the same change.
- The published tree names the participants user 1 and user 2 and carries no
  account id, token or bot name, in code, tests or documents.

## Before you open a pull request

    pip install -r requirements-dev.txt
    ruff check . && pytest -q

## Language

English only: code, comments, documentation, bot replies and commit messages.

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/):
`type(scope): imperative summary`. Types: `feat`, `fix`, `refactor`, `docs`,
`test`, `chore`, `perf`.

## Rights and licensing

By submitting a contribution, you agree that it is licensed under the terms in
[LICENSE](LICENSE): inbound contributions match the outbound license. No
copyright assignment and no contributor license agreement are required.

## Developer Certificate of Origin

Every commit in a pull request carries a Signed-off-by line certifying the
Developer Certificate of Origin (https://developercertificate.org): the right to
submit the work under the project license. Sign off automatically with

    git commit -s

A pull request whose commits lack a sign-off is not merged. The sign-off is
yours: it certifies your right to submit the work, and an assistant does not
make that certification for you.

## AI-assisted contributions

Using AI tools is welcome. You are responsible for what you submit: review and
understand every line, run the checks above, and be ready to answer review
questions about the change. Every rule in this guide applies to AI-written
code exactly as to hand-written code.
