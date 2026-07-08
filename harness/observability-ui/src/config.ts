const runtimeConfig = window.__OBSERVABILITY_UI_CONFIG__ ?? {};

export const config = {
  appTitle: runtimeConfig.APP_TITLE ?? import.meta.env.VITE_APP_TITLE ?? 'TFG UNIR · proyecto observabilidad',
  observabilityApiUrl:
    runtimeConfig.OBSERVABILITY_API_URL ??
    import.meta.env.VITE_OBSERVABILITY_API_URL ??
    'http://localhost:8001',
  agentApiUrl:
    runtimeConfig.AGENT_API_URL ?? import.meta.env.VITE_AGENT_API_URL ?? 'http://localhost:8000',
  contextWindow: Number(
    runtimeConfig.LLM_CONTEXT_WINDOW ?? import.meta.env.VITE_LLM_CONTEXT_WINDOW ?? 128000,
  ),
  outputReserve: Number(
    runtimeConfig.LLM_OUTPUT_TOKEN_RESERVE ?? import.meta.env.VITE_LLM_OUTPUT_TOKEN_RESERVE ?? 4000,
  ),
};
