"""
FinScreen tool: get_existing_liabilities
Maps to: POST /liabilities/get
"""

from mcp.server.fastmcp import FastMCP
import httpx
from utils.error_handler import (
    validation_error, transient_error, classify_plaid_error, business_error
)


def register(mcp: FastMCP):

    @mcp.tool(
        name="get_existing_liabilities",
        description=(
            "Retrieves existing debt obligations (credit cards, mortgages, student loans) "
            "linked to the applicant's Plaid-connected accounts. "
            "Use this to assess how much existing debt the applicant carries before "
            "approving a new loan. "
            "Returns outstanding balances, minimum payments, and overdue flags per liability. "
            "Does NOT return bank account balances or transaction history. "
            "Note: returns a business_error (non-retryable) if the liabilities product "
            "is not enabled for this applicant's linked account. "
            "Input: access_token (string, required)."
        ),
    )
    async def get_existing_liabilities(access_token: str) -> dict:
        from utils.plaid_client import plaid_post

        if not access_token or not access_token.strip():
            return validation_error("access_token is required.")

        try:
            resp = await plaid_post("/liabilities/get", {"access_token": access_token})
        except httpx.TimeoutException:
            return transient_error(
                "Request to Plaid timed out while fetching liabilities. Please retry.",
                detail="httpx timeout on /liabilities/get",
            )
        except httpx.RequestError as e:
            return transient_error("Network error while contacting Plaid.", detail=str(e))

        if resp.status_code != 200:
            body = resp.json()
            plaid_code = body.get("error_code", "")
            if "PRODUCTS_NOT_SUPPORTED" in plaid_code or "INVALID_PRODUCT" in plaid_code:
                return business_error(
                    "Liabilities product is not enabled for this applicant's linked account. "
                    "Proceed without liabilities data or ask the applicant to re-link with liabilities scope.",
                    detail=plaid_code,
                )
            return classify_plaid_error(resp.status_code, plaid_code)

        data = resp.json()
        liabilities = data.get("liabilities", {})

        credit = liabilities.get("credit", [])
        mortgage = liabilities.get("mortgage", [])
        student = liabilities.get("student", [])

        total_outstanding = 0.0

        credit_summary = []
        for c in credit:
            bal = c.get("last_statement_balance") or 0
            total_outstanding += bal
            credit_summary.append({
                "type": "credit_card",
                "name": c.get("name", ""),
                "lastStatementBalance": bal,
                "minimumPaymentAmount": c.get("minimum_payment_amount"),
                "isOverdue": c.get("is_overdue", False),
            })

        mortgage_summary = []
        for m in mortgage:
            outstanding = m.get("origination_principal_amount") or 0
            total_outstanding += outstanding
            mortgage_summary.append({
                "type": "mortgage",
                "accountId": m.get("account_id", ""),
                "outstandingPrincipal": outstanding,
                "pastDueAmount": m.get("past_due_amount"),
                "isOverdue": (m.get("past_due_amount") or 0) > 0,
            })

        student_summary = []
        for s in student:
            principal = s.get("origination_principal_amount") or 0
            total_outstanding += principal
            student_summary.append({
                "type": "student_loan",
                "name": s.get("loan_name", ""),
                "outstandingPrincipal": principal,
                "minimumPaymentAmount": s.get("minimum_payment_amount"),
                "isOverdue": s.get("is_overdue", False),
            })

        return {
            "isError": False,
            "totalOutstandingDebt": round(total_outstanding, 2),
            "liabilitiesFound": len(credit) + len(mortgage) + len(student),
            "creditCards": credit_summary,
            "mortgages": mortgage_summary,
            "studentLoans": student_summary,
        }