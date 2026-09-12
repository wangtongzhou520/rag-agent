# Ragent AI

Ragent AI 是面向 RAG 的知识检索与问答平台，覆盖文档上传与解析、分块与向量化入库、
问题理解与检索融合、带来源引用的流式回答，以及入库编排、MCP 工具、质量评测与运维管理，
形成一条可运行、可评测、可容器化交付的完整链路。

当前检索主链路是 **pgvector 单通道**：设计文档中规划的 ES 关键词、LightRAG 图谱与
联网搜索通道尚未实现，融合权重已按配置预留。完整差异见「实现边界」。

## 已实现能力

**问答主链路**

- 七事件 SSE 协议（`meta` / `thinking` / `response` / `finish` / `done`，以及 `guidance`
  等扩展事件），思考过程、Markdown 回答、来源角标定位与文档预览。
- 会话记忆与历史摘要、单实例停止生成（Redis 跨实例取消广播）、消息赞踩与可撤销反馈、
  按需推荐追问。
- 结构化歧义引导：多意图命中且分数接近时，以 `guidance` 事件给出候选知识范围。

**问题理解与检索**

- 查询词映射（PostgreSQL + Redis 缓存）、LLM 改写与子问题拆分（FAST 档，失败走确定性兜底）。
- 三级意图树分类、SYSTEM / MCP / KB 分流、多库范围路由与补充路配额。
- pgvector HNSW 向量召回（余弦距离，`ef_search` 与迭代扫描调优）、去重、加权 RRF、
  百炼 `qwen3-rerank` 重排、元数据批量回表与来源装配。

**模型接入层**

- 三档路由（FAST / STANDARD / DEEP）与物理模型注册表、候选 fallback、首包探测与三态熔断、
  Token 估算与 Prompt 槽位管理。
- 产品身份基线：助手自称与定位由 `RAGENT_AGENT__*` 配置（默认 `Ragent 知识助手`），
  所有面向用户的回答统一前置，默认不向用户披露底层模型与供应商。

**入库与文档处理**

- MIME 探测 + (MIME × 解析档位) 路由解析器：支持 `.md` / `.txt` / `.csv` / `.xlsx` /
  `.pdf` / `.html` / `.json` / `.xml`。
- Block 渲染、按预算分块、向量化逐条维度校验、pgvector 与关系表同事务写入。
- 知识库 / 文档 / Chunk 全量管理接口，以及分块、清理、反馈落库等异步任务。

**可编排入库 Pipeline**

- 六类节点（fetcher / parser / enhancer / chunker / enricher / indexer）、JSON 条件 DSL 与
  逐节点执行日志，管理台可配置并可调试运行。

**MCP 工具体系**

- FastMCP 独立服务（`:9099`，内置 weather / sales / ticket 示例工具）、client 侧工具发现与
  注册、意图驱动的 LLM 提参与三态结局、工具结果注入生成上下文、管理台启停与调试。

**韧性与质量**

- Redis FIFO 公平排队限流 + Lua 原子 claim、提交与消费幂等、自研 PG 队列
  （租约 / 心跳 / 崩溃恢复 / 指数退避）。
- 版本化黄金数据集（42 题事实问答 + 8 题无答案安全集）、质量门槛脚本、报告持久化与历史
  对比、可选语义裁判。

**交付与运维**

- 全栈容器编排（PostgreSQL/pgvector + Redis + MCP + API + Worker + 前端 Nginx），
  单镜像承担 API / Worker / MCP 三种进程角色。
- RAG Trace、Dashboard、审计日志、用户与权限管理、运行时与模型设置。
- React SPA 已完成登录与权限、问答、知识库/文档/Chunk、意图树、查询词映射、RAG Trace、
  检索质量实验台、Pipeline 与任务、智能体与 Prompt、MCP、运行时设置、用户与审计。

## 实现边界

以下能力属于设计文档的规划范围，当前代码尚未实现，评估时请勿按既有能力对待：

| 能力 | 现状 |
|---|---|
| ES 关键词通道、LightRAG 图谱通道、联网搜索通道 | 配置为 `type: none`；当前只装配向量通道，融合权重已预留 |
| MinerU 批量解析、图片/SVG + VLM 解析 | 未实现；上传这些格式会被解析器前置拦截 |
| 七类 block-aware chunker、`ChunkPacker`、人工块重嵌入 | 当前是「标题大纲 + 滑窗切分」的简化分块路径 |
| 远程定时刷新 | 仅预留 `schedule_cron` 等字段，没有 cron 扫描与执行器 |
| Pipeline 线上接入（`processMode=pipeline`） | Pipeline 目前是编排与调试入口，线上文档仍走固定入库内核 |
| MCP `youcom_search`、后台自动重发现、意图节点自定义 Prompt 模板 | 未实现；工具重发现目前由管理员显式触发 |

## 技术栈

Python 3.13（`requires-python >=3.12`，锁文件与镜像统一为 3.13）/ FastAPI / SQLAlchemy 2.0
(async) + asyncpg / pgvector / redis-py / 自研 PG 队列 / httpx / FastMCP / Pydantic v2 / uv。
模型接入层自研，不引入 LangChain 等编排框架。

## 设计文档

文档描述的是设计基线与验收标准，与代码现状的差异以「状态」列标注。

| 文档 | 内容 | 状态 |
|---|---|---|
| [00-总体架构与技术选型](docs/00-总体架构与技术选型.md) | 架构基线：技术选型、进程拓扑、工程结构、关键决策、分期路线图 | 设计基线 |
| [01-问答主链路与会话记忆](docs/01-问答主链路与会话记忆.md) | 七步编排管线、SSE 事件协议、记忆与摘要、反馈、取消 | 已落地 |
| [02-问题理解与混合检索](docs/02-问题理解与混合检索.md) | 术语映射、改写拆分、意图树、四通道检索、RRF 融合、Rerank、溯源 | 问题理解与后处理已落地；四通道仅向量通道 |
| [03-入库管线与文档处理](docs/03-入库管线与文档处理.md) | 解析器矩阵、Block 模型、分块、向量化、多 Sink、可编排 Pipeline、定时刷新 | 固定内核与 Pipeline 调试已落地；增强解析与定时刷新为规划 |
| [04-模型接入层](docs/04-模型接入层.md) | 模型档位、候选路由、首包探测、三态熔断、Token 估算、Prompt 管理 | 已落地 |
| [05-流量保护与韧性设计](docs/05-流量保护与韧性设计.md) | Redis 公平排队、Lua 原子 claim、取消广播、幂等、自研 PG 队列可靠性 | 已落地 |
| [06-MCP工具体系](docs/06-MCP工具体系.md) | MCP server/client、工具注册、LLM 提参与三态结局 | 已落地；`youcom_search` 等为规划 |
| [07-系统管理与可观测](docs/07-系统管理与可观测.md) | 认证授权、审计、RAG Trace、Dashboard、agents 人设与 Prompt 槽位 | 已落地 |
| [08-前端工程与页面设计](docs/08-前端工程与页面设计.md) | React 工程、蓝色视觉体系、页面规划、REST/SSE 联调、测试与分期 | F0–F4 已落地 |
| [09-CI质量门禁](docs/09-CI质量门禁.md) | Linux/Apple Silicon 后端、Docker 集成、前端 E2E 与真实 RAG 评测门禁 | 已落地 |
| [10-容器化部署](docs/10-容器化部署.md) | 全栈镜像构建、compose 编排、配置项、首个管理员、备份升级与安全基线 | 已落地 |
| [11-人工验收方案](docs/11-人工验收方案.md) | 页面级验收前置、可答/拒答素材、分批勾选清单、证据规范与问题模板 | 已交付 |

## 开发命令

```bash
uv sync                                                   # 安装依赖（虚拟环境由 uv 管理）
uv run --env-file .env uvicorn app.main:app --port 9090   # 启动 API 服务
uv run --env-file .env python -m app.worker               # 启动 PG 队列 worker
uv run python -m mcp_server.main                          # 启动 MCP 工具服务（:9099）
uv run pytest -q                                          # 测试
uv run ruff check .                                       # Lint
```

Docker 一键拉起完整栈（PostgreSQL/pgvector + Redis + MCP + API + Worker + 前端 Nginx）：

```bash
cp .env.docker.example .env.docker             # 修改两个必填密码
docker compose --env-file .env.docker up -d --build
curl -s http://127.0.0.1:9090/health           # API 健康检查
# 浏览器访问 http://127.0.0.1:5173/
```

宿主端口默认避开本机已占用的 5432/6379（PG 映射到 15432、Redis 映射到 16379），
`mcp:9099` 不映射宿主。首个管理员创建、认证启用、备份与回滚步骤见
`docs/10-容器化部署.md`；页面验收的执行顺序与判定标准见 `docs/11-人工验收方案.md`。

前端开发与质量检查：

```bash
cd frontend
npm install
npm run dev                                    # http://127.0.0.1:5173
npm run lint && npm run typecheck && npm run test && npm run build
npm run e2e                                    # 首次运行需 npx playwright install chromium
```

本地 PostgreSQL/pgvector 与 Redis 启动后，可运行不调用外部模型的集成验收。测试会创建并
自动删除随机命名的 PostgreSQL 数据库，不写入开发库：

```bash
RAGENT_RUN_INTEGRATION=1 uv run --env-file .env pytest -m integration -q
RAGENT_DATASOURCE__PASSWORD='<local-password>' uv run python -m scripts.benchmark_m5

# 质量评测：先播种基准语料，再对目标部署跑检索/答案门槛
uv run python -m scripts.seed_eval_corpus --base-url http://127.0.0.1:9090/api/ragent
uv run python -m scripts.evaluate_rag --base-url http://127.0.0.1:9090/api/ragent
```

## 实施顺序与当前进度

按 `00` 文档第 9 节路线图推进：M1 骨架 + 问答主链路 → M2 入库链路 → M3 混合检索增强 →
M4 可编排入库 + MCP + 管理面 → M5 韧性与生产化。

当前状态是 M1、M4、M5 已闭环，M2 以简化分块路径交付，M3 只完成了问题理解、后处理链与
向量通道，混合检索的三条增强通道仍在规划中。生产化部分已补齐全栈容器编排、CI 四类门禁
（后端双平台、PG/Redis 集成、前端 E2E、容器构建）与真实质量工作流；容器化部署的验收数据
见 `docs/10-容器化部署.md` 第 11 节。
