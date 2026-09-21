"""Seed demo data into a fresh database.

Called once at app startup. Idempotent — if the demo creator already
exists, does nothing.
"""

from __future__ import annotations

from satsflow.storage.db import Database, NotFoundError

DEMO_SLUG = "kayakcrasher"


def seed_demo(db: Database) -> None:
    """Create the demo creator + a handful of donations, if not present."""
    try:
        db.get_creator_by_slug(DEMO_SLUG)
        return  # already seeded
    except NotFoundError:
        pass

    creator = db.create_creator(
        slug=DEMO_SLUG,
        display_name="Kayak Crasher",
        bio="Building SatsFlow in the open. Tips fund late-night dev sessions.",
        btc_address="bc1qexampleaddressxxxxxxxxxxxxxxxxxxxxxxxx",
        xmr_address=(
            "4examplexmrxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
            "xxxxxxxxxxxxxxxx"
        ),
    )
    assert creator.id is not None

    db.create_donation(
        creator.id, "BTC", 2_500_000,
        usd_at_receipt=168.42,
        donor_name="anon_sats",
        message="Great stream tonight! Keep it up.",
        txid="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2",
    )
    db.create_donation(
        creator.id, "BTC", 500_000,
        usd_at_receipt=33.68,
        txid="f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5",
    )
    db.create_donation(
        creator.id, "BTC", 1_250_000,
        usd_at_receipt=84.21,
        donor_name="monero_fan",
        message="Been following since day one. Sent some sats.",
        txid="1111111111111111111111111111111111111111111111111111111111111111",
    )
    db.create_donation(
        creator.id, "BTC", 250_000,
        usd_at_receipt=16.84,
        donor_name="quiet_donor",
        txid="2222222222222222222222222222222222222222222222222222222222222222",
    )
