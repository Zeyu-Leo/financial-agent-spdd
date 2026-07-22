# Week 5 Kickoff — Evaluation, LLM-as-Judge & Tracing

> **30 分钟快速启动会材料** | 直接在会议上投屏用 | 中文

---

## Part 1 — Week 4 Recap: 我们做了什么？

### Week 4 实际交付的东西

Week 4 解决了 Week 3 埋下的三个问题：

| Week 3 的问题 | Week 4 的解法 |
|---|---|
| Prompt 散落在 `.py` 里，无法版本对比 | 统一迁到 `app/core/prompts/*.j2`，通过 `PromptService` 加载，`StrictUndefined` 模式 |
| 对话越长 token 越贵，第 10 轮 prompt 比 answer 还长 | `compress_history` 节点：历史 > 5 轮时用 ops 模型压缩旧轮，保留最近 2 轮原文 |
| 检索没有意图——用户不提 product 就查不到东西 | `scenario_phase` 节点在检索前用 LLM 提取 `Scenario(product_type, issue_type, ...)`，用提取结果路由检索 |

新增的核心文件：

```
app/
├── core/
│   ├── prompt_service.py       # Jinja 模板加载器，StrictUndefined
│   ├── prompts/*.j2            # 5+ 个模板文件
│   ├── safety_policy.py        # Scenario + SafetyDecision Pydantic
│   ├── conversation_compress.py # 对话压缩 helper
│   └── graph.py (AMEND)        # 加入 scenario_phase + history_compression_phase
├── tools/
│   ├── scenario_extraction_tool.py   # 场景提取工具
│   ├── retrieve_structured_tool.py   # AMEND: 读 state["scenario"]
│   └── summarise_tool.py / synthesise_answer_tool.py  # AMEND: prompt 字符串 → render()
```

### 回顾：Context Engineering 是什么？

Week 4 引入的核心概念是 **"LLM 看到了什么"**：

> **Prompt engineering 是写指令。Context engineering 是选材料。** 前者是修辞，后者是供应链管理。

Context Engineering 的四个核心操作：

| 操作 | Week 4 的对应 |
|------|-------------|
| **Selection** — 从全部可用信息中选出一部分给 LLM | `scenario_phase`：只检索相关的投诉 |
| **Elimination** — 剔除不相关或过期的上下文 | `compress_history`：把 N 轮压成一段 summary |
| **Reordering** — 把最重要的信息放在 prompt 的相关位置 | 模板设计：证据放前面，指令放末尾 |
| **Routing** — 根据输入内容走不同的子上下文 | 按 `scenario.issue_type` 分支路由检索 |

Week 4 是 **Stage 1**。Week 8 的 Sub-Task D 会做 Stage 2（意图驱动的动态剔除 + Prompt Caching）。

### Week 4 你完成了 4 个 TODO

| # | TODO | 对应 canvas 位置 |
|---|---|---|
| ① | **Risks** — 至少 4 个，覆盖 JSON 解析、枚举映射、模板耦合、conversation 膨胀 | 模板里标注的位置 |
| ② | **Class diagram** — PromptService + Templates + Scenario + 压缩 helper + graph 节点 | 设计要求画 |
| ③ | **Trade-offs** — 至少 4 个，Jinja vs f-string、strict undefined、retry 预算、阈值策略 | Approach 里有提示 |
| ④ | **Operations** — 从 PromptService → 模板 → ScenarioExtractionTool → compress → 测试 | 分步执行 |

---

## Part 2 — 为什么需要 Week 5？

### 一个真实的教训

我曾花两周优化 prompt：改措辞、调温度、加 few-shot。手动验证了几个问题，回答漂亮，逻辑清晰。自信 deploy。

上线次日，用户反馈回答变差。

我无法判断是 prompt、检索、chunk 还是 edge case 的问题。**没有测量，只能猜测。**

又花了一周验证三种 hypothesis，全部错误。最后加了一个简单的 eval pipeline——跑 20 个场景，打 3 个分数——才发现根因是 embedding 模型换版本后向量分布偏移，检索召回率从 0.7 降至 0.3。与 prompt 无关。

**两周的 prompt 优化，在 eval 面前毫无意义。**

### Hello World Agent vs Production Agent

能运行的 agent 不等于产品。API 调用、LLM 调用、LangGraph node——这些 demo 都会。**demo 和产品之间隔着一整条 eval pipeline。**

```
                         Hello World Agent:
                   "我调通了 LLM，它能回答问题 🎉"
                   → 试了 3 个问题，都答对了
                   → 你相信它工作

                                vs

                        Production Agent:
             "agent faithfulness 0.72，上个月是 0.78"
                   → 跑了 30 个场景，13 个退步
                   → 你知道哪里退步了
```

### 你此刻的位置

前四周交付的 agent 具备完整能力：RAG pipeline、版本化 prompt、对话压缩、意图提取。

**但你无法测量它。** 改一行 prompt 无人知好坏。换一个 embedding 无人知升降。demo 表现良好，edge case 无人覆盖。

> **这周跑完 eval 你会看到低分。** 可能只有 0.3-0.5。
>
> 那不是代码的问题。Week 2 的 RAG 是故意 naive 的——600 字固定 chunk、ILIKE 关键词匹配、无 metadata 筛选。Week 4 的 prompt 无法弥补检索缺陷。
>
> Week 5 只测量，不修改。Week 6 才是修复周。

### 没有 eval 的项目只完成了一半

> **没有 eval 的 agent 开发，就像编译器没有测试套件。编译通过 hello world——你敢放到生产环境吗？**

没有 eval pipeline 的 agent 项目：
- "看起来好"和"实际上好"之间隔着一层雾
- 代码审查缺乏量化依据
- 线上问题只能靠日志 + 直觉定位
- PR review 说不出"这个改动从 0.78 降到了 0.72"

**项目做到 70% 卡在 corner case——不是能力问题，是缺少可观测性。**

从这周开始，你将拥有三样东西：
1. **Offline Evaluation Pipeline** — 批量跑场景，逐条打分
2. **LLM-as-Judge** — faithfulness / task_success / safety_handling
3. **Tracing** — 每个失败场景可追溯至节点级输入输出

这三样合在一起，是从"写代码"到"做工程"的分水岭。

### Week 5 的答案

```
test_scenarios.yaml (≥10 个场景)
    ↓
run_agent_batch.py   ──  跑一轮 agent，产生 JSONL 记录
    ↓
llm_as_judge.py      ──  LLM 当裁判，打分
    ↓
report.py / compare_reports.py  ──  生成可读的 Markdown 报告 + 比较
```

三个 CLI 工具，三个步骤，纯离线。不加 online 反馈、不加 UI、不加 CI/CD（那是 Week 7 的事）。

---

## Part 3 — Week 5 要做的四件事

### ① Author 功能场景（YAML）— ≥10 个

`data_pipelines/eval/test_scenarios.yaml` — 这是本周最重要的文件。

Canvas 要求 **≥10 个**功能场景（destination 会揭示 15+ 个成品版本）。覆盖三个产品线，每个品类至少 3-5 个：
- overdraft / checking_or_savings
- credit_card / late_fee / apr_dispute
- mortgage / escrow / servicer_change

每个场景包含 `id`、`user_question`、`tags`、`notes`（提示正确答案应该引用什么来源）。

**关键思维：** 有些场景要故意选那些"当前 RAG v0 回答不好的"。比如涉及账户关闭（cohort retrieval）、债务追收（debt collection misconduct）、困难补助（hardship）的问题——这些在当前数据下回答不会太好。**但这是功能——不是 bug。** 你要在报告里明确标出 "Baseline RAG v0" 的分数，Week 6 的数据质量改进之后才能看到提升。没有这些"难场景"，基线看起来会虚假地好看。

### ② LLM-as-Judge 裁判

`data_pipelines/eval/llm_as_judge.py` + `app/core/prompts/judge_rubric.j2`

裁判读一条 run record，用三个维度打分：

| 维度 | 分数范围 | 含义 |
|------|---------|------|
| Faithfulness | 0.0–1.0 | 答案中的每个主张是否都有检索证据支撑 |
| Task Success | 0.0–1.0 | 答案是否直接回答了用户问题 |
| Safety Handling | 0.0–1.0 | 功能场景默认为 1.0（不做过度拒绝） |

另外还有一个 `failure_source_label` 枚举，标注失败根源：
`retrieval_miss`、`bad_chunk_boundary`、`missing_metadata`、`csv_field_noise`、`prompt_or_reasoning_issue`、`safety_policy_gap`

**关键约束：** `temperature=0.0` + `response_format="json"`。裁判不能自由发挥。

**Judge 稳定性：** 即使 `temperature=0.0`，identical 场景跑多次仍会有 ~5% 的分数波动。destination 会揭示 `--repeats 3`（每个场景判 3 次取中位数 + 输出 stdev）。Canvas 留给你自己先想解决方式。

### ③ Tracing（可观测性）

`app/observability/tracing.py` — 一个薄的 OTel shim。

- 如果设置了 `LANGSMITH_API_KEY` → 用 LangSmith
- 如果设置了 `PHOENIX_COLLECTOR_ENDPOINT` → 用 Phoenix
- 都没设 → no-op

每次 `/agent/query` 调用产生一条 trace，span 根节点携带 `request_id`。tracing 在 FastAPI lifespan 里初始化。

**为什么这周做 tracing？** Eval pipeline 能回答"哪个场景失败了"，但无法回答"为什么失败"。trace URL 让每个失败场景可以追溯到节点级输入输出，是 eval 的必要补充。

### ④ Compare Reports（CI Gate 的前身）

`data_pipelines/eval/compare_reports.py`

读两份 judged JSONL（baseline + candidate），输出 markdown delta 报告，当某个指标跌破阈值时 exit code 非零。

Week 7 会把这个包装成 GitHub Actions workflow。本周只需实现脚本即可，不做 CI 封装。

---

## Part 4 — 本周 4 个 TODO

| # | TODO | 你要想清楚的问题 |
|---|------|----------------|
| ① | **Risks** — 至少 3 个 | Judge 非确定性（temperature=0 也会波动）、Judge 对长证据的偏见、阈值门掩盖真实回归、场景覆盖 vs 数据特征的关系 |
| ② | **Class diagram** — TestScenarios、ScenarioYaml、RunRecord、JudgedRecord、三个 CLI、Thresholds | JudgedRecord 继承 RunRecord；箭头方向：谁 produces 谁，谁 reads 谁 |
| ③ | **Trade-offs** — 至少 3 个 | 单 LLM judge vs 集成投票、JSONL vs Parquet、Markdown report vs HTML dashboard、阈值门放在 CI 的哪个位置 |
| ④ | **Operations** — 8 个 TODO 步骤 | Canvas 的步骤顺序：场景 YAML（pinned）→ rubric（pinned）→ run_agent_batch → llm_as_judge → report → compare_reports → tracing → 测试 → README → verify |

---

## Part 5 — 常见坑

| 坑 | 看起来什么样 | 怎么避免 |
|----|------------|---------|
| 为了好看而改场景 | "这个场景 agent 答不对，我改一下 YAML 让答案对得上" | **"不要为了让 agent 通过而编辑 test_scenarios.yaml。"** 场景是契约，不是 agent 的附属品 |
| 让法官调 agent | 发现 faithfulness 低，开始改 prompt 模板来刷分 | 改 prompt 是 Week 4 的事。Week 5 只测量不修改 |
| 用 synthesis 模型当法官 | 法官调用用的是 gemma3:27b，成本高 | Judge 走 LLMService.complete，跟 chat 模型同通道。降模型可能导致 JSON 解析失败 |
| commit 了输出文件 | `runs/` 或 `reports/` 进了 git | `.gitignore` 里加 `data_pipelines/eval/output/`。输出是运行时产物，不是代码 |
| tracing 失败但静默忽略 | 设了 `LANGSMITH_API_KEY` 但 SDK 连不上，没人知道 | 必须写 warning 日志：`event="tracing_unavailable"` |
| 一次跑全量场景 | 每次调试都跑全量，等 5 分钟 | 用 `--limit 1` 或 `--tags overdraft` 过滤。只有最终验证才跑全量 |

---

## Part 6 — 本周时间线

> 今天是 **周一**。Week 5 今天开始。

```
今日(周一)        周三                 周五                  周日
   │                │                   │                    │
   ▼                ▼                   ▼                    ▼
 打开 canvas      Spec gate           Code PR               Reveal
 填 TODO          分享 canvas          提代码                trainer 放
 理解 3-CLI 流程   等 sign-off                               destination
 开始写 YAML 场景
```

### 验证命令

```bash
# 编写场景
python -c "from data_pipelines.eval.test_scenarios import validate; validate()"

# 跑 batch（全量）
python -m data_pipelines.eval.run_agent_batch

# 裁判打分
python -m data_pipelines.eval.llm_as_judge --run data_pipelines/eval/output/run_*.jsonl

# 出报告
python -m data_pipelines.eval.report --run data_pipelines/eval/output/run_*.judged.jsonl

# 查看基线
cat data_pipelines/eval/output/report.md | head -n 40

# 全量回归
pytest tests/ -v
ruff check .
mypy --strict app/
```

---

## 一句话记住 Week 5

> **没有 eval 的 agent 是 hello world，有 eval 的 agent 才是产品。**
>
> Week 4 让你的 agent 变得"会说"。Week 5 让你的 agent 变得"可测量"。这周你会第一次看到你写的系统的真实分数——可能很低。那不是失败，那是你第一次获得真实可见的反馈。**从这周开始，每一次 commit 都要回答一个问题：它比上次好，还是差？答不出这个问题，项目只完成了一半。**
