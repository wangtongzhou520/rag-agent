# Ragent AI

Ragent AI 是面向 Agentic RAG 的 Python 应用平台，覆盖从文档入库到智能问答的完整链路。

- **功能覆盖**：混合检索（向量 + ES 关键词 + LightRAG 图谱 + 联网搜索）、问题理解（术语映射 / 改写拆分 / 意图树 / 多库路由）、模型档位与熔断降级、会话记忆、公平排队限流、可编排入库 Pipeline、MCP 工具、RAG Trace、管理后台。
- **前端契约稳定**：保持现有 React 前端依赖的 REST 路径、`Result<T>` 包装和 SSE 六事件协议，支持零改动对接。
- **独立数据模型**：全新项目启动时初始化自己的 PostgreSQL Schema，不复用其他实现的表结构、数据或迁移历史。

## 技术栈

Python 3.12+ / FastAPI / SQLAlchemy 2.0 (async) + asyncpg / pgvector / redis-py / 自研 PG 队列（异步任务）/ httpx / FastMCP / Pydantic v2 / uv。自研模型接入层（档位路由 + 首包探测 + 三态熔断），不引入 LangChain 等编排框架。

## 设计文档

| 文档 | 内容 |
|---|---|
| [00-总体架构与技术选型](docs/00-总体架构与技术选型.md) | 架构基线：技术选型、进程拓扑、工程结构、关键决策、分期路线图 |
| [01-问答主链路与会话记忆](docs/01-问答主链路与会话记忆.md) | 七步编排管线、SSE 事件协议、记忆与摘要、反馈、取消 |
| [02-问题理解与混合检索](docs/02-问题理解与混合检索.md) | 术语映射、改写拆分、意图树、四通道检索、RRF 融合、Rerank、溯源 |
| [03-入库管线与文档处理](docs/03-入库管线与文档处理.md) | 解析器矩阵、Block 模型、分块、向量化、多 Sink、可编排 Pipeline、定时刷新 |
| [04-模型接入层](docs/04-模型接入层.md) | 模型档位、候选路由、首包探测、三态熔断、Token 估算、Prompt 管理 |
| [05-流量保护与韧性设计](docs/05-流量保护与韧性设计.md) | Redis 公平排队、Lua 原子 claim、取消广播、幂等、自研 PG 队列可靠性 |
| [06-MCP 工具体系](docs/06-MCP工具体系.md) | MCP server/client、工具注册、LLM 提参与三态结局 |
| [07-系统管理与可观测](docs/07-系统管理与可观测.md) | 认证授权、审计、RAG Trace、Dashboard、agents 人设与 Prompt 槽位 |

## 开发命令

```bash
uv sync                                        # 安装依赖（虚拟环境由 uv 管理）
uv run uvicorn app.main:app --port 9090        # 启动 API 服务（root_path=/api/ragent）
uv run python -m app.worker                    # 启动 PG 队列 worker（M2 起有实质逻辑）
uv run python -m mcp_server.main               # 启动 MCP 工具服务（:9099）
uv run pytest -q                               # 测试
uv run ruff check app mcp_server               # Lint
```

## 实施顺序

按 `00` 文档第 9 节路线图推进：M1 骨架 + 问答主链路 → M2 入库链路 → M3 混合检索增强 → M4 可编排入库 + MCP + 管理面 → M5 韧性与生产化。当前进度：M1/M2 核心代码已落地——JWT + Redis 会话认证（默认关闭，待配置启用）、SSE 六事件协议、模型候选容错、会话记忆与摘要装饰、pgvector 单通道检索、来源引用、固定五步入库内核、本地解析与分块、知识库/文档/chunk CRUD、HNSW 初始化及 PG 队列 worker。数据库、Redis 和模型供应商配置完成后需做真实环境联调；M3 的改写/意图树与混合检索尚未实现。
