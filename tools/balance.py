"""
FinScreen tool: check_account_balance
Maps to: POST /accounts/get
"""

from mcp.server.fastmcp import FastMCP
import httpx
from utils.error_handler import validation_error, transient_error, classify_plaid_error


def register(mcp: FastMCP):

    @mcp.tool(
        name="check_account_balance",
        description=(
            "Retrieves all bank accounts linked to an applicant's Plaid access_token "
            "and returns current and available balances for each account. "
            "Use this to assess whether the applicant has sufficient funds to cover "
            "loan repayments. Returns account type, subtype, currency, current balance, "
            "and available balance. "
            "Does NOT return transaction history — call verify_income or "
            "analyze_spending_patterns for that. "
            "Input: access_token (string, required). "
            "Returns an empty accounts list if the applicant has no linked accounts."
        ),
    )
    async def check_account_balance(access_token: str) -> dict:
        from utils.plaid_client import plaid_post

        if not access_token or not access_token.strip():
            return validation_error(
                "access_token is required to retrieve account balances.",
                detail="access_token was empty or missing",
            )

        try:
            resp = await plaid_post("/accounts/get", {"access_token": access_token})
            #error before it gets to plaid, plaid never saw your request
        except httpx.TimeoutException:
            return transient_error(
                "Request to Plaid timed out while fetching account balances. Please retry.",
                detail="httpx timeout on /accounts/get",
            )
        except httpx.RequestError as e:
            return transient_error(
                "Network error while contacting Plaid. Please retry.",
                detail=str(e),
            )
        #when the request successfully reached Plaid but Plaid rejected it:
        if resp.status_code != 200:
            body = resp.json()
            return classify_plaid_error(resp.status_code, body.get("error_code", ""))

        data = resp.json()
        accounts = data.get("accounts", [])

        if not accounts:
            return {
                "isError": False,
                "hasAccounts": False,
                "message": "No accounts found for this access_token.",
                "accounts": [],
            }

        return {
            "isError": False,
            "hasAccounts": True,
            "accountCount": len(accounts),
            "accounts": [
                {
                    "accountId": acc["account_id"],
                    "name": acc.get("name", ""),
                    "type": acc.get("type", ""),
                    "subtype": acc.get("subtype", ""),
                    "currency": acc["balances"].get("iso_currency_code", "NGN"),
                    "currentBalance": acc["balances"].get("current"),
                    "availableBalance": acc["balances"].get("available"),
                }
                for acc in accounts
            ],
        }