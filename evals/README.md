# RAG 质量回归数据集

`datasets/rag_quality.v3.jsonl` 是当前默认的版本化黄金问题集，共 42 题；其中新增 12 题覆盖跨文档、
三文档、精确边界、否定条件和相似数字消歧。`v1` 保留最初 6 题，`v2` 保留 30 题基线。
`datasets/rag_unanswerable.v1.jsonl` 是独立的 8 题无答案对抗集，不混入事实问答平均分。
每行一个 JSON 对象：

- `id`：跨版本稳定的用例标识；
- `question`：送入 `/rag/eval` 的原始问题；
- `answerable`：默认 `true`；设为 `false` 时表示受控语料无法回答，且 `referenceDocIds` 必须为空；
- `referenceDocIds`：期望命中的业务文档 ID，即导入文件名去掉最后一个扩展名；
- `referenceAnswer`：人工核对过的标准答案，为后续答案正确性评测保留；
- `expectedKeywords`：标准答案应覆盖的原子事实词；单项中用 `|` 分隔允许的同义表达；
- `intentLeafIds`：可选，与每个拆分子问题对应的 top-1 意图叶子 ID；
- `tags`：便于按领域分析，不参与评分。

首次使用时，创建 `collectionName=m5_quality_baseline` 的独立知识库，将 `corpus/` 下
三个 Markdown 文件导入并等待向量化成功。启动 API 后运行：

这一步可以交给播种脚本自动完成，它按 `collectionName` 精确复用或创建知识库，只上传缺失的
语料，对未完成或失败的文档触发分块，并轮询到 `success` 为止；重复执行不会重复建库或重复
分块，可以直接用在全新部署上：

```bash
uv run python -m scripts.seed_eval_corpus
uv run python -m scripts.seed_eval_corpus --base-url https://rag.example.com/api/ragent
```

脚本失败时以非零退出码结束，并打印失败或超时文档名；`--output` 可落盘播种结果 JSON。
Corpus 导入完成后运行：

```bash
uv run python -m scripts.evaluate_rag
uv run python -m scripts.evaluate_rag --with-answers
uv run python -m scripts.evaluate_rag --with-answers --publish-report --label "release-candidate"
uv run python -m scripts.evaluate_rag --judge-answers --publish-report --label "semantic-check"
uv run python -m scripts.evaluate_rag --judge-answers --limit 3 --label "semantic-smoke"
uv run python -m scripts.evaluate_rag --tag hard --with-answers --label "hard-cases"
uv run python -m scripts.evaluate_rag --dataset evals/datasets/rag_unanswerable.v1.jsonl \
  --judge-answers --publish-report --label "unanswerable-check"
```

默认门槛为文档 Hit Rate ≥ 0.8、MRR ≥ 0.7、Context Precision ≥ 0.75、Latency P95 ≤ 5000ms，
任何接口错误也会令进程退出码为 1。默认只做改写、意图和检索，不产生主回答模型费用；
`--with-answers` 会额外复用线上 KB Prompt 和 Chat 路由生成答案，但不创建会话、不写入消息记录。
答案模式默认同时守卫关键事实覆盖率 ≥ 0.90 与完整答案率 ≥ 0.80。需要认证的部署可将管理员原值 token 写入
`RAGENT_EVAL_TOKEN` 环境变量，脚本不会把 token 写进报告。
`--publish-report` 会在全部用例完成后将摘要和逐题结果写入管理端批次档案；即使质量门槛未通过也会
保存报告，便于定位回退。发布动作不保存 API Token、Provider Key 或 Authorization Header。
脚本默认只检索 `m5_quality_baseline`，严格关闭跨库补充召回，避免开发库的其他文档
污染评分。可通过重复传入 `--collection <name>` 评测其他受控集合。

指标口径：

- Doc Hit Rate：期望文档至少命中一个的用例比例；
- Doc Recall：每题期望文档的召回比例均值；
- MRR：第一个相关文档排名倒数的均值；
- Context Precision：召回 Chunk 中属于期望文档的比例；
- Intent Accuracy：提供 `intentLeafIds` 的用例才计入；
- Latency P95：服务端返回的端到端检索耗时 P95。
- Answer Keyword Recall：生成答案覆盖黄金关键事实的比例，先做全半角、大小写和标点归一化；
- Answer Complete Rate：覆盖当题全部关键事实的用例比例；
- Answer Latency P95：仅 Chat 答案生成阶段的 P95，与检索 P95 分开统计。
- Semantic Score：模型裁判结合参考答案与本次召回上下文，对候选答案事实一致性给出的 0–1 评分；
- Semantic Pass Rate：裁判输出 `PASS` 的比例，`PARTIAL` 与 `FAIL` 会在报告中标记为风险用例。
- Unanswerable Abstention Rate：无答案题中明确说明资料不足、没有擅自推断允许或禁止的比例；答案模式
  默认门槛为 `0.80`。
- Unanswerable No Evidence Rate：无答案题经过重排阈值后完全没有 Chunk 的比例，仅观察。召回同领域
  资料并依据其范围说明“未覆盖”仍是正确拒答，不因此扣分。

无答案题不参与正向文档命中、排序与上下文精度门槛；报告中的这些兼容字段按中性通过值记录，管理页
改为优先展示拒答率与无证据率，不能把兼容字段的 `1.0` 解读为“没有召回任何文档”。

`--judge-answers` 隐含启用答案生成，并为每题额外调用一次 STANDARD 档 Chat 模型。默认只记录
Semantic Score/Pass Rate，不影响质量门禁；只有同时传入 `--min-semantic-score <0..1>` 才将平均
语义分数作为退出码条件。模型裁判可能与答题模型同源，存在自我偏好，因此不能替代人工抽检；生产
基线建议固定独立裁判模型后再启用硬门槛。
参考答案定义最低事实要求，不作为答案内容上限；召回上下文支持、且不与参考答案矛盾的补充信息
不应扣分。裁判仅对无依据、矛盾、误导或明显偏题的补充内容降分。
需要先验证模型输出契约或控制试跑费用时，可用 `--limit N` 只执行数据集前 N 题；正式基线不得带
该参数。`--tag <tag>` 只执行包含指定标签的用例；可重复传入，且用例必须同时包含全部指定标签。
筛选先于 `--limit`，因此可用 `--tag hard --limit 3` 对困难集做低成本烟雾检查。

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

同日使用 `--with-answers` 运行最终答案回归：Answer Keyword Recall = `1.0`、
Answer Complete Rate = `1.0`、Answer Latency P95 = `2263ms`；检索指标继续为
Hit/Recall/MRR = `1.0`、Context Precision = `0.9556`、Retrieval P95 = `3144ms`，
30/30 无错误通过全部门槛。

2026-09-12 扩展到 v3 的 42 题。新增 12 题统一标记 `hard`，其中 7 题要求同时召回两到三个文档，
3 题验证“正好等于门槛”时不应误用“超过”规则，其余覆盖时间线归纳、额度对比和相似数字消歧。
批量器同时增加 `--tag` 过滤，便于单独回归困难集。真实运行 `--tag hard --judge-answers`
得到 Hit Rate、Doc Recall、MRR、Answer Keyword Recall、Answer Complete Rate、Semantic Score 和
Semantic Pass Rate 均为 `1.0`，Context Precision 为 `0.9722`，Retrieval P95 为 `3464ms`，
Answer P95 为 `4587ms`，12/12 无错误。报告 `hard-semantic-12` 已写入管理端评测账本。

同日新增 8 题无答案对抗集。首次运行发现空 Chunk 返回空字符串、自然拒答表达漏识别，以及模型将
“资料未提及折现”推断成“不能折现”。修复为空证据明确拒答、可解释的拒答识别，并在在线与评测
知识库 Prompt 后强制追加事实边界后，最终 8/8 正确拒答且语义裁判 8/8 `PASS`；Retrieval P95
为 `3447ms`，Answer P95 为 `2992ms`，No Evidence Rate 为 `0.125`。报告
`unanswerable-final-8-v2` 已写入管理端评测账本。
