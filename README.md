# SatsFlow

Self-hosted Bitcoin and Monero donation platform.
A GNOMEFINANCE product.

## Status
Phase 1 — scaffold.

## Design
- Non-custodial: 99% to creator, 1% to GNOMEFINANCE, per-tx on-chain.
- Self-hosted BTC and XMR backends (hybrid: public API in dev, own node in prod).
- Argon2id password hashing, AES-256-GCM local vault.
- Termux-native UI.

## Dev setup
```bash
cp .env.example .env
pip install -e ".[dev]"
pre-commit install
pytest
