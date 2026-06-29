"""
FinScreen MCP Server — entry point.

Registers all loan eligibility tools and starts the server via stdio transport.
Claude Desktop connects to this process through .mcp.json.

Tool inventory (one tool per concern):
  check_account_balance     — /accounts/get
  verify_income             — /transactions/get  (inflow/salary analysis)
  analyze_spending_patterns — /transactions/get  (outflow/leverage analysis)
  verify_identity           — /identity/get
  get_existing_liabilities  — /liabilities/get
"""

import sys
from mcp.server.fastmcp import FastMCP
from config.settings import validate_config

# Validate credentials at startup
missing = validate_config()
if missing:
    print(
        f"[FinScreen] WARNING: Missing environment variables: {', '.join(missing)}. "
        "Set them in .env before running loan assessments.",
        file=sys.stderr,
    )

#creating our mcp server instance
mcp = FastMCP(
    name="finscreen",
    instructions=(
        "You are a loan officer assistant for FinScreen. "
        "When asked to assess loan eligibility, always call these tools in order: "
        "1. check_account_balance — confirms the applicant has accounts and funds. "
        "2. verify_income — confirms regular salary or income credits. "
        "3. analyze_spending_patterns — assesses over-leverage risk. "
        "4. get_existing_liabilities — checks existing debt burden (call if available). "
        "5. verify_identity — cross-checks declared identity (call if available). "
        "Never issue an eligibility verdict without calling at least the first three. "
        "Return a structured assessment: eligible/ineligible, reasons, and recommended loan limit."
    ),
)

# Register all tools
from tools.balance import register as register_balance
from tools.income import register as register_income
from tools.spending import register as register_spending
from tools.identity import register as register_identity
from tools.liabilities import register as register_liabilities

register_balance(mcp)
register_income(mcp)
register_spending(mcp)
register_identity(mcp)
register_liabilities(mcp)

if __name__ == "__main__":
    mcp.run(transport="stdio")

#The only reason register() exists is because the developer didn't want to write ALL the tools inside server.py. It would get massive. So they split each tool into its own file.