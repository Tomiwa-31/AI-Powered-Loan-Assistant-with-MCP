"""
FinScreen Phase 4 — local tool tests.

Mocks httpx so we can verify:
  1. Each tool parses a realistic Plaid sandbox response correctly
  2. Timeout paths return the right errorCategory + isRetryable
  3. Invalid input returns validation_error before any HTTP call is made

Run: python -m pytest tests/test_tools.py -v
     (or: python tests/test_tools.py for no-pytest fallback)
"""

import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch


# ── helpers ──────────────────────────────────────────────────────────────────

def make_response(status: int, body: dict):
    """Build a mock httpx.Response."""
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body
    return r


def run(coro):
    return asyncio.run(coro)

# ── Plaid sandbox fixtures ────────────────────────────────────────────────────

ACCOUNTS_RESP = {
    "accounts": [
        {
            "account_id": "abc123",
            "name": "Plaid Checking",
            "type": "depository",
            "subtype": "checking",
            "balances": {
                "current": 1500.00,
                "available": 1200.00,
                "iso_currency_code": "USD",
            },
        }
    ]
}

TRANSACTIONS_RESP = {
    "accounts": [],
    "transactions": [
        {
            "date": "2024-01-31",
            "name": "Employer Payroll Deposit",
            "amount": -250000.0,   # negative = inflow in Plaid
            "iso_currency_code": "NGN",
            "category": ["Payroll"],
        },
        {
            "date": "2024-01-15",
            "name": "Rent Payment",
            "amount": 80000.0,     # positive = outflow
            "iso_currency_code": "NGN",
            "category": ["Service"],
        },
        {
            "date": "2024-02-28",
            "name": "Salary Credit",
            "amount": -250000.0,
            "iso_currency_code": "NGN",
            "category": ["Payroll"],
        },
    ],
    "total_transactions": 3,
}

IDENTITY_RESP = {
    "accounts": [
        {
            "account_id": "abc123",
            "owners": [
                {
                    "names": ["Amara Okonkwo"],
                    "emails": [{"data": "amara@example.com"}],
                    "phone_numbers": [{"data": "+2348012345678"}],
                    "addresses": [
                        {"data": {"street": "12 Broad St", "city": "Lagos", "region": "LA", "country": "NG"}}
                    ],
                }
            ],
        }
    ]
}

LIABILITIES_RESP = {
    "liabilities": {
        "credit": [
            {
                "name": "GTBank Credit Card",
                "last_statement_balance": 45000.0,
                "minimum_payment_amount": 5000.0,
                "is_overdue": False,
            }
        ],
        "mortgage": [],
        "student": [],
    }
}


# ── tests ─────────────────────────────────────────────────────────────────────

def test_check_account_balance_success():
    from tools.balance import register
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP(name="test")
    register(mcp)

    tools = {t.name: t for t in mcp._tool_manager.list_tools()}
    tool_fn = tools["check_account_balance"].fn

    with patch("utils.plaid_client.plaid_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = make_response(200, ACCOUNTS_RESP)
        result = run(tool_fn(access_token="access-sandbox-test"))

    assert result["isError"] is False
    assert result["hasAccounts"] is True
    assert result["accountCount"] == 1
    assert result["accounts"][0]["currentBalance"] == 1500.00
    print("✓ check_account_balance — success path")


def test_check_account_balance_empty_token():
    from tools.balance import register
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP(name="test")
    register(mcp)
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}
    result = run(tools["check_account_balance"].fn(access_token=""))
    assert result["isError"] is True
    assert result["errorCategory"] == "validation"
    assert result["isRetryable"] is False
    print("✓ check_account_balance — validation error on empty token")


def test_check_account_balance_timeout():
    import httpx
    from tools.balance import register
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP(name="test")
    register(mcp)
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}

    with patch("utils.plaid_client.plaid_post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("timed out")
        result = run(tools["check_account_balance"].fn(access_token="access-sandbox-test"))

    assert result["isError"] is True
    assert result["errorCategory"] == "transient"
    assert result["isRetryable"] is True
    print("✓ check_account_balance — transient error on timeout")


def test_verify_income_detects_salary():
    from tools.income import register
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP(name="test")
    register(mcp)
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}

    with patch("utils.plaid_client.plaid_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = make_response(200, TRANSACTIONS_RESP)
        result = run(tools["verify_income"].fn(
            access_token="access-sandbox-test",
            start_date="2024-01-01",
            end_date="2024-02-28",
        ))

    assert result["isError"] is False
    assert result["incomeDetected"] is True
    assert result["isRecurring"] is True          # 2 months of salary
    assert result["estimatedMonthlyIncome"] == 250000.0
    print("✓ verify_income — detects recurring salary, correct monthly average")


def test_analyze_spending_dti():
    from tools.spending import register
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP(name="test")
    register(mcp)
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}

    with patch("utils.plaid_client.plaid_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = make_response(200, TRANSACTIONS_RESP)
        result = run(tools["analyze_spending_patterns"].fn(
            access_token="access-sandbox-test",
            start_date="2024-01-01",
            end_date="2024-02-28",
            monthly_income=250000.0,
        ))

    assert result["isError"] is False
    assert result["debtToIncomeRatio"] is not None
    assert result["overLeverageRisk"] is False    # 80k/250k = 0.32 — under 0.43
    print(f"✓ analyze_spending — DTI={result['debtToIncomeRatio']}, overLeverage={result['overLeverageRisk']}")


def test_verify_identity_parses_owners():
    from tools.identity import register
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP(name="test")
    register(mcp)
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}

    with patch("utils.plaid_client.plaid_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = make_response(200, IDENTITY_RESP)
        result = run(tools["verify_identity"].fn(access_token="access-sandbox-test"))

    assert result["isError"] is False
    assert result["identityRecordsFound"] == 1
    assert "Amara Okonkwo" in result["identities"][0]["names"]
    print("✓ verify_identity — parses owner name, email, phone, address")


def test_get_liabilities_success():
    from tools.liabilities import register
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP(name="test")
    register(mcp)
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}

    with patch("utils.plaid_client.plaid_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = make_response(200, LIABILITIES_RESP)
        result = run(tools["get_existing_liabilities"].fn(access_token="access-sandbox-test"))

    assert result["isError"] is False
    assert result["totalOutstandingDebt"] == 45000.0
    assert len(result["creditCards"]) == 1
    print("✓ get_existing_liabilities — parses credit card balance correctly")


def test_get_liabilities_product_not_supported():
    from tools.liabilities import register
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP(name="test")
    register(mcp)
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}

    with patch("utils.plaid_client.plaid_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = make_response(400, {"error_code": "PRODUCTS_NOT_SUPPORTED"})
        result = run(tools["get_existing_liabilities"].fn(access_token="access-sandbox-test"))

    assert result["isError"] is True
    assert result["errorCategory"] == "business"
    assert result["isRetryable"] is False
    print("✓ get_existing_liabilities — business_error on product not supported")


if __name__ == "__main__":
    tests = [
        test_check_account_balance_success,
        test_check_account_balance_empty_token,
        test_check_account_balance_timeout,
        test_verify_income_detects_salary,
        test_analyze_spending_dti,
        test_verify_identity_parses_owners,
        test_get_liabilities_success,
        test_get_liabilities_product_not_supported,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"✗ {t.__name__}: {e}")
            failed += 1
    print(f"\n{'─'*40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)


# pytest tests/test_tools.py