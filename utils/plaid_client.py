"""
Shared httpx client for all Plaid API calls.
Wired up in Phase 4 — this file is scaffolded now so every tool module
can import it without circular dependencies.
"""

import httpx
from config.settings import PLAID_BASE_URL, PLAID_CLIENT_ID, PLAID_SECRET


def get_headers() -> dict[str, str]:
    """Standard headers required on every Plaid request."""
    return {
        "Content-Type": "application/json",
        "PLAID-CLIENT-ID": PLAID_CLIENT_ID,
        "PLAID-SECRET": PLAID_SECRET,
    }


async def plaid_post(endpoint: str, body: dict) -> httpx.Response:
    """
    POST to a Plaid sandbox endpoint.
    Returns the raw httpx.Response — callers handle status codes themselves
    so each tool can return the right errorCategory.

    Usage (Phase 4):
        resp = await plaid_post("/accounts/get", {"access_token": token})
        if resp.status_code != 200:
            return classify_plaid_error(resp.status_code, ...)
    """
    url = f"{PLAID_BASE_URL}{endpoint}"
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
        return await client.post(url, json=body, headers=get_headers())
 
    


#AsyncClient:it's that the entire server stays responsive to other requests while waiting. If a loan assessment is running and Claude fires another tool call, the server handles both concurrently instead of freezing.