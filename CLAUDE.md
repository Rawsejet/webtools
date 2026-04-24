# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A local MCP server that provides `web_fetch` and `web_search` tools to Claude Code when running with a local LLM. Replaces Anthropic's cloud-only WebSearch and WebFetch by using Playwright for browsing, DuckDuckGo for search, and a local LLM for summarization.

## Environment

All commands run in the `webtools` conda environment (Python 3.12):

```bash
conda run -n webtools python /home/teja/webtools/server.py
conda run -n webtools pip install -r requirements.txt
conda run -n webtools playwright install chromium
```

## Configuration

Two environment variables control the local LLM connection (set in `~/.claude/mcp.json` under the `webtools` entry):

- `LOCAL_LLM_BASE_URL` — OpenAI-compatible endpoint (default: `http://localhost:8000/v1`)
- `LOCAL_LLM_MODEL` — model ID to use (default: `Qwen/Qwen3-32B`)

The MCP server is registered in `~/.claude/mcp.json`. Restart Claude Code after config changes.

## Architecture

Single file: `server.py`. Runs as a stdio MCP server.

- **Browser**: Playwright Chromium, lazily initialized once (`_browser` global), headless. Each page fetch creates a fresh context to avoid cookie/storage leakage.
- **Text extraction**: `extract_text_from_html()` strips scripts, styles, nav, footer, header via BeautifulSoup (lxml parser).
- **LLM summarization**: `call_local_llm()` sends extracted text + prompt to the local LLM via OpenAI-compatible chat completions. Two system prompts: `SUMMARIZE_SYSTEM` (for fetch) and `SEARCH_SYSTEM` (for search).
- **Content limits**: `MAX_FETCH_CHARS = 30000`, `MAX_SEARCH_PAGE_CHARS = 15000`, `MAX_SEARCH_RESULTS = 5`. Search fetches actual page content for only the top 2 results.

## Tool Flow

- **web_fetch**: URL + prompt → Playwright navigate → extract text → call local LLM with SUMMARIZE_SYSTEM → return summary
- **web_search**: query + prompt → DuckDuckGo `DDGS.text()` → collect result metadata → fetch top 2 pages → build combined context → call local LLM with SEARCH_SYSTEM → return summary

## Known Issues

- `call_local_llm()` imports `AsyncAnthropic` but only uses `AsyncOpenAI`. The Anthropic client is created and immediately closed — dead code that can be removed.
