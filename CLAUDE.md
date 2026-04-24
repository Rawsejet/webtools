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

The MCP server is registered in `~/.claude/mcp.json` using the `start-server.sh` wrapper, which auto-detects a running vLLM process and sets `LOCAL_LLM_BASE_URL` and `LOCAL_LLM_MODEL` before launching `server.py`. Restart Claude Code after config changes.


## Architecture

Single file: `server.py`. Runs as a stdio MCP server.

- **Browser**: Playwright Chromium, lazily initialized once (`_browser` global), headless. Each page fetch creates a fresh context to avoid cookie/storage leakage.
- **Text extraction**: `extract_text_from_html()` strips scripts, styles, nav, footer, header via BeautifulSoup (lxml parser).
- **LLM summarization**: `call_local_llm()` sends extracted text + prompt to the local LLM via OpenAI-compatible chat completions. Two system prompts: `SUMMARIZE_SYSTEM` (for fetch) and `SEARCH_SYSTEM` (for search).
- **Content limits**: `MAX_FETCH_CHARS = 30000`, `MAX_SEARCH_PAGE_CHARS = 15000`, `MAX_SEARCH_RESULTS = 5`. Search fetches actual page content for only the top 2 results.

## Tool Flow

- **web_fetch**: URL + prompt → Playwright navigate → extract text → call local LLM with SUMMARIZE_SYSTEM → return summary
- **web_search**: query + prompt → DuckDuckGo `DDGS.text()` → collect result metadata → fetch top 2 pages → build combined context → call local LLM with SEARCH_SYSTEM → return summary

## Notes

- `server.py` uses MCP SDK 1.27.0 `Tool` and `CallToolResult` types (not raw dicts).
- `detect_vllm()` has no caching — the wrapper script sets env vars at startup.
