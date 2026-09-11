# RAG 质量回归数据集

`datasets/rag_quality.v2.jsonl` 是当前默认的版本化黄金问题集，共 30 题；
`v1` 保留最初 6 题基线。每行一个 JSON 对象：

- `id`：跨版本稳定的用例标识；
- `question`：送入 `/rag/eval` 的原始问题；
- `referenceDocIds`：期望命中的业务文档 ID，即导入文件名去掉最后一个扩展名；
- `referenceAnswer`：人工核对过的标准答案，为后续答案正确性评测保留；
- `expectedKeywords`：标准答案应覆盖的关键事实词，当前不参与纯检索评分；
- `intentLeafIds`：可选，与每个拆分子问题对应的 top-1 意图叶子 ID；
- `tags`：便于按领域分析，不参与评分。

首次使用时，创建 `collectionName=m5_quality_baseline` 的独立知识库，将 `corpus/` 下
三个 Markdown 文件导入并等待向量化成功。启动 API 后运行：

```bash
uv run python -m scripts.evaluate_rag
```

默认门槛为文档 Hit Rate ≥ 0.8、MRR ≥ 0.7、Context Precision ≥ 0.75、Latency P95 ≤ 5000ms，
任何接口错误也会令进程退出码为 1。接口只做
改写、意图和检索，不生成答案，因此不会产生主回答模型费用；Embedding、Rerank、改写和
意图模型仍按当前运行配置调用。需要认证的部署可将管理员原值 token 写入
`RAGENT_EVAL_TOKEN` 环境变量，脚本不会把 token 写进报告。
脚本默认只检索 `m5_quality_baseline`，严格关闭跨库补充召回，避免开发库的其他文档
污染评分。可通过重复传入 `--collection <name>` 评测其他受控集合。

指标口径：

- Doc Hit Rate：期望文档至少命中一个的用例比例；
- Doc Recall：每题期望文档的召回比例均值；
- MRR：第一个相关文档排名倒数的均值；
- Context Precision：召回 Chunk 中属于期望文档的比例；
- Intent Accuracy：提供 `intentLeafIds` 的用例才计入；
- Latency P95：服务端返回的端到端检索耗时 P95。

## 本地基线与优化结果

2026-09-10 在 Apple Silicon 开发机、Docker PostgreSQL/Redis 与百炼模型配置下运行 v1 的 6 条。
初始基线为 `Hit Rate=1.0`、`Doc Recall=1.0`、`MRR=1.0`、`Context Precision=0.2`、
`Latency P95=3496ms`、`errors=0`。接入百炼 `relevance_score` 并设置
`ai.rerank.min_score=0.30` 后，同一数据集实测为 `Hit Rate=1.0`、`Doc Recall=1.0`、
`MRR=1.0`、`Context Precision=0.8333`、`Latency P95=3639ms`、`errors=0`。文档命中、
召回和排名未回退，上下文精度提升 0.6333，并通过提高后的 0.75 门槛。

2026-09-11 扩展到 v2 的 30 题，增加同义表达、时间、金额、角色、流程和边界条件，
并为每题补充 `referenceAnswer` 与 `expectedKeywords`。首轮揭示 6 题对阈值校准不充分；
严格限定 `m5_quality_baseline` 且将 `ai.rerank.min_score` 校准为 `0.40` 后，
`Hit Rate=1.0`、`Doc Recall=1.0`、`MRR=1.0`、`Context Precision=0.9556`、
`Latency P95=3401ms`、`errors=0`，30/30 通过默认门槛。
