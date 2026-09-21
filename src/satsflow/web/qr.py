"""QR code helpers.

Uses segno to generate inline SVG data-URIs so the invoice page can show
a scannable code without any image files or JS dependencies.
"""
from __future__ import annotations

import io

import segno


def btc_uri(address: str, amount_sats: int | None = None) -> str:
    """Return a BIP21-style Bitcoin payment URI."""
    uri = f"bitcoin:{address}"
    if amount_sats and amount_sats > 0:
        btc_amount = amount_sats / 100_000_000
        uri += f"?amount={btc_amount:.8f}"
    return uri


def xmr_uri(address: str, amount_piconero: int | None = None) -> str:
    """Return a Monero payment URI."""
    uri = f"monero:{address}"
    if amount_piconero and amount_piconero > 0:
        xmr_amount = amount_piconero / 1_000_000_000_000
        uri += f"?tx_amount={xmr_amount:.12f}"
    return uri


def qr_svg_data_uri(payload: str, scale: int = 6) -> str:
    """Return an inline data-URI SVG QR code for `payload`."""
    qr = segno.make(payload, error="m")
    buf = io.BytesIO()
    qr.save(
        buf,
        kind="svg",
        scale=scale,
        border=2,
        xmldecl=False,
        svgns=True,
        dark="#f7931a",
        light=None,
    )
    svg = buf.getvalue().decode("utf-8")
    # Return as a data URI so it can be embedded in an <img src="">
    import base64
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"
