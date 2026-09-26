"""Minimal BIP32 + BIP84 derivation for watch-only Bitcoin addresses.

Reads an xpub (never an xprv), derives P2WPKH (bc1q) receive addresses.
Uses only ecdsa + base58 + pycryptodome + hashlib. No native deps.

Tested against BIP32 and BIP84 reference test vectors.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from base58 import b58decode_check
from Crypto.Hash import RIPEMD160
from ecdsa import SECP256k1, VerifyingKey
from ecdsa.ellipticcurve import Point

from satsflow.core.bech32 import encode_segwit

HARDENED = 0x80000000
CURVE = SECP256k1
GENERATOR = SECP256k1.generator
CURVE_ORDER = SECP256k1.order


@dataclass(frozen=True)
class XpubKey:
    depth: int
    parent_fingerprint: bytes
    child_number: int
    chain_code: bytes
    pubkey: bytes


class Bip32Error(Exception):
    """Raised on malformed xpub or derivation failure."""


def parse_xpub(xpub: str) -> XpubKey:
    """Decode a base58check xpub / zpub / ypub into its components."""
    try:
        raw = b58decode_check(xpub)
    except Exception as exc:
        raise Bip32Error(f"invalid base58check: {exc}") from exc

    if len(raw) != 78:
        raise Bip32Error(f"xpub payload must be 78 bytes, got {len(raw)}")

    version = raw[:4]
    known = {
        bytes.fromhex("0488b21e"),  # xpub
        bytes.fromhex("04b24746"),  # zpub
        bytes.fromhex("049d7cb2"),  # ypub
        bytes.fromhex("0295b43f"),  # Ypub
    }
    if version not in known:
        raise Bip32Error(f"unsupported xpub version bytes: {version.hex()}")

    pubkey = raw[45:78]
    if len(pubkey) != 33 or pubkey[0] not in (2, 3):
        raise Bip32Error("public key must be 33-byte compressed secp256k1")

    return XpubKey(
        depth=raw[4],
        parent_fingerprint=raw[5:9],
        child_number=int.from_bytes(raw[9:13], "big"),
        chain_code=raw[13:45],
        pubkey=pubkey,
    )


def _pubkey_to_point(pubkey: bytes) -> Point:
    vk = VerifyingKey.from_string(pubkey, curve=CURVE)
    return vk.pubkey.point


def _point_to_pubkey(point: Point) -> bytes:
    x = point.x().to_bytes(32, "big")
    prefix = b"\x02" if point.y() % 2 == 0 else b"\x03"
    return prefix + x


def derive_child(parent: XpubKey, index: int) -> XpubKey:
    """Non-hardened child derivation from an xpub."""
    if index >= HARDENED:
        raise Bip32Error("cannot derive hardened children from an xpub")
    if index < 0:
        raise Bip32Error("index must be non-negative")

    data = parent.pubkey + index.to_bytes(4, "big")
    I = hmac.new(parent.chain_code, data, hashlib.sha512).digest()
    IL = int.from_bytes(I[:32], "big")
    IR = I[32:]

    if IL == 0 or IL >= CURVE_ORDER:
        raise Bip32Error("invalid IL (retry next index)")

    parent_point = _pubkey_to_point(parent.pubkey)
    child_point = parent_point + (GENERATOR * IL)
    child_pubkey = _point_to_pubkey(child_point)

    return XpubKey(
        depth=parent.depth + 1,
        parent_fingerprint=b"\x00\x00\x00\x00",
        child_number=index,
        chain_code=IR,
        pubkey=child_pubkey,
    )


def derive_path(parent: XpubKey, path: list[int]) -> XpubKey:
    current = parent
    for index in path:
        current = derive_child(current, index)
    return current


def pubkey_to_p2wpkh(pubkey: bytes, hrp: str = "bc") -> str:
    """Native segwit address (bc1q...) for a compressed pubkey."""
    sha = hashlib.sha256(pubkey).digest()
    h = RIPEMD160.new(sha).digest()
    return encode_segwit(hrp, 0, h)


def xpub_receive_address(xpub: str, index: int, hrp: str = "bc") -> str:
    """Derive m/.../0/<index> from an account-level xpub. Returns bc1q..."""
    if index < 0 or index >= HARDENED:
        raise Bip32Error("index must be in [0, 2^31)")
    account = parse_xpub(xpub)
    external = derive_child(account, 0)  # chain 0 = external
    leaf = derive_child(external, index)
    return pubkey_to_p2wpkh(leaf.pubkey, hrp=hrp)
