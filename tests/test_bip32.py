"""BIP32/BIP84 tests against published reference vectors."""
from __future__ import annotations

import pytest

from satsflow.core.bech32 import encode_segwit
from satsflow.core.bip32 import (
    Bip32Error,
    parse_xpub,
    pubkey_to_p2wpkh,
    xpub_receive_address,
)

# BIP84 test vector — mnemonic "abandon abandon ... about"
BIP84_XPUB = (
    "zpub6rFR7y4Q2AijBEqTUquhVz398htDFrtymD9xYYfG1m4wAcvPhXNfE3EfH1r1ADqtfSdVC"
    "ToUG868RvUUkgDKf31mGDtKsAYz2oz2AGutZYs"
)
BIP84_ADDR_0 = "bc1qcr8te4kr609gcawutmrza0j4xv80jy8z306fyu"
BIP84_ADDR_1 = "bc1qnjg0jd8228aq7egyzacy8cys3knf9xvrerkf9g"


class TestXpubParsing:
    def test_parses_zpub(self):
        xp = parse_xpub(BIP84_XPUB)
        assert len(xp.pubkey) == 33
        assert xp.pubkey[0] in (2, 3)
        assert len(xp.chain_code) == 32

    def test_rejects_garbage(self):
        with pytest.raises(Bip32Error):
            parse_xpub("not-an-xpub")

    def test_rejects_bad_checksum(self):
        bad = BIP84_XPUB[:-1] + ("q" if BIP84_XPUB[-1] != "q" else "p")
        with pytest.raises(Bip32Error):
            parse_xpub(bad)


class TestBip84Derivation:
    def test_first_receive_address(self):
        assert xpub_receive_address(BIP84_XPUB, 0) == BIP84_ADDR_0

    def test_second_receive_address(self):
        assert xpub_receive_address(BIP84_XPUB, 1) == BIP84_ADDR_1

    def test_addresses_are_unique(self):
        assert xpub_receive_address(BIP84_XPUB, 100) != xpub_receive_address(BIP84_XPUB, 101)

    def test_addresses_are_segwit(self):
        for i in range(5):
            assert xpub_receive_address(BIP84_XPUB, i).startswith("bc1q")

    def test_negative_index_rejected(self):
        with pytest.raises(Bip32Error):
            xpub_receive_address(BIP84_XPUB, -1)

    def test_hardened_index_rejected(self):
        with pytest.raises(Bip32Error):
            xpub_receive_address(BIP84_XPUB, 0x80000000)


class TestPubkeyToAddress:
    def test_known_pubkey_generator(self):
        pubkey = bytes.fromhex(
            "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
        )
        addr = pubkey_to_p2wpkh(pubkey)
        assert addr.startswith("bc1q")
        assert len(addr) >= 42


class TestBech32:
    def test_bip173_reference_vector(self):
        program = bytes.fromhex("751e76e8199196d454941c45d1b3a323f1433bd6")
        addr = encode_segwit("bc", 0, program)
        assert addr == "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"

    def test_rejects_bad_witness_version(self):
        with pytest.raises(ValueError):
            encode_segwit("bc", 99, b"\x00" * 20)
