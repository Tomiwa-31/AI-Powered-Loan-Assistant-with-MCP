"""
FinScreen tool: verify_identity
Maps to: POST /identity/get
"""

from mcp.server.fastmcp import FastMCP
import httpx
from utils.error_handler import validation_error, transient_error, classify_plaid_error


def register(mcp: FastMCP):

    @mcp.tool(
        name="verify_identity",
        description=(
            "Retrieves the applicant's identity information (full name, address, "
            "phone number, email) as held by their bank via Plaid's /identity/get. "
            "Use this to cross-check the identity the applicant declared on their "
            "loan application against what their bank has on file. "
            "Returns one identity record per linked account. "
            "Does NOT return account balances or transactions — "
            "use check_account_balance or verify_income for those. "
            "Input: access_token (string, required)."
        ),
    )
    async def verify_identity(access_token: str) -> dict:
        from utils.plaid_client import plaid_post

        if not access_token or not access_token.strip():
            return validation_error("access_token is required.")

        try:
            resp = await plaid_post("/identity/get", {"access_token": access_token})
        except httpx.TimeoutException:
            return transient_error(
                "Request to Plaid timed out while fetching identity data. Please retry.",
                detail="httpx timeout on /identity/get",
            )
        except httpx.RequestError as e:
            return transient_error("Network error while contacting Plaid.", detail=str(e))

        if resp.status_code != 200:
            body = resp.json()
            return classify_plaid_error(resp.status_code, body.get("error_code", ""))

        data = resp.json()
        accounts = data.get("accounts", [])

        identities = []
        for acc in accounts:
            for owner in acc.get("owners", []):
                identities.append({
                    "accountId": acc["account_id"],
                    "names": owner.get("names", []),
                    "emails": [e["data"] for e in owner.get("emails", [])],
                    "phoneNumbers": [p["data"] for p in owner.get("phone_numbers", [])],
                    "addresses": [
                        {
                            "street": a["data"].get("street", ""),
                            "city": a["data"].get("city", ""),
                            "region": a["data"].get("region", ""),
                            "country": a["data"].get("country", ""),
                        }
                        for a in owner.get("addresses", [])
                    ],
                })

        return {
            "isError": False,
            "identityRecordsFound": len(identities),
            "identities": identities,
        }