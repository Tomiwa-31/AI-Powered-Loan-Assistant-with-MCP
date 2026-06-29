"""
FinScreen — one-shot sandbox access_token generator.

Run this once to get a sandbox access_token without cloning the Quickstart.

Usage:
    python get_access_token.py

Requires PLAID_CLIENT_ID and PLAID_SECRET to be set in your .env
"""

import asyncio
import httpx
from dotenv import load_dotenv
import os

load_dotenv()

CLIENT_ID = os.environ.get("PLAID_CLIENT_ID", "")
SECRET = os.environ.get("PLAID_SECRET", "")
BASE_URL = "https://sandbox.plaid.com"

HEADERS = {
    "Content-Type": "application/json",
    "PLAID-CLIENT-ID": CLIENT_ID,
    "PLAID-SECRET": SECRET,
}


async def main():
    if not CLIENT_ID or not SECRET:
        print("ERROR: PLAID_CLIENT_ID and PLAID_SECRET must be set in your .env")
        return

    async with httpx.AsyncClient(timeout=15.0) as client:

        # Step 1: Create a sandbox public_token for a test user
        print("Step 1: Creating sandbox public_token...")
        r1 = await client.post(
            f"{BASE_URL}/sandbox/public_token/create",
            json={
                "institution_id": "ins_109508",   # First Platypus Bank
                "initial_products": ["transactions", "identity", "liabilities"],
                "client_id": CLIENT_ID,
                "secret": SECRET,
            },
            headers=HEADERS,
        )

        if r1.status_code != 200:
            print(f"FAILED (HTTP {r1.status_code}): {r1.text}")
            return

        public_token = r1.json()["public_token"]
        print(f"  public_token: {public_token[:40]}...")

        # Step 2: Exchange public_token for access_token
        print("\nStep 2: Exchanging for access_token...")
        r2 = await client.post(
            f"{BASE_URL}/item/public_token/exchange",
            json={
                "public_token": public_token,
                "client_id": CLIENT_ID,
                "secret": SECRET,
            },
            headers=HEADERS,
        )

        if r2.status_code != 200:
            print(f"FAILED (HTTP {r2.status_code}): {r2.text}")
            return

        access_token = r2.json()["access_token"]
        item_id = r2.json()["item_id"]

        print(f"\n{'='*55}")
        print(f"SUCCESS — add this to your .env:")
        print(f"{'='*55}")
        print(f"PLAID_ACCESS_TOKEN={access_token}")
        print(f"{'='*55}")
        print(f"item_id (for reference): {item_id}")


asyncio.run(main())