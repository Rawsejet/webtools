# webtools

Local MCP server providing `web_fetch` and `web_search` tools for Claude Code when running with a local LLM.

## Why

Anthropic's built-in `WebSearch` and `WebFetch` tools require their cloud API. This replaces them locally using Playwright for browsing, DuckDuckGo for search, and a local LLM for summarization — keeping raw page dumps out of the coding agent's context.

## Setup

```bash
# Already done — environment is `webtools` conda env
conda create -n webtools python=3.12
conda run -n webtools pip install -r requirements.txt
conda run -n webtools playwright install chromium
```

## Configuration

Register the MCP server in `~/.claude/mcp.json` using the wrapper script:

```json
{
  "mcpServers": {
    "webtools": {
      "command": "<path-to-webtools>/start-server.sh"
    }
  }
}
```

The wrapper script (`start-server.sh`) detects a running vLLM process via `ps aux` at startup, extracts `--port` and `--served-model-name`, and sets `LOCAL_LLM_BASE_URL` and `LOCAL_LLM_MODEL` before launching `server.py`. This handles random vLLM ports without manual config.

To use fixed env vars instead (e.g. when running multiple LLMs), register `server.py` directly with env overrides:

```json
{
  "mcpServers": {
    "webtools": {
      "command": "<path-to-python>",
      "args": ["<path-to-webtools>/server.py"],
      "env": {
        "LOCAL_LLM_BASE_URL": "http://localhost:8000/v1",
        "LOCAL_LLM_MODEL": "Qwen/Qwen3-32B"
      }
    }
  }
}
```

> **Note:** The server requires a running vLLM process. If no vLLM server is detected at startup, the wrapper script exits with an error and the MCP tools won't be available.

> **Tip:** When using Claude models that support Anthropic's built-in `web_fetch` and `web_search`, prefer those over this local server. Tell Claude Code to use Anthropic's tools first and fall back to this server only when those aren't available — the cloud tools are more reliable and don't need a local LLM.

## Tools

### `web_fetch`

Fetches a URL and extracts relevant content via a local LLM.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `url`     | Yes      | The URL to fetch |
| `prompt`  | Yes      | What to extract or find on the page |

### `web_search`

Searches DuckDuckGo, fetches top results, and summarizes findings.

| Parameter     | Required | Description                          |
|---------------|----------|--------------------------------------|
| `query`       | Yes      | The search query                     |
| `prompt`      | Yes      | What to find or extract from results |
| `max_results` | No       | Results to fetch (default 3, max 5)  |

## How it works

1. **web_fetch**: Playwright navigates the URL → extracts page text → local LLM summarizes based on the prompt
2. **web_search**: DuckDuckGo returns result URLs → Playwright fetches top 2 pages → local LLM summarizes all findings against the prompt

The intermediate LLM call filters noise before content reaches the coding agent's context window.

## Troubleshooting

Check that a vLLM server is running:

```bash
ps aux | grep 'vllm' | grep 'serve'
```

Test the wrapper detection manually:

```bash
bash <path-to-webtools>/start-server.sh
```

It should launch without error. If it prints `ERROR: No running vLLM server found`, start your vLLM server first.

Restart Claude Code after any config changes to pick up the MCP server.
