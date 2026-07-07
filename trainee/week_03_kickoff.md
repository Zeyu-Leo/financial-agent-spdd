# Week 3 Kickoff — The Agent Comes Alive

> **30 分钟快速启动会材料** | 直接在会议上投屏用

> ⚠️ **所有文件都在同一棵目录树下。** 不按周建子文件夹。我们交付的是一个产品，不是 9 个独立作业。

---

## The Big Picture — 培训的两个目标

这个训练营有两层目标，且同等重要：

| 目标 | 含义 | 怎么衡量 |
|------|------|---------|
| **① 交付一个生产级 Agent** | 9 周后你手里的 agent 能自主完成金融消费者问答——自动检索证据、综合分析、生成有依据的答案、通过 eval 评估、处理错误和安全审核 | POST /agent/query 能回答真实 CFPB 问题、eval 管道能量化回答质量、安全审核能拦截越界问题 |
| **② 成为 Context Engineer** | 你带走的是"怎么把模糊需求变成结构化规格"的能力——这是 **Business Analyst + Tech Architect + Developer** 三种角色的融合 | 你自己的 canvas 从 Week 1 到 Week 9 的进化能看出思维深度的跨越 |

> **代码是副产品，思维方式是主产品。** 9 周后你可能会忘记某个 API 的拼写，但你不应该忘记"先写 spec 再写代码"和"每个设计决策都有被拒绝的替代方案"。

---

### 什么是 Context Engineer？

你平时在 Jira 上看到的 ticket 长这样：

> "用户希望 agent 能记住之前说过的话，不要每次问都从头开始。"

这不是一个 engineering task。这是一个**信息密度极低的模糊需求**。它涉及：
- **Business Analysis**：什么是"记住"？记住多久？会话内还是跨会话？记住什么——用户名字、之前的偏好、还是整个对话历史？
- **Tech Architecture**：存哪里——Redis？Postgres 新表？Graph state？存多少——10 轮对话还是 100 轮？满了怎么办——截断还是压缩？
- **Implementation**：改哪个文件？AgentState 加字段吗？LangGraph 节点要改吗？之前有这个设计预留吗？

传统开发模式里，这三个人接力：BA 写需求 → Architect 画设计 → Developer 写代码。每个接力棒都有信息损耗。

**Context Engineer** 是一个人完成这三件事。输入是一句模糊的 Jira 描述（甚至是一句口头需求），输出是一份结构化的 REASONS canvas——有 Risks、Design Decisions、Trade-offs、Operations 步骤，另一个工程师拿到 canvas 能直接写代码。

> **SPDD 本质上就是 Context Engineer 的工作流：** 把一句话需求，变成结构化 spec，再变成代码。先想清楚，再动手。

---

### SPDD vs "Grill Me"——两种不同的"想清楚"

有些同学前两周的感受是：

> "我对着空白的 canvas 不知道填什么。好像必须写出'完美答案'才能通过 gate。"

把两种方式并排放，差异就清楚了：

| | **Grill Me** | **SPDD（我们的方式）** |
|---|---|---|
| 触发方式 | 你写完后别人问问题，你被迫回答 | 一份模板（REASONS canvas）带着问题来找你，你填空 |
| 节奏 | 一次性压力测试："你这里为什么这么设计？" | 分步骤填空：今天填 Risks，明天想 Trade-offs，逐步完成 |
| 产出标准 | "答得上来"就是好 | "填满了"就是好。填的时候发现"这空我不知道怎么填"，本身就比硬填更有价值 |
| 纠错时机 | 写完才知道错了 | 填空的过程中模板就会提醒你："Trade-offs 还没写——你是不是还没想过？" |

**SPDD 本质上是一份填空 checklist，用格式逼迫内容。** 模板问"你的 risks 是什么"，你不得不去想 risks。模板问"trade-offs 是什么"，你不得不去想被拒绝的方案。比起靠别人问问题来推动思考（grill me），SPDD 是你自己对着模板一项一项过。

**而且 spec 不是一天写完的。** 你不需要在周一提交一份完美的 canvas。今天写 Risks，明天补 Trade-offs，后天改 Operations 步骤——canvas 是活的。最终的"完美"发生在周日 reconcile 时，你在 destination 的对比中发现差距，把 spec 更新到当前认知的边界。

> **Grill me 是你写完了，别人来拷打你。SPDD 是模板替别人问了你一遍，你先把能答的答了，答不出的标记下来。最终对答案发生在 reconcile 时，不在周三的 gate 上。（在真实开发中，真正的对答案发生在测试出问题的时候——测试告诉你"你的 spec 和 reality 不一致"，那时你回头改 spec 还是改实现。）**

> **SPDD 不是"你写完了我 grills 你"。SPDD 是你有一份草稿，我帮你看看哪里可能掉坑里。** 区别很大。

---

### Spec-Driven Development 的形态光谱

> 你可能在其他地方见过不同形式的 Spec-Driven Development。这里把它放在一个光谱上，让你看到 SPDD 在哪里。

```
轻量级                                                   重量级
◄─────────────────────────────────────────────────────────►
                                                    
  隐式存放       半结构文档        REASONS canvas         形式化规格
  (CONTEXT.md)   (RFC doc)        ← 我们在这里            (TLA+/Alloy)
  
  无固定模板      按需写            强制模板 + 全部字段     数学验证
  靠默契          靠约定            靠框架思考             靠机器证明
```

四种常见做法：

| 做法 | 长什么样 | 谁用 |
|------|---------|------|
| **隐式存放** | 维护一个 `CONTEXT.md` 或 `CLAUD.md`，记录项目的关键约束和当前状态。RFC 文档不强制，spec 用自然语言散落在代码注释或 PR description 里。 | 小型团队、紧密协作的资深工程师。**信息存放但不强制消费**——有人看就有用，没人看也不阻塞。 |
| **半结构文档** | 按需写 RFC/ADR，解决特定决策时拉一个文档。没有固定模板，自由格式。 | 中型团队，需要记录跨团队决策，但不需要人人都遵循统一的 spec 格式。 |
| **结构化提示词** (REASONS canvas, 我们这里) | 给一个固定模板强迫你问自己：Risks、Entities、Approach、Structure、Operations、Norms、Safeguards。**你不能跳过任何一个字段**。 | 正在学习架构决策过程的人。模板让你"假装会了"直到真的会。对资深工程师来说这其实是很重的方法论——因为它强制你写本可以只在脑子里想的东西。 |
| **形式化规格** (TLA+, Alloy) | 用数学语言描述系统行为，让计算机验证你的设计有没有死锁。 | 分布式系统、共识算法等高风险场景。 |

**SPDD 的位置：它其实是一套很重的方法论。** 相比"在 CONTEXT.md 里记几行关键约束就开写"，REASONS canvas 强迫你把每个设计维度都写成文字——Risks 必须列、Trade-offs 必须写、Operations 必须编号。这在工作节奏快的团队里不是常态。常态是**隐式存放**：维护一个 `CONTEXT.md` 记录当前关键状态，不主动引入 RFC 流程，靠团队默契对齐。

那我们为什么用这么重的方法？因为你正在**学习架构决策**，不是在交付今天的 ticket。模板让你看到"一个完整的决策应该覆盖哪些维度"，哪怕你以后回到隐式存放的模式，你也知道"我脑子里快速过掉的那六个维度叫什么"。

---

## 这个 Agent 到底是什么？—— 最终状态全景

> 有些同学 Week 2 结束时还在困惑："我到底在做什么？" 让我们用当前磁盘上的真实代码和数据说清楚。

### 一句话

这是一个 **金融消费者投诉智能问答 Agent**。你问它 CFPB（Consumer Financial Protection Bureau，美国消费者金融保护局）的政策问题，它从真实投诉数据和政策文档中找到证据，综合生成有依据的答案。

### 这个 agent 的核心优势——为什么它比"直接问 ChatGPT"有用？

| 场景 | 直接问 ChatGPT | 这个 agent |
|------|---------------|-----------|
| "信用卡透支费怎么收的？" | 可能回答通用的透支费定义，但说不清 CFPB（美国消费者金融保护局）的具体规定（因为训练数据截止后条款可能变了） | 从 `overdraft_faq.txt` 检索到 CFPB 原文："one-time debit card transactions cannot be charged overdraft fee unless you opt in"——**答案有来源可查** |
| "有人被 Chase 乱收透支费了吗？" | 无法回答——ChatGPT 不知道用户个人的投诉历史 | 从 `complaints` 表里按 `product='Credit card' AND narrative ILIKE '%overdraft%'` 检索，返回真实投诉案例 |
| "Mortgage escrow account 是什么？公司不给我 refund 怎么办？" | 只能给通用的 escrow 定义 | 从政策文档检索 escrow 定义 + 从投诉检索相似案例——**既有规定又有现实处理结果** |

**简单说：这个 agent 不依赖模型的训练记忆。它每次回答都去查真实数据。政策改了？重新入库就行。投诉更新了？重新跑 ingest。模型可以换，数据是锚点。**

### Agent 能力的演进路线（前 3 周）

| Week | Agent 能做什么 | 还不能做什么 |
|------|---------------|-------------|
| **Week 1** | 调用 LLM 生成文本。能回答"hello world"，但内容全凭模型训练数据 | 没有知识库，问"overdraft fee 怎么收的"只能胡编 |
| **Week 2** | 建了 Postgres 知识库（1000 条投诉 + 3 份政策文档分块），能语义搜索。可以在 REPL 里手动调 `retrieve_docs("overdraft fee", top_k=3)` 看到结果 | **没有 HTTP 端点**。检索能力藏在程序内部，用户无法通过浏览器问问题 |
| **Week 3** | 编排后的 RAG endpoint：用户 HTTP 提问 → 固定 4 步流程（检索文档 + 检索投诉 → LLM 分析 → LLM 综合）→ 返回答案。有状态管理、结构化日志、错误处理 | **不是自主 agent**——节点顺序固定，没有工具选择，没有条件分支。没有多轮对话（Week 4）、没有 prompt 模板（Week 4）、没有 eval（Week 5）、没有安全审核（Week 7） |

### 真实数据长什么样

**投诉数据 (complaints_sample.csv) — 1000 行，4 个产品各 250 行**

每一行是一条真实消费者投诉。字段包含：

| 字段 | 含义 | 例子 |
|------|------|------|
| `complaint_id` | CFPB 投诉编号 | `9999983` |
| `date_received` | CFPB 收到日期 | `2024-09-03` |
| `product` | 产品大类 | `Credit card` |
| `sub_product` | 产品子类 | `General-purpose credit card or charge card` |
| `issue` | 问题分类（issue 分类由 CFPB 定义） | `Getting a credit card` |
| `sub_issue` | 问题子分类 | `Card opened without my consent or knowledge` |
| `company` | 被投诉公司 | `JPMORGAN CHASE & CO.` |
| `state` | 消费者所在州 | `MA` |
| `narrative` | 消费者叙述（自由文本，最长可达数千字，个人身份信息被替换为 XXXX） | `"Chase bank called me about a fraudulent case application..."` |
| `company_response` | 公司的处理结果 | `Closed with explanation` |
| `consumer_disputed` | 消费者是否争议 | `N/A` |

一行真实数据：
```
complaint_id=9999983, product=Credit card, issue="Getting a credit card",
sub_issue="Card opened without my consent or knowledge",
company=JPMORGAN CHASE & CO., state=MA
narrative: "Chase bank called me about a fraudulent case application. They gave me
me a case number XXXX, transferred me CFPB. During the call, long silent when
agent said is looking at the report, then cut off. No call back was done."
company_response: "Closed with explanation"
```

覆盖的 4 个产品各有 5–13 种不同的 issue 类型：Credit card（13 种，含 fees、disputes、marketing 等）、Checking or savings account（5 种，含 closing、managing、low funds 等）、Debt collection（7 种）、Mortgage（5 种，含 struggling to pay、escrow 等）。总计约 30 种 issue 分类，每行都有 narrative 文本。

**政策文档 (raw_docs/*.txt) — 3 份 CFPB 消费者问答，共约 8,800 字符**

`overdraft_faq.txt`（~2,900 字符）— 两个章节：
> "An overdraft occurs when you don't have enough money in your account to cover a transaction, but the bank pays the transaction anyway."
> "For one-time debit card transactions and ATM withdrawals, banks cannot charge you an overdraft fee unless you opt in."

`credit_card_fees.txt`（~2,300 字符）— 两个章节：
> "A credit card's interest rate is the price you pay for borrowing money. This is called the annual percentage rate (APR)."
> "On most cards, you can avoid paying interest on purchases if you pay your balance in full each month by the due date."

`mortgage_servicing_policy.txt`（~3,600 字符）— 两个章节：
> "Your mortgage lender is the financial institution that originally loaned you the money. Your mortgage servicer sends statements and handles day-to-day tasks."
> "An escrow account helps you pay property taxes and insurance through your monthly mortgage payment instead of one big bill."

#### 这些数据在 agent 里怎么被使用？

> 这个问题很多同学 Week 2 做完还在困惑——"我把数据存进数据库了，然后呢？"

这个 agent 的 RAG 流程里，两个知识源各司其职：

**① `retrieve_docs_tool` — 政策文档 (raw_docs/*.txt)**

走 **语义搜索** 路线。用户问题 → LLM.embed(question) → 向量 → 在 doc_embeddings 表里做 ANN 余弦相似度搜索 → 找到语义最相关的 chunks。

```
用户问: "信用卡透支费什么时候可以收？"
  ↓
embed("信用卡透支费什么时候可以收？") → 768 维向量
  ↓
doc_embeddings 表: ORDER BY embedding <=> :query_vec LIMIT 5
  ↓
命中 overdraft_faq.txt#2: "For one-time debit card transactions and ATM withdrawals,
banks cannot charge you an overdraft fee unless you opt in."
```

用途：回答 **政策类问题**——"规定是什么？""我有什么权利？" 语义搜索的优势是用户不需要用精确关键词，用自然语言就能找到相关段落。

**② `retrieve_structured_tool` — 投诉数据 (complaints_sample.csv)**

走 **结构化过滤** 路线。精确匹配 `product` + ILIKE 模糊匹配 `narrative` 关键词。

```
用户问: "信用卡透支费什么时候可以收？"
  ↓
提取过滤条件: product="Credit card", narrative_keyword="overdraft"
  ↓
complaints 表: SELECT ... WHERE product='Credit card' AND narrative ILIKE '%overdraft%'
  ORDER BY date_received DESC LIMIT 10
  ↓
返回 17 条含 "overdraft" 的信用卡投诉，按日期倒序
（注意: query 参数在 v0 仅用于日志，不参与过滤——这是 Task 2 的 v0 合同约定）
```

用途：回答 **案例类问题**——"有人遇到过类似情况吗？公司怎么处理的？" 投诉数据不告诉用户"政策是什么"，但告诉用户"其他消费者遇到同样问题时发生了什么"。

**③ `summarise_tool` + `synthesise_answer_tool` — LLM 综合分析**

两个知识源的检索结果合并后交给 LLM：

```
LLM 收到的上下文：
  【政策依据】overdraft_faq.txt: "banks cannot charge overdraft fee unless you opt in"
  【相似案例】complaint #9997523: "charged overdraft fee without opting in"
  【相似案例】complaint #9998321: "overdraft fee charged despite sufficient balance"

  ↓ LLM 综合分析 ↓

  "根据 CFPB 规定，银行不能对一次性借记卡交易收取透支费，除非你主动 opt in。
   有消费者投诉称即使账户余额充足仍被收费，如果你遇到类似情况，可以向 CFPB 投诉。"
```

**这个流程说明了什么？**

| 知识源 | 检索方式 | 回答什么 | 为什么需要两种 |
|--------|---------|---------|--------------|
| 政策文档 (docs) | 语义搜索 (ANN) | "规定是什么" | 告诉用户**规则** |
| 投诉数据 (complaints) | 精确 + ILIKE 过滤 | "别人遇到过什么" | 告诉用户**现实** |

两种检索合在一起，agent 才能给出既有政策依据、又有现实案例的答案。这就是 **RAG 的核心价值**——不靠模型记忆，靠检索到的真实证据。

#### 我们的知识库到底有多大？—— 诚实的评估

**三个文档合计 8,800 字符**，分块后约 15–20 个 chunks。这和真实产品（比如一个银行客服 agent 背后可能挂了几万页政策 PDF）相比是**极小**的知识库。投诉数据虽然有 1,000 行，但叙事字段都是消费者的个人经历描述，不是政策解释。

**这意味着 Week 3 的 agent 能回答的问题有明确的边界：**

| 能回答 | 不能回答 |
|--------|---------|
| "透支费什么情况下能收？" → overdraft_faq.txt 有答案 | "某个银行的历史收费趋势" → 没有数据 |
| "APR 是什么？怎么免利息？" → credit_card_fees.txt 有答案 | "某个具体投诉的处理结果" → 只有 narrative 描述，没有结构化结果数据 |
| "Escrow account 是什么？" → mortgage_servicing_policy.txt 有答案 | "Debt collection 超过 7 年还能追讨吗？" → 文档里没有 |

这是**故意的**。这个 curriculum 的目的是让你学会 RAG agent 的搭建方法论，而不是做一个覆盖全 CFPB 知识库的产品。**知识少反而让你更快地调试和验证**——你知道 3 个文档里的每一段内容，能精准判断"答案对不对"。

> 真实产品中的 policy 知识库是**包罗万象的**——数千页的监管文件、产品条款、FAQ、历史判例。但搭建方法是一样的。你在这 9 周学会的是"怎么搭"而不是"搭多少"。

#### 真实产品中 policy 文档的角色

在实际的金融客服 agent 中，policy 文档是**核心知识源**，通常包含：
- **监管政策**（Regulation E, Regulation Z, TILA, RESPA 等 — 可以是数万页的 CFR 文档）
- **产品条款**（各银行的信用卡协议、贷款合同、存款账户条款）
- **内部 SOP**（客服人员的手册——"如果用户说 X，你应该查 Y 再做 Z"）
- **FAQ 和知识库文章**（CFPB ask-cfpb 这类消费者问答只是冰山一角）
- **历史判例和投诉处理记录**（类似我们的 complaints_sample.csv，但更大规模）

我们的 3 个文档是**一个极简的采样**，为了让训练营能在 9 周内跑通全链路。方法论是一样的——你在真实工作中拿到的是更大规模但**结构相同**的数据。

### 最终状态（Week 9 完成后）

```
┌── 用户 ─────────────────────────────────────────────────────────────┐
│  curl -X POST /agent/query -d '{"question": "信用卡透支费怎么收的？"}' │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌───────── FastAPI (port 8000) ───────────────────────────────────────┐
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Middleware                                                    │   │
│  │  ├── Request-Id → 每个请求有唯一追踪 ID                        │   │
│  │  ├── Structured Logging → 所有日志携带 request_id             │   │
│  │  └── Error Handler → LLM 错误→502, 其他→500, 都带 X-Request-Id │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  /agent/query  →  AgentRunner.run(user_query="信用卡透支费...")│   │
│  └──────────────────────────┬───────────────────────────────────┘   │
│                             │                                        │
│                             ▼                                        │
│  ┌─── LangGraph StateGraph ────────────────────────────────────┐   │
│  │  ① ingest_input — 把 question 转为内部的 user_query        │   │
│  │  ② retrieve_phase (asyncio.gather, 并行)                   │   │
│  │    ├── retrieve_docs_tool:                                  │   │
│  │    │   embed("信用卡透支费...") → 搜索 doc_embeddings 表     │   │
│  │    │   → 返回 overdraft_faq.txt#3, credit_card_fees.txt#7   │   │
│  │    └── retrieve_structured_tool:                            │   │
│  │        → SELECT FROM complaints WHERE product='Credit card' │   │
│  │          AND narrative ILIKE '%overdraft%'                  │   │
│  │  ③ analysis_phase — LLM 分析检索到的证据                   │   │
│  │  ④ synthesis_phase — LLM 综合证据生成答案                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                             │                                        │
│                             ▼                                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  AgentQueryResponse                                          │   │
│  │  ├── final_answer: "根据 CFPB 规定，信用卡透支费..."         │   │
│  │  ├── retrieved_doc_ids: ["overdraft_faq.txt#3"]             │   │
│  │  └── retrieved_complaint_ids: ["CFPB-9999983"]              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─── Postgres + pgvector ────────────────────────────────────────────┐
│  complaints 表          docs 表              doc_embeddings 表       │
│  ┌──────────────────┐   ┌────────────────┐   ┌──────────────────┐   │
│  │ 1000 rows        │   │ ~30 chunks     │   │ ~30 vectors      │   │
│  │ 4 products × 250 │   │ 600 chars each │   │ 768 dim each     │   │
│  └──────────────────┘   └────────────────┘   └──────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Part 1 — 前两周我们都做了什么

### Week 0 — 环境

```
docker compose up          → FastAPI + Postgres + pgvector
curl /healthz              → 200 OK
```

### Week 1 — Agent 的"大脑"和"神经"

| 交付物 | 类比 |
|--------|------|
| `LLMService.complete()` + `LLMService.embed()` | 大脑皮层 — 能理解和生成语言 |
| `Settings` (pydantic-settings, 3 providers) | 神经系统参数表 |
| 结构化日志 + `request_id` ContextVar + secret 脱敏 | 黑匣子记录仪 |
| `GET /healthz`, `GET /readyz` | 心电监护仪 |
| `LLMProviderError`, `LLMOutputValidationError` | 免疫系统 |
| `ServicesContainer` + FastAPI lifespan | 骨骼 — 所有服务的装配点 |

### Week 2 — Agent 的"图书馆"

两个 CFPB 公开数据源入库：

**投诉数据** — 1000 条真实投诉，CSV → `complaints` 表（UPSERT 幂等）
**政策文档** — 3 份 CFPB Q&A，按 600 字符分块 + embedding → `docs` + `doc_embeddings` 表

`RetrievalService` 提供两种查询能力：
- `retrieve_docs`: 语义搜索（embed query → ANN cosine → 返回 DocumentChunk[]）
- `retrieve_complaints`: 结构性过滤（product 精确匹配 + narrative ILIKE）

**Week 2 结束时的状态：** 知识库就位，Python REPL 可以验证检索。但用户还不能通过 HTTP 提问。

---

## Part 2 — Week 3: 从 RAG 基础设施到 LangGraph 编排

### 核心变化

> **Week 2：你可以手动调 Python 查资料。Week 3：你搭了一个 HTTP 端点，发一个问题拿到一个答案。**

具体来说：`LLMService`（Week 1）+ `RetrievalService`（Week 2）被串进一个 **LangGraph 编排图**，暴露为 `POST /agent/query`。用户发一个问题 → 4 个固定节点（ingest → retrieve → summarise → synthesise）依次执行 → 返回答案。

**⚠️ 但这不是"agent"。** 这是一个 **确定性 RAG pipeline**——节点顺序固定，没有工具选择，没有条件分支，没有自主决策。"Agent"的定义是能自主选择工具、规划步骤、动态调整策略。这个训练营里真正的 agentic 行为（safety 判断、scenario 分支、tool 选择）从 Week 7 才开始引入。Week 3 交付的是一个**编排后的 RAG endpoint**，不是自主 agent。

> **为什么先说清楚这个？** 因为"agent"这个词在行业里被用得太多，含义模糊。Week 3 你做的具体事情是：把三个服务（LLM、Retrieval、合成的 Prompt）用 LangGraph 串成一个线性流程，加了状态管理和错误处理。做成这件事之后，后面加条件分支、加工具选择、加安全审核——每次加一个维度，才逐步逼近真正的"agent"。

### 本周交付物一览

| 层次 | 文件 | 做什么 |
|------|------|--------|
| **状态定义** | `app/core/state.py` | `AgentState` TypedDict（10 个字段）+ 从 Task 2 re-export DocumentChunk / ComplaintRow |
| **4 个工具节点** | `app/tools/retrieve_docs_tool.py` | 调用 `RetrievalService.retrieve_docs` |
| | `app/tools/retrieve_structured_tool.py` | 调用 `RetrievalService.retrieve_complaints` |
| | `app/tools/summarise_tool.py` | `LLMService.complete()` 分析检索结果 |
| | `app/tools/synthesise_answer_tool.py` | `LLMService.complete()` 综合答案 |
| **图编排** | `app/core/graph.py` | `build_agent()` → 4 个节点 → `AgentRunner` 包装 |
| **HTTP 端点** | `app/api/main.py` (amend) | `POST /agent/query`, 502/500 错误处理 |
| **测试 × 7** | 4 个单节点测试 + `test_graph.py` + `test_agent_query_endpoint.py` | 单元 + 端到端 + 错误路径 |
| **冒烟** | `scripts/smoke.starter.sh` (adopt) | /healthz + /readyz + /agent/query |

### 本周 4 个 TODO 的关键思考点

| # | TODO | 作为 Context Engineer 你要想清楚的问题 |
|---|------|--------------------------------------|
| ① | **Risks**（至少 3 个） | state-merge 语义（两个节点写同个字段，reducer 谁赢）、图编译时机（lifespan vs per-request）、错误跨节点传播（retrieve 节点 LLM 挂了 synthesis 怎么办）、HTTP 状态码契约（502 vs 500 分别对应什么） |
| ② | **Class + flow diagram** | 两个图：classDiagram 看静态关系（类之间怎么连接），flowchart 看动态流程（数据怎么流动）。flowchart 是 code review 的核心 artifact。 |
| ③ | **Trade-offs**（至少 3 个） | TypedDict vs Pydantic、并行 vs 串行检索、inline prompt vs 模板化、lifespan 一次构建 vs FastAPI DI |
| ④ | **Operations 3–9** | 从 Method signatures + File layout 推导执行顺序。工具节点要先于 graph.py。端点要先于测试。 |

### 最容易踩的坑

| 坑 | 怎么避免 |
|----|---------|
| 直接修改 state（`state["x"] = ...; return state`） | 返回 partial dict。`return {"retrieved_docs": ...}` |
| 合成前没等检索完成 | 图的边顺序是契约。synthesis 只在检索之后运行 |
| 忘了设 X-Request-Id 响应头 | Middleware 在每个响应（成功或错误）都设这个头 |
| 从 API 返回原始 AgentState | 映射到 AgentQueryResponse Pydantic 再返回 |
| 节点吞 LLMProviderError | 让错误透传到 FastAPI handler → HTTP 502 |
| 每请求重新编译图 | 在 lifespan 编译一次，存到 ServicesContainer |

### 这个 Agent 的开发流程——Context Engineer 的工作循环

> 这不是"写代码前的繁文缛节"。这是 Context Engineer 的核心工作流。

Week 1–3 你一直在做同一套循环。让我们把它的本质说清楚：

```
Jira/口头需求                          .trainee.md                 代码
 "用户希望 agent                     ┌──────────────┐            ┌────────┐
  能查信用卡收费"                      │ Risks        │            │ 实现   │
         │                         │ Trade-offs   │──────────→ │       │
         ▼                         │ Design dec.  │  实现       │       │
  ┌──────────────┐                 │ Operations   │            └────────┘
  │ 分析 + 拆解   │──────────────→ │ Safeguards   │                │
  │ BA + Arch    │  Context        └──────────────┘                │
  │ + Dev 融合   │  Engineer          │                            │
  └──────────────┘  的产出            │ 周三 gate                  │
                                      │                            │
                                      ▼                            ▼
                                 mentor 检查                  代码 PR →
                                 "这里风险没覆盖"              mentor review
                                 "这个 trade-off                "跟 spec 一致"
                                 少考虑了一个方向"               "测试覆盖了"
```

**这不是 SPDD 独有的。** 任何 Spec-Driven Development 方法都在做同一件事：

| 变体 | 怎么做 | 角色 |
|------|--------|------|
| **BDD** (Behavior-Driven Dev) | `Given/When/Then` 场景描述 | QA + Dev 协作 |
| **TDD** (Test-Driven Dev) | 先写测试，再写实现 | Developer |
| **API-first** (OpenAPI/Smithy) | 先定义接口契约，再实现两端 | API Designer + Backend/Frontend |
| **SPDD** (我们这里) | REASONS canvas 覆盖 Risks → Trade-offs → Operations 全链路 | **Context Engineer** (BA + Arch + Dev 合一) |

**共同点：** 先想清楚再动手。不同的只是"想清楚"的粒度和形式。

**不同点：** SPDD 要求 Context Engineer 同时具备 BA 的分析能力、Arch 的设计视野、Dev 的实现直觉。这是这个训练营真正想让你带走的能力——不只是"会用 LangGraph"，而是"拿到一个模糊需求，知道从哪里开始想，怎么把它变成可执行的 spec"。

### 验证命令

```bash
# 确保数据已入库（Week 2 的产出）
python -m data_pipelines.ingest_tables.ingest_public_data
python -m data_pipelines.ingest_docs.embed_starter_docs

# 跑测试
pytest tests/test_state.py tests/test_retrieve_docs_tool.py \
       tests/test_retrieve_structured_tool.py tests/test_summarise_tool.py \
       tests/test_synthesise_answer_tool.py tests/test_graph.py \
       tests/test_agent_query_endpoint.py -v

# 静态检查
ruff check .
mypy --strict app/

# 启动 + 冒烟
docker compose -f infra/docker-compose.yml up -d --build
./scripts/smoke.starter.sh
```

### 本周时间线

> 今天是 **周日 07/06**。Week 3 **明天（周一 07/07）开始**。这是你的时间线：

```
周一 07/07    周三 07/09         周五 07/11          周日 07/13
   │              │                  │                   │
   ▼              ▼                  ▼                   ▼
 打开 canvas    Spec gate          Code PR              Reveal
 填 TODO        分享 canvas         提代码               trainer 放
                等 sign-off                             destination
```

注意：周日 07/13 是 destination reveal 日。届时你会拿到完整版 `Task_3_Orchestration.md`，对比自己的 `.trainee.md` 做 reconcile diff。

### 一句话记住 Week 3

> **Week 1 让你能调 LLM。Week 2 让你能查知识库。Week 3 把它们串成一个 HTTP endpoint——发一个问题，走完检索→分析→合成的固定流程，拿到一个有依据的答案。这不是一个自主 agent，这是一个编排好的 RAG pipeline。后面 6 周，每次加一个维度（多轮对话、prompt 模板、eval、安全审核），它才逐步变成真正的 agent。**