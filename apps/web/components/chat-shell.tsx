"use client";

import Link from "next/link";
import { useEffect, useState, useTransition } from "react";

import {
  type AgentConfig,
  type Conversation,
  type DatabaseQueryResult,
  type DatabaseSchema,
  type HealthStatus,
  type Message,
  type ToolDefinition,
  createConversation,
  executeDatabaseQuery,
  fetchConfig,
  fetchConversation,
  fetchConversations,
  fetchDatabaseSchema,
  fetchHealthStatus,
  fetchTools,
  sendMessageStream,
  updateConfig,
} from "../lib/api";


function createLocalId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }

  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

const demoPrompt = "查询最近一周销售数据，分析环比趋势并输出报告，同时生成语音播报";
const DEFAULT_CHAT_MODEL = "MiMo-V2.5-Pro";
type StreamStatus = "idle" | "thinking" | "acting" | "done" | "failed";
 type GenerationTargetId = "auto" | "dialogue" | "analysis" | "search" | "code" | "multimodal" | "tts" | "voice_clone" | "voice_design";
type GenerationTarget = {
  id: GenerationTargetId;
  label: string;
  description: string;
  preferredModels: string[];
  toolIds: string[];
  capabilities: string[];
  agentFunction: string;
  examplePrompt: string;
};


const MODEL_CATALOG = [
  {
    id: "MiMo-V2.5-Pro",
    type: "对话 / 推理",
    summary: "旗舰级 Agent 模型，适合复杂任务编排、多轮推理与工具链协同。",
    chatSelectable: true,
    highlights: ["复杂任务编排", "多轮推理", "企业级问答"],
  },
  {
    id: "MiMo-V2.5",
    type: "对话 / 推理",
    summary: "标准版，平衡性能与成本，适合常规对话、分析和自动化执行。",
    chatSelectable: true,
    highlights: ["平衡成本", "日常问答", "分析执行"],
  },
  {
    id: "MiMo-V2.5-TTS-VoiceClone",
    type: "语音合成",
    summary: "声音克隆模型，适合基于参考音频生成稳定语音分身。",
    chatSelectable: false,
    highlights: ["声音克隆", "品牌播报", "定制音色复刻"],
  },
  {
    id: "MiMo-V2.5-TTS-VoiceDesign",
    type: "语音合成",
    summary: "音色设计模型，可创建虚拟角色音色与风格化播报。",
    chatSelectable: false,
    highlights: ["音色设计", "虚拟角色", "风格化播报"],
  },
  {
    id: "MiMo-V2.5-TTS",
    type: "语音合成",
    summary: "通用文本转语音模型，用于报告播报、结果朗读与客服话术输出。",
    chatSelectable: false,
    highlights: ["文本播报", "结果朗读", "通用 TTS"],
  },
  {
    id: "MiMo-V2-Pro",
    type: "对话 / 推理",
    summary: "上一代旗舰，可作为稳定 fallback 模型处理常见 Agent 任务。",
    chatSelectable: true,
    highlights: ["fallback", "稳定问答", "兼容旧链路"],
  },
  {
    id: "MiMo-V2-Omni",
    type: "多模态",
    summary: "图文 / 音视频多模态理解模型，适合跨模态输入与搜索解析。",
    chatSelectable: true,
    highlights: ["多模态理解", "搜索解析", "跨媒体任务"],
  },
  {
    id: "MiMo-V2-TTS",
    type: "语音合成",
    summary: "上一代通用文本转语音模型，适合作为 TTS fallback。",
    chatSelectable: false,
    highlights: ["TTS fallback", "兼容旧语音链路", "通用播报"],
  },
] as const;

const GENERATION_TARGETS: GenerationTarget[] = [
  {
    id: "auto",
    label: "自动路由",
    description: "根据输入内容自动匹配报告、搜索、代码或语音链路。",
    preferredModels: ["MiMo-V2.5-Pro", "MiMo-V2.5", "MiMo-V2-Omni"],
    toolIds: ["web_search", "database_query", "code_interpreter", "api_caller", "file_manager", "mimo_tts"],
    capabilities: ["任务判断", "模型分发", "工具编排"],
    agentFunction: "先识别你要生成的内容，再选择对应模型和可用工具。",
    examplePrompt: demoPrompt,
  },
  {
    id: "dialogue",
    label: "单纯对话",
    description: "普通聊天、解释、总结和泛化问答直接调用最高模型。",
    preferredModels: ["MiMo-V2.5-Pro", "MiMo-V2.5", "MiMo-V2-Pro"],
    toolIds: [],
    capabilities: ["普通对话", "结构化回答", "高阶推理"],
    agentFunction: "不需要专项能力时，直接使用最高模型处理问题。",
    examplePrompt: "你好，帮我解释一下什么是智能体路由。",
  },
  {
    id: "analysis",
    label: "数据报告",
    description: "适合报表、总结、方案和多步推理。",
    preferredModels: ["MiMo-V2.5-Pro", "MiMo-V2.5", "MiMo-V2-Pro"],
    toolIds: ["database_query", "code_interpreter", "file_manager"],
    capabilities: ["报告生成", "数据分析", "长文总结"],
    agentFunction: "读取数据后输出结构化报告、结论和下一步建议。",
    examplePrompt: "整理最近一周销售数据，输出环比分析和一页总结报告。",
  },
  {
    id: "search",
    label: "联网搜索",
    description: "适合搜索资料、提炼网页摘要和整理多源结果。",
    preferredModels: ["MiMo-V2-Omni", "MiMo-V2.5-Pro", "MiMo-V2.5"],
    toolIds: ["web_search", "api_caller"],
    capabilities: ["网页检索", "资料整理", "结果摘要"],
    agentFunction: "联网抓取结果后，输出压缩过的检索结论。",
    examplePrompt: "联网搜索本周 AI Agent 领域的重要动态，并整理成三点摘要。",
  },
  {
    id: "code",
    label: "接口 / 代码",
    description: "适合代码片段、接口方案和自动化脚本说明。",
    preferredModels: ["MiMo-V2.5-Pro", "MiMo-V2.5", "MiMo-V2-Omni"],
    toolIds: ["code_interpreter", "api_caller", "file_manager"],
    capabilities: ["代码生成", "接口设计", "脚本检查"],
    agentFunction: "生成代码或接口设计，并结合工具给出执行层面的说明。",
    examplePrompt: "生成一个 FastAPI 接口示例，返回订单统计结果，并附上调用说明。",
  },
  {
    id: "multimodal",
    label: "图文解析",
    description: "适合截图理解、图文解析和跨媒体任务。",
    preferredModels: ["MiMo-V2-Omni", "MiMo-V2.5-Pro"],
    toolIds: ["web_search", "api_caller"],
    capabilities: ["截图解析", "图文理解", "跨媒体检索"],
    agentFunction: "优先走多模态理解链路，处理截图、图片和图文混合任务。",
    examplePrompt: "请根据截图内容总结页面结构，并指出关键交互区域。",
  },
  {
    id: "tts",
    label: "语音播报",
    description: "适合文本转语音、朗读和播报类输出。",
    preferredModels: ["MiMo-V2.5-TTS", "MiMo-V2-TTS"],
    toolIds: ["mimo_tts"],
    capabilities: ["文本转语音", "播报输出", "音频生成"],
    agentFunction: "把文本直接转换为语音，并返回可播放的音频地址。",
    examplePrompt: "请把下面内容生成语音播报：本周销售额增长了 12%，请输出简洁播报稿。",
  },
  {
    id: "voice_clone",
    label: "声音克隆",
    description: "适合复刻指定音色、品牌播报和语音分身。",
    preferredModels: ["MiMo-V2.5-TTS-VoiceClone", "MiMo-V2.5-TTS"],
    toolIds: ["mimo_tts"],
    capabilities: ["声音复刻", "品牌音色", "语音分身"],
    agentFunction: "按声音克隆链路生成更贴近指定角色或品牌的播报效果。",
    examplePrompt: "请用接近品牌主播的风格播报：新品将在周五上午 10 点发布。",
  },
  {
    id: "voice_design",
    label: "音色设计",
    description: "适合虚拟角色音色、风格化播报和角色配音。",
    preferredModels: ["MiMo-V2.5-TTS-VoiceDesign", "MiMo-V2.5-TTS"],
    toolIds: ["mimo_tts"],
    capabilities: ["角色音色", "风格设计", "虚拟播报"],
    agentFunction: "按角色和风格去设计音色，再生成对应的语音结果。",
    examplePrompt: "请用活泼的虚拟角色音色播报：欢迎来到本次新品发布会。",
  },
];

function getGenerationTarget(id: GenerationTargetId) {
  return GENERATION_TARGETS.find((target) => target.id === id) ?? GENERATION_TARGETS[0];
}

function inferGenerationTarget(prompt: string): GenerationTargetId {
  const lowered = prompt.toLowerCase();
  if (["克隆", "复刻", "voice clone", "分身"].some((keyword) => lowered.includes(keyword))) {
    return "voice_clone";
  }
  if (["音色设计", "角色音", "风格音", "voice design"].some((keyword) => lowered.includes(keyword))) {
    return "voice_design";
  }
  if (["语音", "播报", "tts", "朗读", "配音"].some((keyword) => lowered.includes(keyword))) {
    return "tts";
  }
  if (["截图", "图片", "图像", "视觉", "多模态"].some((keyword) => lowered.includes(keyword))) {
    return "multimodal";
  }
  if (["代码", "接口", "api", "python", "脚本"].some((keyword) => lowered.includes(keyword))) {
    return "code";
  }
  if (["搜索", "联网", "网页", "资料", "检索"].some((keyword) => lowered.includes(keyword))) {
    return "search";
  }
  if (["报告", "总结", "分析", "数据", "环比", "销量", "报表"].some((keyword) => lowered.includes(keyword))) {
    return "analysis";
  }
  return "dialogue";
}

function resolveModelForTarget(
  target: GenerationTarget,
  tools: ToolDefinition[],
) {
  const isCatalogModel = (modelId: string) => MODEL_CATALOG.some((model) => model.id === modelId);
  if (target.id === "auto") {
    return target.preferredModels.find((model) => isCatalogModel(model)) ?? DEFAULT_CHAT_MODEL;
  }

  const targetTools = tools.filter((tool) => target.toolIds.includes(tool.id));
  const supportedModels = targetTools.length > 0
    ? targetTools.reduce<string[]>((common, tool, index) => {
      if (index === 0) {
        return [...tool.support_models];
      }
      return common.filter((model) => tool.support_models.includes(model));
    }, [])
    : MODEL_CATALOG.map((model) => model.id as string);

  return target.preferredModels.find((model) => supportedModels.includes(model) && isCatalogModel(model))
    ?? target.preferredModels.find((model) => isCatalogModel(model))
    ?? DEFAULT_CHAT_MODEL;
}


export function ChatShell() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string>("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [tools, setTools] = useState<ToolDefinition[]>([]);
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [prompt, setPrompt] = useState(demoPrompt);
  const [selectedTarget, setSelectedTarget] = useState<GenerationTargetId>("dialogue");
  const [streamThought, setStreamThought] = useState("");
  const [streamTools, setStreamTools] = useState<Array<{ id: string; payload: string }>>([]);
  const [isSending, setIsSending] = useState(false);
  const [streamStatus, setStreamStatus] = useState<StreamStatus>("idle");
  const [streamStatusDetail, setStreamStatusDetail] = useState("等待发送");
  const [databaseSchema, setDatabaseSchema] = useState<DatabaseSchema | null>(null);
  const [databaseSql, setDatabaseSql] = useState("SELECT id, title, model, updated_at FROM conversations ORDER BY updated_at DESC LIMIT 10");
  const [databaseResult, setDatabaseResult] = useState<DatabaseQueryResult | null>(null);
  const [isQueryingDatabase, setIsQueryingDatabase] = useState(false);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    startTransition(async () => {
      const [conversationPayload, toolPayload, configPayload] = await Promise.all([
        fetchConversations(),
        fetchTools(),
        fetchConfig(),
      ]);
      const [schemaPayload, healthPayload] = await Promise.all([
        fetchDatabaseSchema(),
        fetchHealthStatus(),
      ]);
      setConversations(conversationPayload.items);
      setTools(toolPayload.items);
      setConfig(configPayload);
      setDatabaseSchema(schemaPayload);
      setHealth(healthPayload);
      if (conversationPayload.items.length === 0) {
        const conversation = await createConversation(configPayload.model);
        setConversations([conversation]);
        setActiveConversationId(conversation.id);
      } else {
        setActiveConversationId(conversationPayload.items[0].id);
      }
    });
  }, []);

  useEffect(() => {
    if (!activeConversationId) {
      return;
    }

    startTransition(async () => {
      const detail = await fetchConversation(activeConversationId);
      setMessages(detail.messages ?? []);
    });
  }, [activeConversationId]);

  async function handleCreateConversation() {
    const conversation = await createConversation(config?.model);
    setConversations((current) => [conversation, ...current]);
    setActiveConversationId(conversation.id);
    setMessages([]);
  }

  async function handleSend() {
    if (!activeConversationId || !prompt.trim() || isSending) {
      return;
    }
    const effectiveModel = routedModel;
    const userMessage: Message = {
      id: createLocalId(),
      role: "user",
      content: prompt,
      created_at: new Date().toISOString(),
      model: effectiveModel,
      tokens_used: 0,
      latency_ms: 0,
      tool_calls: [],
      thought: null,
      tts_audio_url: null,
    };
    setMessages((current) => [...current, userMessage]);
    const currentPrompt = prompt;
    setPrompt("");
    setStreamThought("");
    setStreamTools([]);
    setStreamStatus("thinking");
    setStreamStatusDetail("正在分析请求");
    setIsSending(true);
    window.scrollTo({ top: 0, behavior: "smooth" });

    try {
      await sendMessageStream(activeConversationId, currentPrompt, effectiveModel, activeTarget.id, (event) => {
        if (event.event === "agent/thought") {
          const payload = event.data as { content: string };
          setStreamThought(payload.content);
          setStreamStatus("thinking");
          setStreamStatusDetail("思考中");
          return;
        }
        if (event.event === "tool_call") {
          setStreamStatus("acting");
          setStreamStatusDetail("执行中");
          setStreamTools((current) => [
            ...current,
            {
              id: createLocalId(),
              payload: JSON.stringify(event.data, null, 2),
            },
          ]);
          return;
        }
        if (event.event === "final_answer") {
          const payload = event.data as { message: Message };
          setMessages((current) => [...current, payload.message]);
          setStreamStatus("done");
          setStreamStatusDetail("请求成功");
          window.scrollTo({ top: 0, behavior: "smooth" });
        }
      });
      const refreshed = await fetchConversations();
      setConversations(refreshed.items);
      setStreamStatus("done");
      setStreamStatusDetail("请求成功");
    } catch (error) {
      setStreamStatus("failed");
      setStreamStatusDetail(error instanceof Error ? error.message : "请求失败");
      throw error;
    } finally {
      setIsSending(false);
    }
  }

  async function handleConfigChange(field: keyof AgentConfig, value: string) {
    if (!config) {
      return;
    }
    const nextPayload: Partial<AgentConfig> = {
      ...config,
      [field]: field === "temperature" || field === "max_iterations" || field === "memory_window"
        ? Number(value)
        : value,
    };
    const updated = await updateConfig(nextPayload);
    setConfig(updated);
  }

  async function handleTargetChange(value: GenerationTargetId) {
    setSelectedTarget(value);
  }

  async function handleDatabaseQuery() {
    if (!databaseSql.trim() || isQueryingDatabase) {
      return;
    }
    setIsQueryingDatabase(true);
    try {
      const result = await executeDatabaseQuery(databaseSql);
      setDatabaseResult(result);
    } finally {
      setIsQueryingDatabase(false);
    }
  }

  const latestAssistant = [...messages].reverse().find((message) => message.role === "assistant");
  const activeTarget = getGenerationTarget(selectedTarget === "auto" ? inferGenerationTarget(prompt) : selectedTarget);
  const routedModel = resolveModelForTarget(activeTarget, tools);
  const effectiveModel = routedModel;
  const selectedCatalogModel = MODEL_CATALOG.find((model) => model.id === effectiveModel) ?? MODEL_CATALOG[0];
  const activeAgentTools = tools.filter((tool) => activeTarget.toolIds.includes(tool.id));
  const activeCapabilities = Array.from(new Set([...activeTarget.capabilities, ...selectedCatalogModel.highlights]));
  const streamStatusLabel = {
    idle: "等待发送",
    thinking: "思考中",
    acting: "执行中",
    done: "已完成",
    failed: "请求失败",
  }[streamStatus];

  return (
    <main className="shell">
      <aside className="panel sidebar">
        <div className="actions">
          <div>
            <div className="badge">Agent Core</div>
            <h2 className="section-title" style={{ marginTop: 10 }}>会话中心</h2>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Link className="ghost" href="/admin">后台</Link>
            <button className="primary" onClick={handleCreateConversation}>新建</button>
          </div>
        </div>

        <div className="metric-grid" style={{ marginTop: 14 }}>
          <div className="metric-card">
            <div className="muted">模型链路</div>
            <strong>{config?.model ?? "MiMo-V2.5-Pro"}</strong>
          </div>
          <div className="metric-card">
            <div className="muted">工具数量</div>
            <strong>{tools.length}</strong>
          </div>
          <div className="metric-card">
            <div className="muted">LLM 来源</div>
            <strong>{health?.llm_provider ?? "loading"}</strong>
          </div>
          <div className="metric-card">
            <div className="muted">TTS 来源</div>
            <strong>{health?.tts_provider ?? "loading"}</strong>
          </div>
        </div>

        <div className="conversation-list">
          {conversations.map((conversation) => (
            <button
              key={conversation.id}
              className={`conversation-card ${conversation.id === activeConversationId ? "active" : ""}`}
              onClick={() => setActiveConversationId(conversation.id)}
            >
              <h3>{conversation.title}</h3>
              <p className="muted">{conversation.model}</p>
              <p className="muted">{conversation.preview ?? "等待第一条消息"}</p>
            </button>
          ))}
        </div>
      </aside>

      <section className="panel chat">
        <header className="chat-header">
          <div className="badge">ReAct + Tooling + MiMo</div>
          <h1 className="headline">智能体平台控制台</h1>
          <p className="subline">
            覆盖会话管理、工具调用卡片、配置面板、TTS 播放与 MiMo 模型切换。当前运行态会直接展示真实 MiMo 或本地 Stub 的来源状态。
          </p>
        </header>

        <div className="message-list">
          {messages.length === 0 ? (
            <div className="message assistant">
              <div className="message-meta">
                <span>system</span>
                <span>示例</span>
              </div>
              <div>输入销售分析、联网搜索、接口生成或语音播报类问题即可触发对应工具。</div>
            </div>
          ) : null}

          {messages.map((message) => (
            <article key={message.id} className={`message ${message.role === "user" ? "user" : "assistant"}`}>
              <div className="message-meta">
                <span>{message.role === "user" ? "用户" : "助手"}</span>
                <span>{message.model ?? "manual"}</span>
              </div>
              <div style={{ whiteSpace: "pre-wrap" }}>{message.content}</div>
              {message.tool_calls.length > 0 ? (
                <div className="tool-grid" style={{ marginTop: 12 }}>
                  {message.tool_calls.map((tool) => (
                    <div key={tool.id} className="tool-card">
                      <h4>{tool.display_name}</h4>
                      <p className="muted">{JSON.stringify(tool.arguments)}</p>
                      <pre>{JSON.stringify(tool.result, null, 2)}</pre>
                    </div>
                  ))}
                </div>
              ) : null}
              {message.tts_audio_url ? (
                <audio className="audio" controls src={`${process.env.NEXT_PUBLIC_API_BASE_URL?.replace("/api/v1", "") ?? "http://localhost:8000"}${message.tts_audio_url}`} />
              ) : null}
            </article>
          ))}
        </div>

        <div className="composer">
          <div className="composer-card">
            <textarea rows={4} value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="输入消息..." />
            <div className="composer-footer">
              <label className="intent-switcher">
                <span className="muted">生成内容</span>
                <select
                  value={selectedTarget}
                  onChange={(event) => void handleTargetChange(event.target.value as GenerationTargetId)}
                >
                  {GENERATION_TARGETS.map((target) => (
                    <option key={target.id} value={target.id}>
                      {target.label}
                    </option>
                  ))}
                </select>
              </label>
              <div className="model-hint">
                <span className="muted">当前路由</span>
                <strong>{selectedCatalogModel.id}</strong>
                <span className="muted">{selectedTarget === "auto" ? `系统将按“${activeTarget.label}”自动适配到 ${effectiveModel}` : `${activeTarget.label} 已适配 ${effectiveModel}`}</span>
              </div>
              <div className="agent-summary">
                <span className="muted">智能体功能</span>
                <strong>{activeTarget.label}</strong>
                <span className="muted">{activeTarget.agentFunction}</span>
              </div>
              <div className="stream-status">
                <span className="muted">请求状态</span>
                <strong>{streamStatusLabel}</strong>
                <span className="muted">{streamStatusDetail}</span>
              </div>
            </div>
            <div className="actions">
              <button className="ghost" onClick={() => setPrompt(activeTarget.examplePrompt)}>填充示例</button>
              <button className="primary" onClick={handleSend} disabled={isPending || isSending}>
                {isSending ? "发送中..." : "发送消息"}
              </button>
            </div>
          </div>
        </div>
      </section>

      <aside className="panel config">
        <div className="badge">配置面板</div>
        <h2 className="section-title" style={{ marginTop: 10 }}>Agent 配置</h2>
        <p className="muted" style={{ marginTop: 4 }}>动态调整模型、窗口和迭代次数。</p>

        {config ? (
          <div className="config-grid" style={{ marginTop: 16 }}>
            <label>
              <span className="muted">模型</span>
              <select value={config.model} onChange={(event) => handleConfigChange("model", event.target.value)}>
                <option value="MiMo-V2.5-Pro">MiMo-V2.5-Pro</option>
                <option value="MiMo-V2.5">MiMo-V2.5</option>
                <option value="MiMo-V2-Pro">MiMo-V2-Pro</option>
                <option value="MiMo-V2-Omni">MiMo-V2-Omni</option>
              </select>
            </label>
            <label>
              <span className="muted">Temperature</span>
              <input value={config.temperature} onChange={(event) => handleConfigChange("temperature", event.target.value)} />
            </label>
            <label>
              <span className="muted">最大迭代次数</span>
              <input value={config.max_iterations} onChange={(event) => handleConfigChange("max_iterations", event.target.value)} />
            </label>
            <label>
              <span className="muted">记忆窗口</span>
              <input value={config.memory_window} onChange={(event) => handleConfigChange("memory_window", event.target.value)} />
            </label>
          </div>
        ) : null}

        <div className="section-block">
          <h3 className="section-block-title">当前智能体功能</h3>
          <div className="agent-function-card">
            <div className="model-summary-head">
              <div>
                <h4>{activeTarget.label}</h4>
                <p className="muted">适配模型：{effectiveModel}</p>
              </div>
              <span className="badge badge--success">{selectedTarget === "auto" ? "自动匹配" : "指定任务"}</span>
            </div>
            <p className="model-summary-text">{activeTarget.description}</p>
            <p className="agent-function-text">{activeTarget.agentFunction}</p>
            <div className="capability-chip-row">
              {activeCapabilities.map((capability) => (
                <span key={capability} className="capability-chip">{capability}</span>
              ))}
            </div>
            <div className="agent-tool-list">
              {activeAgentTools.map((tool) => (
                <span key={tool.id} className="agent-tool-pill">{tool.name}</span>
              ))}
              {activeAgentTools.length === 0 ? <span className="muted">当前路由暂未匹配到工具</span> : null}
            </div>
          </div>
        </div>

        <div className="section-block">
          <h3 className="section-block-title">模型与智能体简介</h3>
          <div className="model-catalog-grid">
            {MODEL_CATALOG.map((model) => (
              <article key={model.id} className={`model-summary-card ${effectiveModel === model.id ? "active" : ""}`}>
                <div className="model-summary-head">
                  <div>
                    <h4>{model.id}</h4>
                    <p className="muted">{model.type}</p>
                  </div>
                  {model.chatSelectable ? <span className="badge">可对话</span> : <span className="badge badge--success">语音 / 专项</span>}
                </div>
                <p className="model-summary-text">{model.summary}</p>
                <div className="capability-chip-row">
                  {model.highlights.map((highlight) => (
                    <span key={highlight} className="capability-chip">{highlight}</span>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </div>

        <div className="section-block">
          <h3 className="section-block-title">已注册工具</h3>
          <div className="tool-grid">
            {tools.map((tool) => (
              <div className="tool-card" key={tool.id}>
                <h4>{tool.name}</h4>
                <p className="muted">{tool.description}</p>
              </div>
            ))}
            {tools.length === 0 && (
              <p className="muted" style={{ fontSize: 12, padding: "8px 0" }}>暂无注册工具</p>
            )}
          </div>
        </div>

        <div className="section-block">
          <h3 className="section-block-title">数据库查询</h3>
          <div className="tool-card">
            <p className="muted">手工输入只读 SQL，直接调用后端数据库工具。</p>
            <textarea
              rows={5}
              value={databaseSql}
              onChange={(event) => setDatabaseSql(event.target.value)}
              style={{ marginTop: 8 }}
            />
            <div className="actions" style={{ marginTop: 10 }}>
              <button
                className="ghost"
                onClick={() => setDatabaseSql("SELECT c.id, c.title, m.role, m.created_at FROM conversations c JOIN messages m ON m.conversation_id = c.id ORDER BY m.created_at DESC LIMIT 20")}
              >
                填充示例
              </button>
              <button className="primary" onClick={handleDatabaseQuery} disabled={isQueryingDatabase}>
                {isQueryingDatabase ? "执行中..." : "执行查询"}
              </button>
            </div>
            {databaseSchema?.status === "success" ? (
              <div style={{ marginTop: 12 }}>
                <p className="muted" style={{ fontSize: 11, marginBottom: 6 }}>当前 schema</p>
                <div className="tool-grid">
                  {databaseSchema.tables.slice(0, 3).map((table) => (
                    <div className="tool-card" key={table.name}>
                      <h4>{table.name}</h4>
                      <p className="muted">{table.columns.map((column) => `${column.name}:${column.data_type}`).join(", ")}</p>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            {databaseResult ? (
              <div className="tool-card" style={{ marginTop: 10 }}>
                <div className="info-row">
                  <span className="muted">状态</span>
                  <span>{databaseResult.status}</span>
                </div>
                <div className="info-row">
                  <span className="muted">行数</span>
                  <span>{databaseResult.row_count}</span>
                </div>
                <pre>{JSON.stringify(databaseResult.rows, null, 2)}</pre>
                {databaseResult.error ? <p className="muted" style={{ marginTop: 6 }}>{databaseResult.error}</p> : null}
              </div>
            ) : null}
          </div>
        </div>

        {latestAssistant ? (
          <div className="section-block">
            <h3 className="section-block-title">最近一次推理</h3>
            <div className="tool-card">
              <div className="info-row">
                <span className="muted">Thought</span>
              </div>
              <p style={{ margin: "2px 0 8px", fontSize: 12.5 }}>{latestAssistant.thought ?? "未返回显式推理说明"}</p>
              <div className="info-row">
                <span className="muted">LLM Source</span>
                <span>{health?.llm_provider ?? "unknown"}</span>
              </div>
              <div className="info-row">
                <span className="muted">TTS Source</span>
                <span>{health?.tts_provider ?? "unknown"}</span>
              </div>
              <div className="info-row">
                <span className="muted">Latency</span>
                <span>{latestAssistant.latency_ms} ms</span>
              </div>
              <div className="info-row">
                <span className="muted">Tokens</span>
                <span>{latestAssistant.tokens_used}</span>
              </div>
            </div>
          </div>
        ) : null}

        {(streamThought || streamTools.length > 0) ? (
          <div className="section-block">
            <h3 className="section-block-title">流式进度</h3>
            <div className="tool-card">
              <div className="info-row">
                <span className="muted">Thought</span>
              </div>
              <p style={{ margin: "2px 0 0", fontSize: 12.5 }}>{streamThought || "等待模型决策"}</p>
              {streamTools.length > 0 ? (
                <div className="tool-grid" style={{ marginTop: 10 }}>
                  {streamTools.map((tool) => (
                    <div className="tool-card" key={tool.id}>
                      <pre style={{ margin: 0 }}>{tool.payload}</pre>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </aside>
    </main>
  );
}
