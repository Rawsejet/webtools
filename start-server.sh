#!/usr/bin/env bash
# Wrapper that detects a running vLLM server and launches the MCP webtools server.

set -e

detect_vllm() {
    local line
    line=$(ps aux | grep 'vllm' | grep 'serve' | grep -v grep | head -1) || true
    if [[ -z "$line" ]]; then
        echo "ERROR: No running vLLM server found (expected 'vllm serve ...')" >&2
        exit 1
    fi

    local port model
    port=$(echo "$line" | grep -oP -- '--port\s+\K\d+' || echo "8000")
    model=$(echo "$line" | grep -oP -- '--served-model-name\s+\K\S+' || echo "Qwen3-32B")

    export LOCAL_LLM_BASE_URL="http://localhost:${port}/v1"
    export LOCAL_LLM_MODEL="$model"
}

detect_vllm

exec /home/teja/miniconda3/envs/webtools/bin/python /home/teja/webtools/server.py "$@"
