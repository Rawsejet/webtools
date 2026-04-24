"""MCP server providing web_fetch and web_search tools for local LLM usage."""

import asyncio
import os
import re
import subprocess

from bs4 import BeautifulSoup
from ddgs import DDGS
from mcp.server import Server
from mcp.types import TextContent, Tool, CallToolResult
from openai import AsyncOpenAI
from playwright.async_api import async_playwright


MAX_FETCH_CHARS = 30000
MAX_SEARCH_RESULTS = 5
MAX_SEARCH_PAGE_CHARS = 15000


def detect_vllm():
    """Detect vLLM port and model from environment or running process."""
    env_url = os.environ.get("LOCAL_LLM_BASE_URL")
    env_model = os.environ.get("LOCAL_LLM_MODEL")
    if env_url and env_model:
        return env_url, env_model

    try:
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "vllm" in line and "serve" in line and "grep" not in line:
                m_port = re.search(r"--port\s+(\d+)", line)
                m_model = re.search(r"--served-model-name\s+(\S+)", line)
                port = m_port.group(1) if m_port else "8000"
                model = m_model.group(1) if m_model else "Qwen3-32B"
                return f"http://localhost:{port}/v1", model
    except Exception:
        pass

    return "http://localhost:8000/v1", "Qwen3-32B"


SUMMARIZE_SYSTEM = (
    "You are a research assistant. You receive web page content and a user prompt. "
    "Extract only the information relevant to the prompt. Be concise and factual. "
    "Cite the source URL(s). If the content does not contain relevant information, "
    "say so directly."
)

SEARCH_SYSTEM = (
    "You are a research assistant. You receive search results (titles, snippets, "
    "and page excerpts) for a query. Answer the user's question or summarize the "
    "findings based on the results. Be concise. Include source titles and URLs. "
    "If the results don't answer the question, say so."
)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

server = Server("webtools")

# Browser instance, lazily initialized
_browser = None


async def get_browser():
    global _browser
    if _browser is None:
        pw = await async_playwright().start()
        _browser = await pw.chromium.launch(headless=True)
    return _browser


def extract_text_from_html(html: str) -> str:
    """Extract readable text from HTML, stripping scripts/styles."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text)


async def fetch_page_text(url: str) -> str:
    """Navigate to a URL with Playwright and return extracted text."""
    browser = await get_browser()
    context = await browser.new_context(user_agent=USER_AGENT)
    page = await context.new_page()
    try:
        await page.goto(url, timeout=15000, wait_until="domcontentloaded")
        await asyncio.sleep(1)
        html = await page.content()
        text = extract_text_from_html(html)
        if len(text) > MAX_FETCH_CHARS:
            text = text[:MAX_FETCH_CHARS] + "\n... (truncated)"
        return text
    finally:
        await context.close()


async def call_local_llm(system: str, user: str) -> str:
    """Send a request to the local LLM and return the response text."""
    base_url, model = detect_vllm()
    client = AsyncOpenAI(base_url=base_url, api_key="none")
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=2048,
        temperature=0.3,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    return response.choices[0].message.content or ""


WEB_FETCH_TOOL = Tool(
    name="web_fetch",
    description=(
        "Fetch a webpage and extract information relevant to a prompt. "
        "Uses Playwright to load the page, then summarizes the content "
        "via a local LLM based on the given prompt."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch content from",
            },
            "prompt": {
                "type": "string",
                "description": "What to extract or find on the page",
            },
        },
        "required": ["url", "prompt"],
        "additionalProperties": False,
    },
)

WEB_SEARCH_TOOL = Tool(
    name="web_search",
    description=(
        "Search the web via DuckDuckGo, fetch top results, and summarize "
        "relevant findings via a local LLM. Returns concise results without "
        "filling the context with raw page dumps."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            },
            "prompt": {
                "type": "string",
                "description": "What to find or extract from the search results",
            },
            "max_results": {
                "type": "integer",
                "description": "Number of top results to fetch (default 3, max 5)",
                "default": 3,
            },
        },
        "required": ["query", "prompt"],
        "additionalProperties": False,
    },
)


@server.list_tools()
async def list_tools():
    return [WEB_FETCH_TOOL, WEB_SEARCH_TOOL]


def ok(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)])


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> CallToolResult:
    if name == "web_fetch":
        url = arguments["url"]
        prompt = arguments["prompt"]

        text = await fetch_page_text(url)

        if not text.strip():
            return ok(f"Failed to extract content from {url}")

        user_msg = (
            f"Prompt: {prompt}\n\n"
            f"Source URL: {url}\n\n"
            f"Page content:\n{text}"
        )
        summary = await call_local_llm(SUMMARIZE_SYSTEM, user_msg)
        return ok(summary)

    elif name == "web_search":
        query = arguments["query"]
        prompt = arguments["prompt"]
        max_results = min(arguments.get("max_results", 3), MAX_SEARCH_RESULTS)

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        if not results:
            return ok(f"No search results found for: {query}")

        pages = []
        for r in results[:max_results]:
            title = r.get("title", "")
            snippet = r.get("body", r.get("description", ""))
            url = r.get("href", "")
            pages.append({"title": title, "snippet": snippet, "url": url})

        fetched_texts = []
        for page in pages[:2]:
            try:
                text = await fetch_page_text(page["url"])
                if len(text) > MAX_SEARCH_PAGE_CHARS:
                    text = text[:MAX_SEARCH_PAGE_CHARS] + "\n... (truncated)"
                fetched_texts.append(text)
            except Exception as e:
                fetched_texts.append(f"[Error fetching {page['url']}: {e}]")

        sections = []
        for i, page in enumerate(pages):
            section = (
                f"Result {i + 1}:\n"
                f"  Title: {page['title']}\n"
                f"  URL: {page['url']}\n"
                f"  Snippet: {page['snippet']}"
            )
            if i < len(fetched_texts):
                section += f"\n  Page content:\n{fetched_texts[i]}"
            sections.append(section)

        user_msg = (
            f"Query: {query}\n"
            f"Prompt: {prompt}\n\n"
            f"Search Results:\n\n"
            + "\n\n---\n\n".join(sections)
        )
        summary = await call_local_llm(SEARCH_SYSTEM, user_msg)
        return ok(summary)

    else:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Unknown tool: {name}")],
            isError=True,
        )


async def main():
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
