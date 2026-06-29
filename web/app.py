"""
FinScreen Backend — FastAPI + proper MCP client.

This is the correct architecture:
1. app.py acts as the MCP CLIENT
2. It connects to server.py (the MCP SERVER) via stdio
3. Claude calls tools through the MCP session
4. Results feed back to Claude in a loop until verdict is ready
"""

import os
import sys
import json
import asyncio
import anthropic
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

app = FastAPI(title="FinScreen")
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")),
    name="static"
)

SERVER_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'server.py')
)
PYTHON_PATH = sys.executable


class AssessRequest(BaseModel):
    question: str
    access_token: str


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(html_path) as f:
        return f.read()


async def run_assessment(question: str, access_token: str) -> str:
    """
    Proper MCP client loop:
    1. Connect to server.py via stdio
    2. Discover tools
    3. Send user message to Claude with tools available
    4. When Claude calls a tool — execute it via MCP session
    5. Feed result back to Claude
    6. Repeat until Claude returns final text verdict
    """

    exit_stack = AsyncExitStack()

    # --- Connect to MCP server (server.py) ---
    server_params = StdioServerParameters(
        command=PYTHON_PATH,
        args=[SERVER_PATH],
        env={
            **os.environ,
            "PLAID_CLIENT_ID": os.environ.get("PLAID_CLIENT_ID", ""),
            "PLAID_SECRET": os.environ.get("PLAID_SECRET", ""),
            "PLAID_ENV": os.environ.get("PLAID_ENV", "sandbox"),
        }
    ) 

    stdio_transport = await exit_stack.enter_async_context(
        stdio_client(server_params)
    )
    read_stream, write_stream = stdio_transport
    session = await exit_stack.enter_async_context(
        ClientSession(read_stream, write_stream)
    )
    
    #This is the MCP handshake. The client and server exchange some setup info (like protocol version and capabilities)
    await session.initialize()

    # --- Discover tools from server.py ---
    tools_response = await session.list_tools()
    tools = [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema,
        }
        for tool in tools_response.tools
    ]

    # --- Build initial message ---
    anthropic_client = anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY", "")
    )

    system_prompt = (
        "You are FinScreen, an AI loan officer assistant. "
        "When given an applicant's access_token, use the available tools to assess "
        "their loan eligibility. Always call check_account_balance, verify_income, "
        "and analyze_spending_patterns. Call verify_identity and get_existing_liabilities "
        "if available. "
        "Return a structured verdict with: "
        "1. ELIGIBLE or INELIGIBLE "
        "2. Recommended loan limit in NGN (if eligible) "
        "3. Key reasons for your decision "
        "4. Any risk flags identified"
    )

    messages = [
        {
            "role": "user",
            "content": f"{question}\n\nApplicant access_token: {access_token}"
        }
    ]

    # --- Agentic loop: Claude calls tools, we execute them, feed back results ---
    while True:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )

        # If Claude is done — return the final text
        if response.stop_reason == "end_turn":
            final = ""
            for block in response.content:
                if hasattr(block, "text"):
                    final += block.text
            await exit_stack.aclose()
            return final

        # Claude wants to call tools — execute each one via MCP session
        if response.stop_reason == "tool_use":
            # Add Claude's response to message history
            messages.append({
                "role": "assistant",
                "content": response.content
            })

            # Execute each tool Claude requested
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_result = await session.call_tool(
                        block.name,
                        arguments=block.input
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(
                            tool_result.content[0].text
                            if tool_result.content
                            else ""
                        ),
                    })

            # Feed tool results back to Claude
            messages.append({
                "role": "user",
                "content": tool_results###################################
            })

        else:
            # Unexpected stop reason
            await exit_stack.aclose()
            return "Assessment could not be completed."


@app.post("/assess")
async def assess(req: AssessRequest):
    try:
        verdict = await run_assessment(req.question, req.access_token)
        return {"success": True, "verdict": verdict}

    except anthropic.AuthenticationError:
        return JSONResponse(
            status_code=401,
            content={"success": False, "error": "Invalid ANTHROPIC_API_KEY."}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.app:app", host="0.0.0.0", port=8000, reload=False)