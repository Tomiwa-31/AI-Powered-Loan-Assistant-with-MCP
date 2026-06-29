"""
Structured error responses for all FinScreen MCP tools.

Every error returned through a tool follows this contract:
  - isError: True
  - errorCategory: one of transient | validation | permission | business
  - isRetryable: bool — tells Claude whether to retry or surface to the user
  - message: human-readable explanation suitable for a loan officer
  - detail: optional technical detail for debugging

Error categories:
  transient   — network timeouts, 5xx from Plaid. Retry is safe.
  validation  — bad access_token format, missing required field. Do not retry.
  permission  — Plaid rejected the credentials or scope. Do not retry.
  business    — applicant has no accounts, product not enabled. Do not retry.
"""

from typing import Any


def transient_error(message: str, detail: str = "") -> dict[str, Any]:
    return {
        "isError": True,
        "errorCategory": "transient",
        "isRetryable": True,
        "message": message,
        "detail": detail,
    }


def validation_error(message: str, detail: str = "") -> dict[str, Any]:
    return {
        "isError": True,
        "errorCategory": "validation",
        "isRetryable": False,
        "message": message,
        "detail": detail,
    }


def permission_error(message: str, detail: str = "") -> dict[str, Any]:
    return {
        "isError": True,
        "errorCategory": "permission",
        "isRetryable": False,
        "message": message,
        "detail": detail,
    }


def business_error(message: str, detail: str = "") -> dict[str, Any]:
    return {
        "isError": True,
        "errorCategory": "business",
        "isRetryable": False,
        "message": message,
        "detail": detail,
    }


def classify_plaid_error(status_code: int, plaid_error_code: str = "") -> dict[str, Any]:
    """
    Map a Plaid HTTP response to a structured FinScreen error.
    Called in Phase 4 when httpx gets a non-2xx response.
    """
    if status_code >= 500:
        return transient_error(
            "Plaid service temporarily unavailable. Please try again shortly.",
            detail=f"HTTP {status_code}",
        )
    if status_code == 401:
        return permission_error(
            "Invalid Plaid credentials. Check PLAID_CLIENT_ID and PLAID_SECRET.",
            detail=plaid_error_code,
        )
    if status_code == 400:
        if "INVALID_ACCESS_TOKEN" in plaid_error_code:
            return validation_error(
                "The access_token provided is not valid. Re-link the applicant's account.",
                detail=plaid_error_code,
            )
        if "ITEM_LOGIN_REQUIRED" in plaid_error_code:
            return business_error(
                "Applicant's bank connection needs to be re-authenticated.",
                detail=plaid_error_code,
            )
        return validation_error(
            f"Bad request to Plaid: {plaid_error_code}",
            detail=f"HTTP {status_code}",
        )
    return transient_error(
        f"Unexpected response from Plaid (HTTP {status_code}).",
        detail=plaid_error_code,
    )


# Plaid's actual response (raw, technical, terse)
#{
  #"error_code": "INVALID_ACCESS_TOKEN", detaild parameter
  #"error_type": "INVALID_INPUT",
  #"error_message": "the provided access token is in an invalid format"  :message parametr
#}

#TODO
#MAKE SURE WE CREATE AA SIMULATION WHERE WE HANDLE EAC OF THOSE ERROR