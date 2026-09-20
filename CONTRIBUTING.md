# Contributing to SatsFlow

## Setup
1. Clone the repo
2. Create a venv: `python -m venv .venv && source .venv/bin/activate`
3. Install: `pip install -e ".[dev]"`
4. Copy env: `cp .env.example .env` and fill in values

## Workflow
- Branch off `main`: `git checkout -b feature/your-thing`
- Keep commits small and focused
- Run `pre-commit install` once — it runs gitleaks + ruff on every commit
- Run tests before pushing: `pytest`

## Security rules
- NEVER commit `.env`, private keys, seeds, or API tokens
- If gitleaks blocks your commit, fix the leak — don't bypass the hook
- Never log passwords, keys, or decrypted vault contents

## Code style
- Ruff handles formatting and linting
- Type hints everywhere
- Docstrings on public functions

## Commit messages
Prefix with the phase or area:
- `core: add Kraken price feed`
- `security: harden vault key wipe`
- `tests: cover tampered nonce case`
