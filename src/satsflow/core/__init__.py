"""SatsFlow core: pricing, Bitcoin, Monero, and fee logic.

Submodules:
    price       — Kraken USD price feed with 60s cache
    bitcoin     — BTC address generation + payment monitoring
    monero      — XMR address generation + payment monitoring
    bitcoin_backends/ — public API and self-hosted node backends
    monero_backends/  — remote, local, and mock node backends
"""
