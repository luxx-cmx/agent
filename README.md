# Agent Core

基于需求文档实现的单仓 MVP，包含：

- FastAPI 后端：会话管理、消息处理、SSE 流式输出、工具注册表、Agent 配置、TTS 生成
- Next.js 前端：聊天界面、工具调用卡片、会话侧栏、配置面板、TTS 播放
- MiMo 模型适配层：默认使用本地 Stub，配置 OpenAI 兼容端点后可切换真实 MiMo 调用

## 目录结构

- apps/api: FastAPI 后端
- apps/web: Next.js 前端
- data/sandbox: 文件工具沙箱目录
- data/audio: TTS 音频输出目录

## 启动后端

```powershell
Set-Location apps/api
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

默认鉴权 Token 为 agent-core-dev-token。

## 启动前端

```powershell
Set-Location apps/web
npm install
npm run dev
```

可选环境变量：

- NEXT_PUBLIC_API_BASE_URL，默认 http://localhost:8000/api/v1
- NEXT_PUBLIC_BEARER_TOKEN，默认 agent-core-dev-token
- DATABASE_URL，PostgreSQL 连接串，配置后自动启用持久化存储并建表
- REDIS_HOST、REDIS_PORT、REDIS_PASSWORD、REDIS_DB，配置后用于缓存 Agent 配置
- AGENT_CORE_MIMO_BASE_URL，配置后端 MiMo OpenAI 兼容接口地址
- AGENT_CORE_MIMO_API_KEY，配置后端 MiMo API Key

## 已实现能力

- 会话创建、分页、重命名、删除、导出 Markdown/JSON
- 最近消息滑动窗口与摘要压缩
- ReAct 风格工具选择与 Observation 汇总
- Web Search、Code Interpreter、Database Query、API Caller、File Manager、MiMo TTS Tool
- SSE 事件：agent/thought、tool_call、tts_progress、final_answer
- MiMo 模型配置与降级链路参数

## 当前实现说明

- 未配置 DATABASE_URL 时，后端回退到内存存储；配置后自动使用 PostgreSQL 持久化 conversations、messages、agent_configs 三张表
- Redis 为可选增强层，仅用于缓存 Agent 配置；不可用时自动回落到数据库读取
- TTS 在未配置真实 MiMo 服务时生成本地 wav 占位音频，接口形状保持一致
- 搜索、数据库、代码解释器工具使用本地演示适配器，便于联调前后端界面