from app.core.schemas import ToolDefinition


TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        id="web_search",
        name="Web Search",
        description="搜索网页摘要与链接，可配合 MiMo-V2-Omni 解析结果。",
        parameters_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        support_models=["MiMo-V2.5-Pro", "MiMo-V2.5", "MiMo-V2-Omni"],
    ),
    ToolDefinition(
        id="code_interpreter",
        name="Code Interpreter",
        description="执行受限 Python 片段，用于生成分析结论与代码检查结果。",
        parameters_schema={"type": "object", "properties": {"task": {"type": "string"}}},
        support_models=["MiMo-V2.5-Pro", "MiMo-V2.5"],
    ),
    ToolDefinition(
        id="database_query",
        name="Database Query",
        description="只读查询示例销售/订单数据，支持趋势分析场景。",
        parameters_schema={"type": "object", "properties": {"sql": {"type": "string"}}},
        support_models=["MiMo-V2.5-Pro", "MiMo-V2.5"],
    ),
    ToolDefinition(
        id="api_caller",
        name="API Caller",
        description="调用外部 HTTP API，内置敏感地址拦截。",
        parameters_schema={
            "type": "object",
            "properties": {"url": {"type": "string"}, "method": {"type": "string"}},
        },
        support_models=["MiMo-V2.5-Pro", "MiMo-V2.5", "MiMo-V2-Omni"],
    ),
    ToolDefinition(
        id="file_manager",
        name="File Manager",
        description="在沙箱目录读写 md/txt/csv 等文本文件。",
        parameters_schema={
            "type": "object",
            "properties": {"action": {"type": "string"}, "path": {"type": "string"}},
        },
        support_models=["MiMo-V2.5-Pro", "MiMo-V2.5", "MiMo-V2-Omni"],
    ),
    ToolDefinition(
        id="mimo_tts",
        name="MiMo TTS Tool",
        description="文本转语音、声音克隆与音色设计的统一入口。",
        parameters_schema={
            "type": "object",
            "properties": {
                "input": {"type": "string"},
                "voice": {"type": "string"},
                "model": {"type": "string"},
                "speed": {"type": "number"},
            },
        },
        support_models=[
            "MiMo-V2.5-TTS",
            "MiMo-V2.5-TTS-VoiceClone",
            "MiMo-V2.5-TTS-VoiceDesign",
            "MiMo-V2-TTS",
        ],
    ),
]
