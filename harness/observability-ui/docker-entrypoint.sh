#!/bin/sh
set -eu

cat > /usr/share/nginx/html/config.js <<EOF_CONFIG
window.__OBSERVABILITY_UI_CONFIG__ = {
  OBSERVABILITY_API_URL: "${OBSERVABILITY_API_URL:-http://localhost:8001}",
  AGENT_API_URL: "${AGENT_API_URL:-http://localhost:8000}",
  APP_TITLE: "${APP_TITLE:-Observabilidad}",
  LLM_CONTEXT_WINDOW: "${LLM_CONTEXT_WINDOW:-128000}",
  LLM_OUTPUT_TOKEN_RESERVE: "${LLM_OUTPUT_TOKEN_RESERVE:-4000}"
};
EOF_CONFIG
