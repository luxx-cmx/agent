"use client";

import Link from "next/link";
import { useEffect, useState, useTransition } from "react";

import {
  type Conversation,
  type DatabaseSchema,
  type HealthStatus,
  fetchConversation,
  fetchConversations,
  fetchDatabaseSchema,
  fetchHealthStatus,
} from "../lib/api";


export function AdminDashboard() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [schema, setSchema] = useState<DatabaseSchema | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null);
  const [isPending, startTransition] = useTransition();

  async function refresh() {
    const [healthPayload, schemaPayload, conversationPayload] = await Promise.all([
      fetchHealthStatus(),
      fetchDatabaseSchema(),
      fetchConversations(),
    ]);
    setHealth(healthPayload);
    setSchema(schemaPayload);
    setConversations(conversationPayload.items);

    const firstConversation = conversationPayload.items[0];
    if (firstConversation) {
      const detail = await fetchConversation(firstConversation.id);
      setActiveConversation(detail);
    }
  }

  useEffect(() => {
    startTransition(async () => {
      await refresh();
    });
  }, []);

  async function handleConversationSelect(conversationId: string) {
    const detail = await fetchConversation(conversationId);
    setActiveConversation(detail);
  }

  return (
    <main className="shell">
      <aside className="panel sidebar" aria-label="会话列表与系统状态">
        <div className="actions">
          <div>
            <div className="badge">Admin</div>
            <h2 className="section-title" style={{ marginTop: 10 }}>落库会话</h2>
          </div>
          <Link className="ghost" href="/">返回控制台</Link>
        </div>

        <div className="metric-grid" style={{ marginTop: 14 }}>
          <div className="metric-card">
            <div className="muted">后端状态</div>
            <strong>{health?.status ?? "loading"}</strong>
          </div>
          <div className="metric-card">
            <div className="muted">存储后端</div>
            <strong>{health?.store ?? "unknown"}</strong>
          </div>
          <div className="metric-card">
            <div className="muted">LLM 来源</div>
            <strong>{health?.llm_provider ?? "unknown"}</strong>
          </div>
          <div className="metric-card">
            <div className="muted">TTS 来源</div>
            <strong>{health?.tts_provider ?? "unknown"}</strong>
          </div>
        </div>

        <div className="actions" style={{ marginTop: 16 }}>
          <span className="muted" style={{ fontSize: 12, fontWeight: 550 }}>最近会话</span>
          <button
            className="primary"
            onClick={() => startTransition(refresh)}
            disabled={isPending}
            aria-label={isPending ? "刷新中..." : "刷新会话列表"}
          >
            {isPending ? "刷新中..." : "刷新"}
          </button>
        </div>

        <div className="conversation-list" role="listbox" aria-label="会话列表">
          {conversations.map((conversation) => (
            <button
              key={conversation.id}
              className={`conversation-card ${activeConversation?.id === conversation.id ? "active" : ""}`}
              onClick={() => handleConversationSelect(conversation.id)}
              role="option"
              aria-selected={activeConversation?.id === conversation.id}
            >
              <h3>{conversation.title}</h3>
              <p className="muted">{conversation.model}</p>
              <p className="muted">{conversation.preview ?? "等待消息"}</p>
            </button>
          ))}
          {conversations.length === 0 && !isPending && (
            <div className="empty-state">
              <div className="empty-state-icon">📭</div>
              <span>暂无会话记录</span>
            </div>
          )}
        </div>
      </aside>

      <section className="panel chat" aria-label="会话详情">
        <header className="chat-header">
          <div className="badge badge--success">持久化审计</div>
          <h1 className="headline">会话与消息后台</h1>
          <p className="subline">直接读取 PostgreSQL 已持久化的数据，检查 conversations 和 messages 表中的最新内容。</p>
        </header>

        <div className="message-list">
          {activeConversation?.messages?.map((message) => (
            <article key={message.id} className={`message ${message.role === "user" ? "user" : "assistant"}`}>
              <div className="message-meta">
                <span>{message.role === "user" ? "用户" : "助手"}</span>
                <time dateTime={message.created_at}>{message.created_at}</time>
              </div>
              <div style={{ whiteSpace: "pre-wrap" }}>{message.content}</div>
            </article>
          ))}
          {(!activeConversation?.messages || activeConversation.messages.length === 0) && (
            <div className="empty-state" style={{ padding: "60px 16px" }}>
              <div className="empty-state-icon">💬</div>
              <span>{isPending ? "加载中..." : "选择一个会话查看消息详情"}</span>
            </div>
          )}
        </div>
      </section>

      <aside className="panel config" aria-label="数据库结构">
        <div className="badge">Schema</div>
        <h2 className="section-title" style={{ marginTop: 10 }}>数据库表结构</h2>
        <p className="muted" style={{ marginTop: 4 }}>Agent 生成 SQL 时基于这里的真实表和字段。</p>
        <div className="tool-grid" style={{ marginTop: 14 }}>
          {schema?.tables.map((table) => (
            <div className="tool-card" key={table.name}>
              <h4>{table.name}</h4>
              <p className="muted">{table.columns.map((column) => `${column.name}:${column.data_type}`).join(", ")}</p>
            </div>
          ))}
          {(!schema?.tables || schema.tables.length === 0) && (
            <div className="empty-state">
              <div className="empty-state-icon">🗄️</div>
              <span>加载中...</span>
            </div>
          )}
        </div>
      </aside>
    </main>
  );
}
