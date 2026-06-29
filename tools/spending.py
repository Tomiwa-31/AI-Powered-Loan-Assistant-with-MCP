"""
FinScreen tool: analyze_spending_patterns
Maps to: POST /transactions/get — outflow analysis only
"""

from mcp.server.fastmcp import FastMCP
import httpx
from utils.error_handler import validation_error, transient_error, classify_plaid_error
from datetime import date


DEBT_CATEGORIES = [
    "loan_payments", "credit_card", "mortgage", "service", "bank_fees",
]


def _months_between(start: str, end: str) -> int:
    try:
        s = date.fromisoformat(start)
        e = date.fromisoformat(end)
        return max(1, (e.year - s.year) * 12 + (e.month - s.month))
    except ValueError:
        return 1


def register(mcp: FastMCP):

    @mcp.tool(
        name="analyze_spending_patterns",
        description=(
            "Retrieves transactions for an applicant over a date range and analyses "
            "their outflow (spending) patterns to assess over-leverage risk. "
            "Returns total monthly spending, top spend categories, debt-related "
            "payments detected, and a debt-to-income ratio if monthly income is provided. "
            "Only analyses OUTFLOWS (money leaving the account) — does NOT look at "
            "income or salary credits; call verify_income for that. "
            "Inputs: access_token (string, required), "
            "start_date (string YYYY-MM-DD, required), "
            "end_date (string YYYY-MM-DD, required), "
            "monthly_income (float, optional) — provide to calculate debt-to-income ratio."
        ),
    )
    async def analyze_spending_patterns(
        access_token: str,
        start_date: str,
        end_date: str,
        monthly_income: float = 0.0,
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
                "Request to Plaid timed out while fetching transactions for spending analysis. Please retry.",
                detail="httpx timeout on /transactions/get (analyze_spending_patterns)",
            )
        except httpx.RequestError as e:
            return transient_error("Network error while contacting Plaid.", detail=str(e))

        if resp.status_code != 200:
            body = resp.json()
            return classify_plaid_error(resp.status_code, body.get("error_code", ""))

        data = resp.json()
        all_txns = data.get("transactions", [])

        # Positive Plaid amounts = money leaving the account
        outflows = [t for t in all_txns if t.get("amount", 0) > 0]

        category_totals: dict[str, float] = {}
        debt_payments = 0.0
        for t in outflows:
            cats = t.get("category") or ["Uncategorized"]
            cat = cats[0].lower().replace(" ", "_")
            category_totals[cat] = category_totals.get(cat, 0) + t["amount"]
            if any(d in cat for d in DEBT_CATEGORIES):
                debt_payments += t["amount"]

        total_spend = sum(category_totals.values())
        months = _months_between(start_date, end_date)
        avg_monthly_spend = round(total_spend / months, 2)

        top_categories = sorted(
            [{"category": k, "total": round(v, 2)} for k, v in category_totals.items()],
            key=lambda x: x["total"],
            reverse=True,
        )[:8]

        dti_ratio = None
        if monthly_income and monthly_income > 0:
            dti_ratio = round(avg_monthly_spend / monthly_income, 3)

        return {
            "isError": False,
            "totalTransactionsAnalysed": len(outflows),
            "monthsCovered": months,
            "totalSpend": round(total_spend, 2),
            "averageMonthlySpend": avg_monthly_spend,
            "debtRelatedPayments": round(debt_payments, 2),
            "debtToIncomeRatio": dti_ratio,
            "overLeverageRisk": dti_ratio is not None and dti_ratio > 0.43,
            "topSpendCategories": top_categories,
        }