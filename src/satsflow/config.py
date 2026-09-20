"""Central config. Every tunable lives here — nothing hardcoded elsewhere."""

import os
from pathlib import Path

# --- Fee ---
FEE_PERCENT = float(os.getenv("SATFLOW_FEE_PERCENT", "0.01"))
GNOME_BTC_ADDRESS = os.getenv("SATFLOW_GNOME_BTC_ADDRESS", "")
GNOME_XMR_ADDRESS = os.getenv("SATFLOW_GNOME_XMR_ADDRESS", "")

# --- Price feed ---
PRICE_SOURCE = os.getenv("SATFLOW_PRICE_SOURCE", "kraken")
PRICE_CACHE_TTL = int(os.getenv("SATFLOW_PRICE_CACHE_TTL", "60"))

# --- Bitcoin backend ---
BTC_BACKEND = os.getenv("SATFLOW_BTC_BACKEND", "public")   # "public" | "node"
BTC_NODE_RPC = os.getenv("SATFLOW_BTC_NODE_RPC", "")
ELECTRS_URL = os.getenv("SATFLOW_ELECTRS_URL", "")
BTC_XPUB = os.getenv("SATFLOW_BTC_XPUB", "")

# --- Monero backend ---
XMR_BACKEND = os.getenv("SATFLOW_XMR_BACKEND", "remote")   # "remote" | "local" | "mock"
XMR_WALLET_RPC = os.getenv("SATFLOW_XMR_WALLET_RPC", "")
XMR_NODE_RPC = os.getenv("SATFLOW_XMR_NODE_RPC", "")

# --- Storage ---
DB_PATH = Path(os.getenv("SATFLOW_DB_PATH", "./data/satsflow.db"))

# --- Session ---
SESSION_TIMEOUT = int(os.getenv("SATFLOW_SESSION_TIMEOUT", "900"))
