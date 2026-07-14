# Week 4 Kickoff — Prompts, Context & The Workflow-Agent Spectrum

> **30 分钟快速启动会材料** | 直接在会议上投屏用

---

## Part 1 — Week 3 Recap: 我们做了个什么？

### Week 3 实际交付的东西

Week 3 把 Week 1 的 `LLMService` + Week 2 的 `RetrievalService` 串进一个 **LangGraph 编排图**，暴露为 `POST /agent/query`：

```
用户 POST /agent/query {"question": "信用卡透支费怎么收的？"}
  ↓
① ingest_input — question → user_query，生成 request_id
② retrieve_phase (asyncio.gather)
   ├── retrieve_docs_tool: embed → ANN 搜索 → DocumentChunk[]
   └── retrieve_structured_tool: product 精确匹配 + narrative ILIKE → ComplaintRow[]
③ analysis_phase — LLM 分析检索结果
④ synthesis_phase — LLM 综合生成答案
  ↓
AgentQueryResponse { final_answer, retrieved_doc_ids, ... }
```

新增了这些文件：

```
app/
├── core/
│   ├── state.py              # AgentState TypedDict + Pydantic re-exports
│   └── graph.py              # build_agent() + AgentRunner
├── tools/
│   ├── retrieve_docs_tool.py
│   ├── retrieve_structured_tool.py
│   ├── summarise_tool.py
│   └── synthesise_answer_tool.py
```

### 但这个不是 "Agent"——复习

Week 3 特意强调过，这里再点一次：

> **Week 3 交付的是一个确定性 RAG pipeline，不是一个自主 agent。** 节点顺序硬编码，没有工具选择，没有条件分支，没有自主决策。它是工厂流水线，不是手工作坊。

### Week 3 埋下的三个问题

Week 3 做完了能回答问题，但代码里有三个明显的"以后要修"的迹象：

**问题 1: Prompt 是散落在 Python 文件里的字符串**

```python
# app/tools/summarise_tool.py 里
prompt = "你是一名金融政策分析师。分析以下检索到的证据...\n\n{evidence}"
# app/tools/synthesise_answer_tool.py 里
prompt = "你是一名消费者权益顾问。基于以下证据综合回答...\n\n{evidence}"
```

这些字符串没法版本对比、没法 review diff、改一个 prompt 要改完整文件。Week 5 的 eval 管道要量化 prompt 质量，如果 prompt 在 .py 里，eval 甚至不知道哪个版本在跑。

**问题 2: Conversation 越长，token 越贵**

`AgentState` 已经在 Week 3 定义了 `conversation_history: list[dict]`（见 `app/core/state.py:30`），Week 3 的 canvas 也要求这个字段从一开始就在 TypedDict 上。但 Week 3 的实际实现**没有消费它**——你问第二遍，它不记得第一遍。

Week 3 的 Wednesday self-check 里有一项专门让你提前想过这个问题：
> *"conversation-history blow-up that's coming next week (think about it now — it's the heart of Week 4)."*

这就是现在要面对的那个问题。到第 10 轮对话，prompt 里塞了 9 轮历史，token 成本翻倍不止。

**问题 3: 检索没有意图驱动**

```python
# app/tools/retrieve_structured_tool.py
# product 和 narrative_keyword 从用户输入直接来
WHERE product = :product AND narrative ILIKE :keyword
# 如果用户没提产品，product=NULL，这行等于废了
```

Week 2 的 v0 合同说 `query` 参数"仅用于日志，不参与过滤"。那是因为 Week 2 还没有能力从用户问题里**提取意图**。现在有了 LLM，可以在检索前先问 LLM："用户问的是什么产品、什么问题类型？"然后用提取结果去检索。

---

## Part 2 — Workflow vs Autonomous Agent

> 为什么 Week 3 是一个 workflow 而不是 agent？这个区别值得专门花时间说清楚。

### 光谱

```
确定性 Workflow                                        自主 Agent
◄─────────────────────────────────────────────────────────►
                                                    
  Week 3 的           加了 scenario        加了 safety      完全自主
  RAG pipeline         分支的 Week 4        审核的 Week 7   工具选择 + 规划
  
  节点固定             按场景走不同路径      条件阻断          自主决定下一步
  没有选择             有限选择              有限选择 + 审核   无限选择
```

### Week 3 为什么是 Workflow

| 特征 | Week 3 | 真正的 Agent |
|------|--------|-------------|
| 节点顺序 | 硬编码：ingest → retrieve → analyse → synthesise | 动态：agent 自己决定先调哪个工具 |
| 工具选择 | 两个检索工具绑定在同一个 phase，全部执行 | 看问题选工具——这个问题需要查 docs 还是查 complaints？还是两个都要？ |
| 条件分支 | 无。无论用户问什么，路径都一样 | 有条件分支：如果检测到安全风险，走阻断路径；如果是退款投诉，走 complaint-letter 路径 |
| 决策能力 | 零。节点只是 LLM 调用 | 有：LLM 决定下一步做什么，LangGraph 的条件边根据 state 内容切换路径 |

**Week 3 的 pipeline 像一个工厂流水线：** 每个产品经过同样的工位，顺序不能变，工位不能跳过。

**真正的 agent 像一个手工作坊：** 接单后看看需要什么，再决定先用车床还是先焊接。

### 为什么先从 Workflow 开始？

因为 **确定性先于自主性**。你还不了解你的数据、你的 LLM 行为模式、你的 token 成本之前，让系统自主决策等于让实习生管公司。先做成线性 workflow，跑通、测量、调优，然后逐步放开控制：

| 阶段 | 控制的松紧 | 你学到了什么 |
|------|-----------|------------|
| Week 3 线性 workflow | 最紧 | 基础设施、状态管理、错误处理 |
| Week 4 + scenario 分支 + prompt 管理 | 中等 | 按意图路由、prompt 版本化、token 成本控制 |
| Week 7 + safety 审核 | 中等 + 护栏 | 安全阻断、条件边 |
| Week 8+ 自主工具选择 | 最松 | 动态规划、工具编排、缓存管理 |

> **行业里有一个共识正在形成：大多数实际落地的 "agent" 其实是 workflow。** 纯自主 agent（工具随便选、步骤随便跳）在目前的 LLM 可靠性下仍然风险很高。你看到的大多数 "agent 框架" 的客户案例，拆开看都是带条件分支的 workflow。知道什么时候该收紧、什么时候该放开的判断力，比会编一个自主 agent 更有价值。

---

## Part 3 — LangChain vs Vanilla API

> Week 3 我们用 LangGraph 做了编排。LangGraph 是 LangChain 生态的一部分。LangChain 这个生态本身在行业里是有争议的。这里把争议摊开来说。

### LangChain 做了什么

LangChain 是一层 **包装**。它把 LLM 调用、prompt 组装、工具调用、向量存储抽象成统一的接口：

```python
# LangChain 风格
from langchain_core.prompts import ChatPromptTemplate
prompt = ChatPromptTemplate.from_messages([("system", system), ("human", "{input}")])
chain = prompt | llm | output_parser
result = chain.invoke({"input": "hello"})
```

```python
# Vanilla API 风格 (我们的 LLMService)
result = await llm.complete(messages=[{"role": "system", "content": system},
                                       {"role": "user", "content": "hello"}])
```

### 争议在哪里

| 支持 LangChain 的理由 | 反对 LangChain 的理由 |
|----------------------|---------------------|
| 统一接口，换 provider 不需要改调用代码 | 抽象层泄漏。每个 provider 的参数细节不同（temperature 叫法、stop token 格式、response 结构），LangChain 的 "统一" 要么丢失细节，要么用一堆 if-else 补救 |
| prompt 模板、output parser、retriever 开箱即用 | 出了问题很难调试。你调的是 LangChain 的代码，不是自己的代码。stack trace 深三层，错误的根因藏在 wrappers 的某个角落里 |
| 社区大，集成多 | 版本升级频繁，API 不稳定。2023 年到 2024 年，LangChain 从 0.0.x 跳到 0.3.x，API breaking change 数次。维护成本被转嫁给了使用者 |
| 快速原型快 | 生产化的时候这些抽象往往是第一个被拆掉的。你最后会发现自己写的调用层比 LangChain 的薄、稳定、好调试 |

### 我们这个 curriculum 的立场

我们用 LangGraph（LangChain 生态的一部分）做图编排，因为 LangGraph 的 StateGraph reducer、checkpointing、条件边机制在同类工具里确实做得好，短期内没有满意的替代品。

但 **LLM 调用层我们用自己的 `LLMService`，不用 LangChain 的 `ChatOpenAI` / `ChatOllama`**。prompt 管理我们用自己的 `PromptService`（Jinja 模板），不用 LangChain 的 `PromptTemplate`。

> **选取有用的抽象，跳过有争议的抽象。** LangGraph 的图模型是好抽象。LangChain 的 LLM 包装层是争议所在——它不是对所有人都适合的选择。你在真实项目中做出这个判断的能力，比背熟任何一个框架的 API 更值钱。

---

## Part 4 — 什么是 Context Engineering？

> 这个术语会在你的职业生涯里反复出现。现在给它一个定义，之后每一周你都会看到这个概念的影子。

### 定义

**Context Engineering** 是指：在 LLM 调用发生之前，对输入上下文进行有策略的**选择、剔除、重组和路由**，使得 LLM 看到的信息是信号密度最高的、token 成本最低的、与当前任务最相关的。

它不是"写 prompt"——prompt engineering 是"怎么写指令"，context engineering 是"给 LLM 喂什么材料"。两个维度正交。

### Context Engineering 的核心操作

| 操作 | 学名 | 通俗说法 | Week 4 的对应 |
|------|------|---------|--------------|
| **Selection** | Context Selection | 从全部可用信息中选出一部分给 LLM | `scenario_phase`：从用户问题里提取 `product_type`、`issue_type`，只检索相关的投诉，不检索全部 1000 条 |
| **Elimination** | Context Elimination / Truncation | 剔除不相关或过期的上下文 | `compress_history`：把 N 轮对话压成一段 summary（剔除低信号轮次），保留最近 2 轮原文 |
| **Reordering** | Context Reordering | 把最重要的信息放在 prompt 的最前面或最后面（LLM 有"lost in the middle"问题） | Prompt 模板设计：证据放在 synthesis prompt 前部，历史放在中部，指令放在末尾 |
| **Routing** | Context Routing | 根据输入内容，决定走哪个子上下文 | 按 `scenario.issue_type` 分支：退款问题用 complaint_letter output，普通查询走 synthesis |
| **Caching** | Prompt Caching / Prefix Caching | 把不变的 system prompt 前缀缓存，避免重复计费 | Week 8 Sub-Task D 做，但 `compress_history` 是前置条件——不压缩的话 prefix 一直在变，没法缓存 |

### 为什么 Context Engineering 从 Week 4 开始？

前 3 周我们故意没管上下文：

| Week | Context 状态 | 为什么不管 |
|------|-------------|-----------|
| 1–2 | 没有 LLM 调用需要上下文（除了 `embed`） | 还没到管的时候 |
| 3 | Prompt 是散落在 .py 里的字符串；`conversation_history` 定义了但不消费 | 先让 pipeline 跑通再说。加了 context 管理出错了你不知道是 context 问题还是 pipeline 问题 |

Week 4 是第一个真正开始关心"LLM 看到了什么"的周。Prompt 字符串集中管理（你才能 diff 每次改了啥）、历史压缩（你才能控制 token 预算）、意图提取（你才知道该喂哪些数据）——这三件事合在一起就是 Context Engineering 在 RAG pipeline 上的落地。

> **行业里有一个共识：prompt engineering 的收益正在边际递减，context engineering 是接下来 2-3 年 GenAI 应用层最有杠杆的工程领域。** Prompt 格式的优化（few-shot 写得好不好、指令清不清晰）能带来的提升已经很有限了。真正拉开差距的是：你往 prompt 里放了什么、你没放什么、你放了之后有没有过期。

### Context Engineering 的 Stage 1 vs Stage 2

| | Stage 1（本周） | Stage 2（Week 8 Sub-Task D） |
|---|---|---|
| 剔除方式 | 对话历史超过 N 轮 → 压缩旧轮 | 意图驱动的动态剔除——"这个问题的上下文只需要上周的 mortgage 记录，不需要昨天的 credit card 记录" |
| 缓存利用 | 无 | Anthropic Prompt Caching / OpenAI Prefix Caching：system prompt 前缀按 cache_group 分组，命中缓存后降 80% cost |
| 检索策略 | `scenario_phase` 提取意图后做精确匹配 | 检索结果也参与 context selection——"搜到了 20 个 chunk，但只有 5 个跟当前意图相关，剩下 15 个不喂给 LLM" |
| 工程复杂度 | 低：一个 compress 节点 + 一个 scenario 节点 | 高：需要 entity resolution、cache group 管理、prompt envelope 分层 |

**Stage 1 不完美但必须做**：没有 Stage 1，Stage 2 的缓存前缀因为历史一直在变而永远无法命中。compress_history 是缓存的前置条件——前缀稳定了，缓存才可能工作。

### 更多阅读

- **Anthropic 的 Context Window Engineering 指南** — 行业里第一个系统化讲 context 管理的文档。提出了"context window 是你最宝贵的资源"这一观点。[Anthropic Context Window Engineering](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering)
- **Prompt Caching 的经济学** — Anthropic 的 prompt_caching 定价：缓存命中后输入 token 成本降 80%-90%。护栏：前缀必须 byte-identical。[Anthropic Prompt Caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
- **Lost in the Middle** — 经典论文，证明 LLM 对长上下文开头和结尾的信息利用率远高于中间。这直接影响了 prompt 模板的设计（证据放前面，指令放后面）。[Lost in the Middle: How Language Models Use Long Contexts](https://arxiv.org/abs/2307.03172)
- **Jinja StrictUndefined** — 我们 prompt 模板的渲染引擎配置。缺失变量直接报错，不静默填空。[Jinja2 StrictUndefined](https://jinja.palletsprojects.com/en/3.1.x/api/#jinja2.StrictUndefined)

---

## Part 5 — Week 4: Prompts & Context Engineering 落地

### 本周要做的三件事

接住 Week 3 埋下的三个问题，一个一个问题解决：

| Week 3 的问题 | Week 4 的解法 | 涉及的新文件 |
|---|---|---|
| Prompt 散落在 .py 里，无法版本对比 | 统一迁到 `app/core/prompts/*.j2`，通过 `PromptService` 加载，`StrictUndefined` 模式 | `app/core/prompt_service.py` + `*.j2` 模板文件 |
| 对话越长 token 越贵，第 10 轮 prompt 比 answer 还长 | `compress_history` 节点：历史 > N 轮时用 ops 模型压缩旧轮，保留最近两轮原文 | `app/core/conversation_compress.py` + `compress_history.j2` |
| 检索没有意图——用户不提 product 就查不到东西 | `scenario_phase` 节点在检索前用 LLM 提取 `Scenario(product_type, issue_type, ...)`，用提取结果路由检索 | `scenario_extraction_tool.py` + `scenario_extraction.j2` |

### 三件事的详细说明

#### ① PromptService + Jinja 模板迁移

```
Week 3 的写法                          Week 4 的写法
                                   
# summarise_tool.py                  # summarise_tool.py
prompt = """你是一名...              prompt = prompts.render("doc_summary.j2", {
  {evidence}}"""                        "evidence": evidence,
                                      })
                                    
                                    # app/core/prompts/doc_summary.j2
                                    你是一名金融政策分析师。分析以下
                                    检索到的证据...
                                    
                                    {{ evidence }}
```

模板文件用 **Jinja2 的 `StrictUndefined`** 模式：模板里用了一个变量但调用时没传 → **直接报错**，不静默填空字符串。这比 f-string 的好处是：

```python
# f-string: 写错了也没人知道
prompt = f"分析以下证据：\n\n{evidenc}"  # 拼写错误 → 变量不存在 → KeyError → 运行时崩

# Jinja StrictUndefined: 启动时就能发现
# 模板里写 {{ evidence }}，调用时传了 evidenc（少个 e）→ PromptService 在加载时直接抛异常
# 不是等用户问到这个 prompt 才崩
```

**为什么不是 f-string？** f-string 在 Python 里是运行时求值的。你的拼写错误只有跑到这行代码才知道。Jinja 模板是文件，git diff 能看到 change，review 能 comment，eval 管道能引用具体版本。

**为什么不是 PEP 750（Template Literals）？** PEP 750 是 Python 3.14+ 才有的提案，还不在稳定版里。Jinja2 现在就可用，生态成熟。

#### ② Conversation Compression

`AgentState` 里已经有 `conversation_history: list[dict]`（Week 3 定义），但 Week 3 没有消费它。Week 4 在 `ingest_input` 后面加一个 `history_compression_phase`：

```
ingest_input
  ↓
history_compression_phase
  ├── len(history) > 5 ?
  │   ├── 否 → no-op，直接过
  │   └── 是 → 调 ops 模型，用 compress_history.j2 压缩
  │       ├── 最近的 2 轮保持原文
  │       └── 之前的轮次 → 一段 summary 字符串
  │       结果写回 state["conversation_history"]
  ↓
safety_phase → scenario_phase → retrieve_phase → ...
```

关键约束（也是常见的坑）：

| 约束 | 为什么 |
|------|--------|
| 阈值 5 是可调的，写在 `Settings` 里 | 3 轮对话的压缩没有意义。5 是 heuristic，应根据 token budget 调整 |
| 保留最近 2 轮原文 | 上一轮的 Q&A 是信号密度最高的上下文，压缩掉了后续回答就无法 grounded |
| 用 ops 模型压缩，不是 synthesis 模型 | `qwen3.5:4b` 压缩 5 条消息的 token 成本远低于 `gemma3:27b`。压缩本身也是 LLM 调用，省钱 |
| 压缩在 prompt 渲染**之前** | 先压缩 `state["conversation_history"]`，再渲染 synthesis prompt。顺序反了会导致 prompt-template 读到的是膨胀后的历史 |

#### ③ Scenario Extraction

这是三件事里思维转变最大的一项。

**Week 2-3 的检索方式：**
```
用户输入 → product=?, narrative_keyword=? → 直接塞进 SQL WHERE
问题：用户没说 product？product=NULL，条件废了
```

**Week 4 的检索方式：**
```
用户输入
  ↓
scenario_phase (新增)
  ├── LLM 读用户问题 → 提取 Scenario
  │   {
  │     "product_type": "Credit card",
  │     "issue_type": "Overdraft fee",
  │     "amount": null,
  │     "jurisdiction": null,
  │     "confidence": 0.85
  │   }
  └── 提取结果写入 state["scenario"]
  ↓
retrieve_phase
  ├── retrieve_docs_tool: embed(query) → ANN（不变）
  └── retrieve_structured_tool: 现在用 scenario.product_type + scenario.issue_type
      WHERE product = :scenario.product_type
      AND (narrative ILIKE :scenario.issue_type OR issue = :scenario.issue_type)
```

**这个变化意味着什么：**

| 之前（Week 3） | 之后（Week 4） |
|----------------|---------------|
| 检索条件**从用户输入直接取**——用户没说就没有 | 检索条件**从 LLM 提取的意图取**——用户没说 product，但 LLM 从上下文推断出是信用卡问题 |
| `narrative_keyword` 是单关键词字符串 | `issue_type` 可以 match Complaints 表的 `issue` 分类字段 + `narrative` ILIKE |
| query 参数仅用于日志 | query 参数终于被用于语义检索了（Week 2 v0 合同的"预留"字段现在用上了） |

**Scenario 提取的失败处理：** LLM 可能输出非法 JSON。方案是有 2 次尝试——第一次用详细版模板（`scenario_extraction.j2`），如果 parse 失败，用简化版模板（`scenario_extraction.simplified.j2`）再试一次。第二次失败就 raise `LLMOutputValidationError`，不走默认值。默认场景会让 retrieval 退回到无差别搜索，比报错更糟糕。

### 本周文件清单

```
app/
├── core/
│   ├── prompt_service.py              # CREATE - Jinja 模板加载器，StrictUndefined
│   ├── prompts/
│   │   ├── doc_summary.j2             # CREATE - 从 summarise_tool 迁出
│   │   ├── compress_history.j2         # CREATE - 对话压缩模板
│   │   ├── scenario_extraction.j2      # CREATE - 场景提取 (详细版)
│   │   ├── scenario_extraction.simplified.j2  # CREATE - 场景提取 (简化版，retry 用)
│   │   └── ... (其他模板文件)
│   ├── conversation_compress.py        # CREATE - 压缩逻辑
│   ├── safety_policy.py               # CREATE - Scenario + SafetyDecision Pydantic
│   └── graph.py                        # AMEND - 加入 scenario_phase + history_compression_phase
├── tools/
│   ├── scenario_extraction_tool.py     # CREATE - 提取 scenario 的 LangGraph 节点
│   ├── retrieve_structured_tool.py     # AMEND - 读 state["scenario"] 代替直接参数
│   ├── summarise_tool.py               # AMEND - prompt 字符串改为 prompts.render()
│   └── synthesise_answer_tool.py       # AMEND - 同上

tests/
├── test_prompt_service.py            # CREATE - 模板加载、变量缺失报错
├── test_conversation_compress.py      # CREATE - 压缩逻辑单元测试
├── test_scenario_extraction.py        # CREATE - 场景提取 + JSON 解析 + retry
```

### 本周 4 个 TODO 的关键思考点

| # | TODO | 你要想清楚的问题 |
|---|------|----------------|
| ① | **Risks** | `StrictUndefined` 在生产中碰到 template-data 不匹配时直接 500，你接受吗？Scenario JSON 解析失败用默认值还是抛异常？compress 阈值设 5 的依据是什么？如果 ops 模型压缩生成的中文 summary 有歧义怎么办？ |
| ② | **Class + flow diagram** | 新的图拓扑：`START → ingest_input → history_compression → safety_phase → scenario_phase → retrieve_phase → analysis_phase → synthesis_phase → END`。safety_phase 本周只定义不 enforce，图上画不画？ |
| ③ | **Trade-offs** | Jinja vs f-string vs PEP 750 template literal、schema-in-prompt 描述 vs JSON mode 参数（哪个更可靠？）、compress 阈值定 5 还是 10、ops 模型选择标准（快 vs 准 vs 便宜？三次每次都要好）、失败时默认 scenario vs raise |
| ④ | **Operations** | 模板文件要先写（编译期检查）、PromptService 要先于所有工具节点初始化、`scenario_phase` 插入在 `retrieve_phase` 之前但不是取代 ingest_input、`compress_history` 的阈值写在 Settings 里 |

### 常见的坑

| 坑 | 看起来什么样 | 怎么避免 |
|----|------------|---------|
| 压缩了最后一条消息 | 用户刚说了"我在加州买的房"，压缩完变成"用户提供了 location 信息"，下次回答不知道在哪个州 | 保持最近 2 轮原文。压缩只覆盖更早的对话 |
| 用 synthesis 模型做压缩 | 每次压缩调用 gemma3:27b，成本 double | 用 ops 模型（qwen3.5:4b），Settings.CHAT_MODEL vs Settings.OPS_MODEL 分开配置 |
| 每次请求都压缩 | 3 轮对话也跑一遍 compress，输出"user said hello, then asked about fees" | 阈值设在 Settings 里，低于阈值 skip |
| 模板忘写 `StrictUndefined` | `{{ misspeld_var }}` 变成空字符串，不报错 | PromptService 构造函数里设置 `undefined=StrictUndefined`，所有模板继承 |
| 工具代码里还留着旧 prompt 字符串 | `synthesise_answer_tool.py` 里有一个旧的 fallback prompt，以为迁完了其实没迁 | Conftest 检查：`app/tools/` 下不应该有超过 3 行的字符串常量 |
| scenario parse 失败用了默认值 | LLM 输出乱码，但系统照常回答，答案文不对题 | 重试一次后仍然失败 → raise。默认值会让用户拿到一个"看似正常但完全无视他问题"的回答，比报错更差 |
| 压缩顺序搞反 | prompt 先渲染再压缩，压缩只改了 state 但 prompt 已经用了旧的历史 | `graph.py` 里 `history_compression_phase` 必须在所有 prompt 渲染的节点之前 |

### 验证命令

```bash
# 本周新增测试
pytest tests/test_prompt_service.py tests/test_conversation_compress.py \
       tests/test_scenario_extraction.py -v

# 全量回归（所有旧测试必须继续绿）
pytest tests/ -v

# 静态检查
ruff check .
mypy --strict app/

# 启动 + 冒烟
docker compose -f infra/docker-compose.yml up -d --build
./scripts/smoke.starter.sh

# 手动验证 - 连续问两次，确认历史被保留
curl -X POST http://localhost:8000/agent/query \
  -H "Content-Type: application/json" \
  -d '{"question": "信用卡透支费怎么收的？", "session_id": "test-1"}'

curl -X POST http://localhost:8000/agent/query \
  -H "Content-Type: application/json" \
  -d '{"question": "我刚才问的是什么？", "session_id": "test-1"}'
# 第二条应该能引用第一条的内容
```

### 本周时间线

> 今天是 **周一 07/13**。Week 4 今天开始。

```
今日(周一 07/13)  周三 07/16         周五 07/18          周日 07/20
   │                 │                  │                   │
   ▼                 ▼                  ▼                   ▼
 打开 canvas       Spec gate          Code PR              Reveal
 填 TODO           分享 canvas         提代码               trainer 放
                   等 sign-off                             destination
```

### 一句话记住 Week 4

> **Week 3 搭了一个能跑但 prompt 散落一地、对话不记忆、检索没意图的 RAG pipeline。Week 4 解决了这三个问题。但比修代码更重要的，是你开始用 Context Engineering 的眼光看系统——这个节点喂了什么、没喂什么、顺序对不对、成本是多少。Prompt engineering 是写指令，context engineering 是选材料。前者是修辞，后者是供应链管理。**