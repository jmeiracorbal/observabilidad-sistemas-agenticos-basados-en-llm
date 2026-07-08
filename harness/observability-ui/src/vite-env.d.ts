/// <reference types="vite/client" />

interface Window {
  __OBSERVABILITY_UI_CONFIG__?: {
    OBSERVABILITY_API_URL?: string;
    AGENT_API_URL?: string;
    APP_TITLE?: string;
    LLM_CONTEXT_WINDOW?: string;
    LLM_OUTPUT_TOKEN_RESERVE?: string;
  };
}

interface ImportMetaEnv {
  readonly VITE_OBSERVABILITY_API_URL?: string;
  readonly VITE_AGENT_API_URL?: string;
  readonly VITE_APP_TITLE?: string;
  readonly VITE_LLM_CONTEXT_WINDOW?: string;
  readonly VITE_LLM_OUTPUT_TOKEN_RESERVE?: string;
}
