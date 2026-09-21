# Customer Service Agent Documentation Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从项目目标重新建立客服 Agent 的总设计和规范文档，并删除当前仅用于演示的实现代码，避免继续围绕特殊案例给协议打补丁。

**Architecture:** 系统分为自然语言理解、Harness 信任边界、案件级 Router、声明式 Workflow Definition、确定性 Workflow Engine 和可信工具六层。模型输出通用的用户提议，Workflow 决定提议如何解析为已确认 Slot、候选集合、澄清或工具输入；Engine 只执行经过校验的结构化事件。

**Tech Stack:** Markdown 规范文档、JSON 示例、JSON Schema 作为后续实现参考；本次不保留 Python Demo 运行时代码。

**Spec:** `docs/architecture-overview.md` 及本计划中定义的文档边界。

## Global Constraints

- 文档必须区分静态 Definition、动态 Workflow Instance、用户提议、已确认 Slot、派生 Artifact 和副作用历史。
- 模型不得生成 Workflow 跳转、revision、权限结论、工具调用或可信业务结果。
- 单值 Slot 不能接收多个候选值；多个候选必须保留为未解决提议，直到 Workflow Policy 解析。
- `slot_change`、用户回答和业务意图是输入语义，不是 Engine 已执行的结果。
- 修改已有输入后，Engine 根据依赖图和 Policy 计算失效与重算，不由模型指定节点。
- 文档中的数组字段必须声明元素类型，引用的对象类型必须有完整字段说明。
- 本次删除 `src/`、`tests/`、`skills/`、`workflows/`、`schemas/` 和 Python 项目配置；保留 Git、docs 和锁文件，除非后续明确要求恢复实现。

## Review Focus

- 用户一次表达确定值、多个候选和无法确认时，系统是否保留提议而不是错误写入 Slot；测试：`docs/conversation-test-cases.md` 的 `INTERACTION-005` 和 `INTERACTION-006`。
- 用户修改已确认输入后，旧 Artifact、确认和副作用是否按依赖与 Policy 失效；测试：`FLIGHT-002`、`REFUND-003`、`REFUND-006`。
- 当前 Workflow 中出现第二个业务目标时，模型是否只报告目标，Router 是否决定继续、恢复、新建或并行；测试：`INTERACTION-004`。
- 可信字段、身份认证和不可逆副作用是否只能由 Engine/Tool 产生；测试：`REFUND-002`、`SAFETY-001`。
- 旧 revision、旧 interaction 和过期选项是否 fail closed；测试：`SAFETY-002`、`SAFETY-003`、`FLIGHT-004`。

---

### Task 1: Write the architecture overview and project README

**Files:**
- Create: `README.md`
- Create: `docs/architecture-overview.md`
- Modify: `docs/superpowers/plans/2026-09-20-rebuild-customer-service-agent.md`

**Interfaces:**
- Produces the canonical terms and layer boundaries used by every later document.

- [ ] **Step 1: Define the product goal and non-goals**

Document that the project builds a reliable SOP-driven customer service agent, not a free-form chatbot or an LLM-controlled workflow executor.

- [ ] **Step 2: Define the canonical runtime model**

Document `Case`, `Workflow Instance`, `Proposal`, `Slot`, `Artifact`, `Pending Interaction`, `Effect`, `Revision`, and `Audit Event`, including which component owns each object.

- [ ] **Step 3: Define the message-to-execution pipeline**

Use this normative flow:

```text
user message
  → model interpretation
  → Harness validation
  → Proposal / Intent / Ambiguity
  → Router or Workflow Engine
  → state transition / tool effect / next interaction
```

- [ ] **Step 4: Write README usage and document map**

README must explain project status, the CLI/demo deletion, document entry points, and the two stress-test domains: refund and flight booking.

- [ ] **Step 5: Review terminology consistency**

Search all docs for `Interpretation Result`, `accepts`, `slot_change`, `ambiguity`, and `new_intent`; record canonical meanings in the overview before later rewrites.

### Task 2: Rewrite the model interaction protocol

**Files:**
- Modify: `docs/model-interaction-protocol.md`

**Interfaces:**
- Consumes: canonical proposal model from `docs/architecture-overview.md`.
- Produces: model request and model candidate response contracts for Harness implementers.

- [ ] **Step 1: Define input context as a typed view**

Specify `utterance`, `conversation_context`, `pending_interaction`, `allowed_slots`, `intent_catalog`, and `allowed_interaction_acts` with element types and field semantics.

- [ ] **Step 2: Replace case-specific output actions with generic proposals**

Define a candidate structure with target, candidates, relation, commitment, and raw evidence. Keep current ask response, Slot correction, and business intent as separate semantic categories only where downstream routing requires them.

- [ ] **Step 3: Define candidate resolution semantics**

Cover one value, `any_of`, `all_of`, uncertain, unable to answer, and conflict without adding a new enum for each business scenario.

- [ ] **Step 4: Define model limitations**

Explicitly prohibit workflow IDs, node jumps, revision values, tool calls, trusted identity/eligibility results, and policy decisions.

- [ ] **Step 5: Add examples for the stress cases**

Include “明天后天都行”, “小米粥或者米饭吧，我记不得了”, mid-flow correction, multi-field answer, yes/no, and a second business intent.

### Task 3: Rewrite Harness, Workflow Definition, and Engine protocols around proposals

**Files:**
- Modify: `docs/harness-interpretation-protocol.md`
- Modify: `docs/workflow-definition-spec.md`
- Modify: `docs/workflow-engine-protocol.md`

**Interfaces:**
- Consumes: model candidate contract and canonical runtime model from Tasks 1–2.
- Produces: deterministic handoff contracts for Router and Engine.

- [ ] **Step 1: Define Harness responsibilities**

Harness validates references, source grounding, Slot types, cardinality, permissions, current interaction, and revisions; it never chooses a workflow path on behalf of Engine.

- [ ] **Step 2: Define Workflow Definition semantics**

Document Slot value contracts, candidate/cardinality policies, Artifact dependencies, node inputs/outputs, ask presentation, policies, effects, and correction behavior.

- [ ] **Step 3: Define Engine state transitions**

Document how Engine receives proposals, resolves them through Definition Policy, stores unresolved candidates, invalidates dependent Artifacts, and emits new interactions or effects.

- [ ] **Step 4: Remove duplicated model-schema explanations**

Harness must link to the model protocol for model I/O and focus on validation and compilation. Engine must link to Harness for interpretation and focus on deterministic commands and state.

- [ ] **Step 5: Check cross-document vocabulary**

Every use of `accepts`, `kind`, `answer`, `slot_change`, `ambiguity`, `pending_interaction`, and `Interpretation Result` must have one consistent meaning.

### Task 4: Rewrite examples and test scenarios as specification fixtures

**Files:**
- Modify: `docs/conversation-test-cases.md`
- Modify: `docs/workflows/flight-booking-v1.md`
- Modify: `docs/workflows/refund_request.md`
- Modify: `docs/workflows/subscription_cancellation.md`
- Delete: `workflows/flight_booking.v1.design.json`
- Delete: `workflows/refund_request.json`
- Delete: `workflows/subscription_cancellation.json`

**Interfaces:**
- Consumes: canonical Definition and proposal semantics from Tasks 1–3.
- Produces: reviewable scenario fixtures; no executable Python dependency.

- [ ] **Step 1: Convert flight booking to a proposal-aware example**

Show A/B/C provided in one message, date correction, candidate dates, stale quote invalidation, and confirmation.

- [ ] **Step 2: Convert refund to a security-aware example**

Show account mismatch, OTP, identity revalidation after phone change, playback/history checks, iOS routing, and eligibility failure.

- [ ] **Step 3: Convert subscription cancellation to a side-effect example**

Show confirmation, refusal, cancellation of current interaction, idempotency, and tool failure.

- [ ] **Step 4: Ensure every test case states the expected proposal, Engine input, final state, and forbidden effect**

### Task 5: Remove the old implementation and validate the documentation set

**Files:**
- Delete: `src/`
- Delete: `tests/`
- Delete: `skills/`
- Delete: `schemas/`
- Delete: `pyproject.toml`
- Keep: `uv.lock` only if repository policy requires retaining the lock file; otherwise remove it with the Python implementation.

**Interfaces:**
- Produces: a documentation-only repository with no stale executable references.

- [ ] **Step 1: Remove implementation directories and Python configuration**

Delete only the paths listed above; do not delete `.git` or `docs`.

- [ ] **Step 2: Search for stale implementation references**

Run `rg -n "support_agent|pytest|pyproject|workflows/.*\.json|schemas/|skills/" README.md docs`; update or remove references that claim executable behavior still exists.

- [ ] **Step 3: Validate Markdown and embedded JSON examples**

Run the repository’s remaining documentation checks or a standalone parser for every fenced JSON block, then run `git diff --check`.

- [ ] **Step 4: Review the document map against the architecture overview**

Confirm each concept has one owner document and no protocol invents a new runtime concept without updating the overview.

- [ ] **Step 5: Commit the documentation rebuild**

```bash
git add README.md docs
git rm -r src tests skills schemas workflows pyproject.toml
git commit -m "docs: rebuild customer service agent architecture"
git push origin main
```
