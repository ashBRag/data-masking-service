"""Seed the `masking_policies` table with the current XML tokenization policy.

Usage:
    uv run python scripts/seed_masking_policies.py
    uv run python scripts/seed_masking_policies.py --clear   # wipe existing rows first
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Running this file directly (not via `python -m`) puts scripts/ on sys.path
# instead of the project root, so `app`/`libs` wouldn't otherwise be
# importable - add the root explicitly before importing them.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import delete  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.models.masking_policy import MaskingPolicy  # noqa: E402
from libs.db import Database, DatabaseSettings  # noqa: E402

SAMPLE_POLICIES = [
    MaskingPolicy(
        policy_name="xml_deterministic_tokenization",
        action="tokenize",
        strategy="deterministic",
        fields=[
            # Reduced to fields that identify a PERSON, not project/task
            # labels - a resource's name and the users who created/last
            # updated a record are genuine PII; a project or activity name
            # (e.g. "MHRNP1 - ARC", "Approval for shore pile") is a business
            # label, not personal or "absolutely confidential" data, and
            # masking it made chat answers meaningfully less useful (can't
            # reference a project or task by its real name) for no privacy
            # benefit. Scoped by parent tag (Resource/Name) since "Name"
            # alone would also match Activity/Name, Project/Name, etc. -
            # see docs/services/masking.md's "Field scoping" section.
            "Resource/Name",
            "CreateUser",
            "LastUpdateUser",
        ],
        token_format="<TOKEN_{type}_{hash}>",
        rules={
            "same_value_same_token": True,
            "different_value_different_token": True,
            "consistent_across_file": True,
            "preserve_xml_structure": True,
            "preserve_element_names": True,
            "preserve_non_sensitive_values": True,
            "do_not_mask_dates": True,
            "do_not_mask_times": True,
            "do_not_mask_numbers_unless_listed": True,
        },
    ),
]


async def seed(clear: bool) -> None:
    """Insert SAMPLE_POLICIES, optionally clearing existing rows first."""
    db = Database(
        DatabaseSettings(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            database=settings.POSTGRES_DB,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
        )
    )

    async for session in db.get_session():
        if clear:
            await session.execute(delete(MaskingPolicy))
            await session.commit()
            print("Cleared existing masking policies.")

        session.add_all(SAMPLE_POLICIES)
        await session.commit()

    for policy in SAMPLE_POLICIES:
        print(f"Seeded masking policy {policy.id}: {policy.policy_name}")

    await db.disconnect()


def main() -> None:
    """Parse CLI args and run the seed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clear", action="store_true", help="Delete existing masking policies before seeding.")
    args = parser.parse_args()
    asyncio.run(seed(clear=args.clear))


if __name__ == "__main__":
    main()
