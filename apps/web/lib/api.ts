export type ToolCall = {
  id: string;
  tool_id: string;
  display_name: string;
  arguments: Record<string, unknown>;
  result: Record<string, unknown>;
  duration_ms: number;
  status: "success" | "failed";
};

export type Message = {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  created_at: string;
  model?: string | null;
  tokens_used: number;
  latency_ms: number;
  thought?: string | null;
  tool_calls: ToolCall[];
  tts_audio_url?: string | null;
};

export type Conversation = {
  id: string;
  title: string;
  model: string;
  created_at: string;
  updated_at: string;
  preview?: string | null;
  system_prompt?: string;
  summary?: string | null;
  messages?: Message[];
};

export type AgentConfig = {
  model: string;
  temperature: number;
  max_iterations: number;
  memory_window: number;
  mimo_fallback: string[];
  enabled_tools: string[];
};

export type HealthStatus = {
  status: string;
  store: string;
  llm_provider: string;
  tts_provider: string;
  image_provider?: string;
};

export type DatabaseSchemaTable = {
  name: string;
  columns: Array<{ name: string; data_type: string }>;
};

export type DatabaseSchema = {
  status: "success" | "failed";
  dialect?: string | null;
  tables: DatabaseSchemaTable[];
  error?: string | null;
};

export type DatabaseQueryResult = {
  status: "success" | "failed";
  sql?: string | null;
  row_count: number;
  truncated: boolean;
  rows: Array<Record<string, unknown>>;
  error?: string | null;
  detail?: string | null;
};

export type ToolDefinition = {
  id: string;
  name: string;
  description: string;
  support_models: string[];
  enabled?: boolean;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const BEARER_TOKEN = process.env.NEXT_PUBLIC_BEARER_TOKEN ?? "agent-core-dev-token";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${BEARER_TOKEN}`,
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

export async function fetchConversations() {
  return request<{ items: Conversation[]; total: number }>("/conversations");
}

export async function createConversation(defaultModel = "MiMo-V2.5-Pro") {
  return request<Conversation>("/conversations", {
    method: "POST",
    body: JSON.stringify({
      title: "Agent Core Demo",
      system_prompt: "你是 Agent Core 的企业级智能体。请用结构化方式回答问题。",
      default_model: defaultModel,
    }),
  });
}

export async function fetchConversation(conversationId: string) {
  return request<Conversation>(`/conversations/${conversationId}`);
}

type StreamEvent = {
  event: string;
  data: unknown;
};

export async function sendMessageStream(
  conversationId: string,
  content: string,
  model: string,
  generationTarget: string,
  onEvent: (event: StreamEvent) => void,
) {
  const response = await fetch(`${API_BASE_URL}/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${BEARER_TOKEN}`,
    },
    body: JSON.stringify({ content, model, generation_target: generationTarget, stream: true }),
  });

  if (!response.ok || !response.body) {
    throw new Error(await response.text());
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";

    for (const chunk of chunks) {
      const lines = chunk.split("\n");
      const eventLine = lines.find((line) => line.startsWith("event:"));
      const dataLine = lines.find((line) => line.startsWith("data:"));
      if (!eventLine || !dataLine) {
        continue;
      }
      const event = eventLine.replace("event:", "").trim();
      const data = JSON.parse(dataLine.replace("data:", "").trim()) as unknown;
      onEvent({ event, data });
    }
  }
}

export async function fetchTools() {
  return request<{ items: ToolDefinition[] }>("/tools");
}

export async function fetchConfig() {
  return request<AgentConfig>("/agent/config");
}

export async function updateConfig(payload: Partial<AgentConfig>) {
  return request<AgentConfig>("/agent/config", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function fetchDatabaseSchema() {
  return request<DatabaseSchema>("/tools/database/schema");
}

export async function executeDatabaseQuery(sql: string) {
  return request<DatabaseQueryResult>("/tools/database/query", {
    method: "POST",
    body: JSON.stringify({ sql }),
  });
}

export async function fetchHealthStatus() {
  const response = await fetch(`${API_BASE_URL.replace("/api/v1", "")}/health`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<HealthStatus>;
}