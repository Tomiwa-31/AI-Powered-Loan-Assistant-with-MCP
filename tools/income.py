"""
FinScreen tool: verify_income
Maps to: POST /transactions/get — inflow analysis only
"""

from mcp.server.fastmcp import FastMCP
import httpx
from utils.error_handler import validation_error, transient_error, classify_plaid_error


INCOME_KEYWORDS = [
    "salary", "payroll", "wages", "income", "payment from",
    "direct deposit", "credit alert", "transfer in", "deposit",
]


def _looks_like_income(txn: dict) -> bool:
    # Plaid convention: negative amount = money INTO the account
    amount = txn.get("amount", 0)
    name = txn.get("name", "").lower()
    is_inflow = amount < 0
    has_keyword = any(kw in name for kw in INCOME_KEYWORDS)
    return is_inflow and has_keyword


def register(mcp: FastMCP):

    @mcp.tool(
        name="verify_income",
        description=(
            "Retrieves transactions for an applicant over a date range and identifies "
            "recurring salary or income credit entries. "
            "Use this to verify the applicant has a regular income source before "
            "approving a loan. "
            "Returns detected income transactions, estimated monthly income, and "
            "whether a recurring pattern was found. "
            "Only analyses INFLOWS (credits/deposits) — does NOT assess spending or "
            "outflows; call analyze_spending_patterns for that. "
            "Inputs: access_token (string, required), "
            "start_date (string YYYY-MM-DD, required), "
            "end_date (string YYYY-MM-DD, required). "
            "Recommended date range: last 3–6 months for reliable income detection."
        ),
    )
    async def verify_income(
        access_token: str,
        start_date: str,
        end_date: str,
    ) -> dict:
        from utils.plaid_client import plaid_post

        if not access_token or not access_token.strip():
            return validation_error("access_token is required.")
        if not start_date or not end_date:
            return validation_error(
                "start_date and end_date are required (format: YYYY-MM-DD).",
                detail=f"got start_date={start_date!r} end_date={end_date!r}",
            )

        try:
            resp = await plaid_post("/transactions/get", {
                "access_token": access_token,
                "start_date": start_date,
                "end_date": end_date,
            })
        except httpx.TimeoutException:
            return transient_error(
                "Request to Plaid timed out while fetching transactions for income analysis. Please retry.",
                detail="httpx timeout on /transactions/get (verify_income)",
            )
        except httpx.RequestError as e:
            return transient_error("Network error while contacting Plaid.", detail=str(e))

        if resp.status_code != 200:
            body = resp.json()
            return classify_plaid_error(resp.status_code, body.get("error_code", ""))

        data = resp.json()
        all_txns = data.get("transactions", [])
        income_txns = [t for t in all_txns if _looks_like_income(t)]

        # Group by month to detect recurring pattern
        monthly: dict[str, float] = {}
        for t in income_txns:
            month = t["date"][:7]
            monthly[month] = monthly.get(month, 0) + abs(t["amount"])

        avg_monthly = round(sum(monthly.values()) / len(monthly), 2) if monthly else 0.0
        is_recurring = len(monthly) >= 2

        return {
            "isError": False,
            "incomeDetected": len(income_txns) > 0,
            "isRecurring": is_recurring,
            "monthsCovered": len(monthly),
            "estimatedMonthlyIncome": avg_monthly,
            "currency": income_txns[0].get("iso_currency_code", "NGN") if income_txns else "NGN",
            "incomeTransactions": [
                {
                    "date": t["date"],
                    "name": t["name"],
                    "amount": abs(t["amount"]),
                }
                for t in income_txns[:20]
            ],
        }