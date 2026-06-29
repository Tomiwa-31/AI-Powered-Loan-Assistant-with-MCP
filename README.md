# FinScreen — AI-Powered Loan Eligibility Screener

FinScreen is a loan officer assistant that uses Claude AI and Plaid's banking API to assess loan applicants. A loan officer asks a natural language question like _"Is this applicant eligible for a ₦500,000 loan?"_ and Claude calls real banking tools to pull the applicant's financial data and return a structured eligibility verdict.

---

## What We Built

### The Core Idea
Instead of a loan officer manually checking bank statements, income history, and existing debts, they paste an applicant's Plaid `access_token` into FinScreen and ask Claude a question. Claude then autonomously calls the right tools in the right order, retrieves real bank data, and produces a structured assessment.

### Architecture

```
Loan Officer (browser)
        |
        | fills in access_token + question
        ↓
FinScreen Web App (HTML frontend)
        |
        | POST /assess
        ↓
FastAPI Backend (web/app.py) ← MCP CLIENT
        |
        | stdio connection
        ↓
MCP Server (server.py) ← exposes 5 tools
        |
        | httpx calls
        ↓
Plaid Sandbox API
        |
        | bank data
        ↓
Claude (claude-sonnet-4-6)
        |
        | structured verdict
        ↓
Loan Officer sees: ELIGIBLE / INELIGIBLE + reasons
```

### How the Agentic Loop Works

The key architectural decision is that `app.py` acts as a proper **MCP client** — it does not pre-fetch data and dump it to Claude. Instead:

1. `app.py` connects to `server.py` via stdio (MCP handshake)
2. Claude receives the question + the list of available tools
3. Claude decides to call `check_account_balance` → `app.py` executes it via MCP session → result goes back to Claude
4. Claude calls `verify_income` → same loop
5. This continues until Claude has enough data
6. Claude returns `end_turn` with the final verdict

Claude is the one deciding which tools to call — the system prompt in `server.py` defines the order.

---

## Project Structure

```
finscreen/
├── run.py                        # Start the web server
├── server.py                     # MCP server — registers all 5 tools
├── parse_spec.py                 # Phase 2 — parses Plaid OpenAPI spec
├── get_access_token.py           # One-shot sandbox token generator
├── requirements.txt
├── .env.example                  # Copy to .env and fill in credentials
├── .mcp.json                     # MCP server config (team-shared)
├── claude_desktop_config.json    # Claude Desktop config (optional)
│
├── config/
│   ├── __init__.py
│   └── settings.py               # Loads env vars, validates credentials
│
├── tools/                        # One file per MCP tool
│   ├── __init__.py
│   ├── balance.py                # check_account_balance → /accounts/get
│   ├── income.py                 # verify_income → /transactions/get
│   ├── spending.py               # analyze_spending_patterns → /transactions/get
│   ├── identity.py               # verify_identity → /identity/get
│   └── liabilities.py            # get_existing_liabilities → /liabilities/get
│
├── utils/
│   ├── __init__.py
│   ├── plaid_client.py           # Shared httpx client for all Plaid calls
│   └── error_handler.py          # Structured errors (transient/validation/permission/business)
│
├── web/
│   ├── app.py                    # FastAPI backend + MCP client loop
│   └── static/
│       └── index.html            # Loan officer UI (single page)
│
└── tests/
    ├── test_tools.py             # Validation + local tests (no credentials needed)
    └── test_live.py              # Full live sandbox integration tests
```

---

## The 5 MCP Tools

Each tool maps to a specific Plaid endpoint and has a focused responsibility. Tool descriptions are written so Claude routes to the right tool reliably — each one explicitly states what it does **not** do.

| Tool | Plaid Endpoint | Purpose |
|------|---------------|---------|
| `check_account_balance` | `/accounts/get` | Checks if applicant has sufficient funds |
| `verify_income` | `/transactions/get` | Detects recurring salary/income credits |
| `analyze_spending_patterns` | `/transactions/get` | Assesses over-leverage risk via DTI ratio |
| `verify_identity` | `/identity/get` | Cross-checks declared identity vs bank records |
| `get_existing_liabilities` | `/liabilities/get` | Retrieves existing loans and credit card debt |

Note: `verify_income` and `analyze_spending_patterns` both use `/transactions/get` but look at opposite sides — inflows vs outflows. They are intentionally separate tools with distinct descriptions so Claude never confuses them.

---

## Error Handling

Every tool returns structured errors — never a bare string like `"Something went wrong"`. The error schema is:

```json
{
  "isError": true,
  "errorCategory": "transient | validation | permission | business",
  "isRetryable": true,
  "message": "Human-readable explanation",
  "detail": "Technical detail for debugging"
}
```

| Category | Example | Retryable |
|----------|---------|-----------|
| `transient` | Plaid timeout, 5xx response | Yes |
| `validation` | Empty access_token, bad date format | No |
| `permission` | Invalid credentials | No |
| `business` | Liabilities product not enabled for this Item | No |

---

## Setup

### 1. Clone and install

```bash
cd finscreen
python -m venv .venv

# Windows
.venv\Scripts\activate

# Mac/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.example .env
```

Fill in `.env`:

```
PLAID_CLIENT_ID=your_client_id
PLAID_SECRET=your_sandbox_secret
PLAID_ENV=sandbox
ANTHROPIC_API_KEY=your_anthropic_api_key
```

Get Plaid credentials free at [dashboard.plaid.com](https://dashboard.plaid.com).
Get your Anthropic API key at [console.anthropic.com](https://console.anthropic.com).

### 3. Generate a sandbox access token

```bash
python get_access_token.py
```

Copy the printed `access_token` into your `.env` as `PLAID_ACCESS_TOKEN`.

### 4. Run live tests

```bash
python tests/test_live.py
```

All 5 tools should return `✓ PASS`.

### 5. Start the server

```bash
python run.py
```

Open `http://localhost:8000` in your browser.

---

## Usage

1. Open `http://localhost:8000`
2. Paste the applicant's `access_token`
3. Type your assessment question e.g. _"Is this applicant eligible for a ₦500,000 loan?"_
4. Click **Run Eligibility Assessment**
5. Wait ~30-60 seconds while Claude calls all 5 tools
6. Receive a structured verdict: ELIGIBLE / INELIGIBLE, recommended limit, risk flags

---

## Key Design Decisions

**Tool descriptions include what each tool does NOT do.** This prevents Claude from calling `check_account_balance` hoping to get transaction history. Each tool explicitly says _"does NOT return transactions — call verify_income for that"_.

**`app.py` is the MCP client, not a proxy.** The backend connects to `server.py` via the MCP protocol and Claude calls tools through a proper session. The backend does not pre-fetch data.

**Credentials never touch config files.** `.mcp.json` uses `${ENV_VAR}` substitution. `.env` is gitignored. `claude_desktop_config.json` is a template only.

**`reload=False` in `run.py`.** Uvicorn's hot reload kills the async stdio subprocess mid-assessment.

---

## What's Next (Version 2 Features)

- **Database** — store applicant records and past assessments
- **Plaid Link frontend** — let applicants link their own bank account via the UI
- **Authentication** — loan officer login before accessing assessments
- **PDF report export** — generate a formal assessment document
- **Multi-applicant dashboard** — compare multiple applicants side by side
- **Production Plaid environment** — switch from sandbox to live bank data

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Model | Claude Sonnet (claude-sonnet-4-6) |
| MCP Framework | FastMCP (mcp >= 1.0.0) |
| Backend | FastAPI + Uvicorn |
| HTTP Client | httpx (async) |
| Banking API | Plaid Sandbox |
| Frontend | HTML / CSS / Vanilla JS |
| Config | python-dotenv |
| Validation | Pydantic v2 |