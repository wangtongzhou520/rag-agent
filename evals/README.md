# RAG 质量回归数据集

`datasets/rag_quality.v1.jsonl` 是版本化黄金问题集；每行一个 JSON 对象：

- `id`：跨版本稳定的用例标识；
- `question`：送入 `/rag/eval` 的原始问题；
- `referenceDocIds`：期望命中的业务文档 ID，即导入文件名去掉最后一个扩展名；
- `intentLeafIds`：可选，与每个拆分子问题对应的 top-1 意图叶子 ID；
- `tags`：便于按领域分析，不参与评分。

首次使用时，将 `corpus/` 下三个 Markdown 文件导入同一个知识库并等待向量化成功。启动 API
后运行：

```bash
uv run python -m scripts.evaluate_rag
```

默认门槛为文档 Hit Rate ≥ 0.8、MRR ≥ 0.7、Context Precision ≥ 0.75、Latency P95 ≤ 5000ms，
任何接口错误也会令进程退出码为 1。接口只做
改写、意图和检索，不生成答案，因此不会产生主回答模型费用；Embedding、Rerank、改写和
意图模型仍按当前运行配置调用。需要认证的部署可将管理员原值 token 写入
`RAGENT_EVAL_TOKEN` 环境变量，脚本不会把 token 写进报告。

指标口径：

- Doc Hit Rate：期望文档至少命中一个的用例比例；
- Doc Recall：每题期望文档的召回比例均值；
- MRR：第一个相关文档排名倒数的均值；
- Context Precision：召回 Chunk 中属于期望文档的比例；
- Intent Accuracy：提供 `intentLeafIds` 的用例才计入；
- Latency P95：服务端返回的端到端检索耗时 P95。

## 本地基线与优化结果

2026-09-10 在 Apple Silicon 开发机、Docker PostgreSQL/Redis 与百炼模型配置下运行 6 条。
初始基线为 `Hit Rate=1.0`、`Doc Recall=1.0`、`MRR=1.0`、`Context Precision=0.2`、
`Latency P95=3496ms`、`errors=0`。接入百炼 `relevance_score` 并设置
`ai.rerank.min_score=0.30` 后，同一数据集实测为 `Hit Rate=1.0`、`Doc Recall=1.0`、
`MRR=1.0`、`Context Precision=0.8333`、`Latency P95=3639ms`、`errors=0`。文档命中、
召回和排名未回退，上下文精度提升 0.6333，并通过提高后的 0.75 门槛。
