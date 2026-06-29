"""
FinScreen Phase 2 — Parse Plaid OpenAPI spec.

Fetches 2020-09-14.yml from GitHub, parses it with PyYAML, and prints
a focused report of only the endpoints FinScreen needs for loan assessment:

  /accounts/get        -> check_account_balance
  /transactions/get    -> verify_income + analyze_spending_patterns
  /identity/get        -> verify_identity
  /liabilities/get     -> get_existing_liabilities

For each endpoint prints:
  - path + method
  - description
  - required request body parameters
  - response fields we actually use in FinScreen

Run: python parse_spec.py
"""

import httpx
import yaml
from typing import Any

SPEC_URL = "https://raw.githubusercontent.com/plaid/plaid-openapi/master/2020-09-14.yml"

# The only Plaid endpoints FinScreen cares about
FINSCREEN_ENDPOINTS = {
    "/accounts/get":     "check_account_balance",
    "/transactions/get": "verify_income + analyze_spending_patterns",
    "/identity/get":     "verify_identity",
    "/liabilities/get":  "get_existing_liabilities",
}


def fetch_spec(url: str) -> dict:
    print(f"Fetching spec from GitHub...")
    r = httpx.get(url, timeout=30, follow_redirects=True)
    r.raise_for_status()
    print(f"OK — {len(r.content):,} bytes\n")
    return yaml.safe_load(r.text)


def resolve_ref(spec: dict, ref: str) -> dict:
    """Follow a $ref pointer like #/components/schemas/AccountsGetRequest."""
    parts = ref.lstrip("#/").split("/")
    node = spec
    for part in parts:
        node = node[part]
    return node


def get_required_params(spec: dict, endpoint: str, method: str = "post") -> list[dict]:
    """Extract required fields from the request body schema for an endpoint."""
    path_item = spec["paths"].get(endpoint, {})
    operation = path_item.get(method, {})
    
    try:
        body_schema_ref = (
            operation["requestBody"]["content"]["application/json"]["schema"]
        )
        if "$ref" in body_schema_ref:
            schema = resolve_ref(spec, body_schema_ref["$ref"])
        else:
            schema = body_schema_ref

        required_fields = schema.get("required", [])
        properties = schema.get("properties", {})

        params = []
        for field in required_fields:
            prop = properties.get(field, {})
            # Resolve nested $ref if present
            if "$ref" in prop:
                prop = resolve_ref(spec, prop["$ref"])
            params.append({
                "name": field,
                "type": prop.get("type", prop.get("format", "object")),
                "description": prop.get("description", "").split("\n")[0][:80],
            })
        return params

    except (KeyError, TypeError):
        return []


def get_response_fields(spec: dict, endpoint: str, method: str = "post") -> list[str]:
    """Extract top-level fields from the 200 response schema."""
    path_item = spec["paths"].get(endpoint, {})
    operation = path_item.get(method, {})

    try:
        resp_schema_ref = (
            operation["responses"]["200"]["content"]["application/json"]["schema"]
        )
        if "$ref" in resp_schema_ref:
            schema = resolve_ref(spec, resp_schema_ref["$ref"])
        else:
            schema = resp_schema_ref

        return list(schema.get("properties", {}).keys())

    except (KeyError, TypeError):
        return []


def get_description(spec: dict, endpoint: str, method: str = "post") -> str:
    path_item = spec["paths"].get(endpoint, {})
    operation = path_item.get(method, {})
    return operation.get("summary", operation.get("description", "No description"))[:120]


def print_separator():
    print("─" * 60)


def main():
    spec = fetch_spec(SPEC_URL)
    total = len(spec.get("paths", {}))
    print(f"Total endpoints in Plaid spec: {total}")
    print(f"FinScreen uses: {len(FINSCREEN_ENDPOINTS)} of {total}\n")

    for endpoint, maps_to in FINSCREEN_ENDPOINTS.items():
        print_separator()
        print(f"ENDPOINT : {endpoint}")
        print(f"METHOD   : POST")
        print(f"MAPS TO  : {maps_to}")
        print(f"DESC     : {get_description(spec, endpoint)}")

        params = get_required_params(spec, endpoint)
        if params:
            print(f"REQUIRED PARAMS:")
            for p in params:
                print(f"  • {p['name']} ({p['type']}) — {p['description']}")
        else:
            print(f"REQUIRED PARAMS: none resolved")

        fields = get_response_fields(spec, endpoint)
        if fields:
            print(f"RESPONSE FIELDS : {', '.join(fields)}")
        else:
            print(f"RESPONSE FIELDS : none resolved")

    print_separator()
    print("\nDone. These 4 endpoints cover all 5 FinScreen MCP tools.")
    print("Phase 3: build server.py tools using the params above as inputSchema.\n")


if __name__ == "__main__":
    main()