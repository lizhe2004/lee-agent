# Customer Support Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI customer support agent with executable refund and subscription-cancellation workflows, a guarded harness, reusable skills, and readable workflow documentation.

**Architecture:** A JSON Schema validates workflow definitions; semantic validation then checks graph references, tool registration, transitions, and safe expressions before compiling nodes. A durable engine persists each case and executes asks, branches, guarded tool actions, responses, and terminal states. A harness mediates model extraction/replies and registered tools. Skills provide model-facing SOP language, while JSON workflows remain the source of executable order and guards. A generic case planner composes only registered goals; it does not generate arbitrary tools or workflows.

**Tech Stack:** Python 3.11+, `jsonschema`, SQLite via `sqlite3`, `argparse`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-18-customer-support-agent-design.md`

## Global Constraints

- Models may extract user-provided fields and write replies, but may not set trusted identity, order, eligibility, subscription, or operation-result facts.
- Identity, order, eligibility, cancellation, and refund success must come from registered tool results.
- Refund submission requires verified identity, a matched first-party order, eligible policy result, explicit user confirmation, and an idempotency key.
- Apple and other third-party purchases must not be submitted to the first-party refund tool.
- Unmet guards prevent tool execution; missing failure routes and unknown tool statuses fail closed.
- Persist workflow ID and version with every case so interrupted cases resume on the same definition.
- Do not create one workflow or skill for every combination of user intents.

---

## File Structure

- `pyproject.toml`: package metadata, runtime dependency, and pytest configuration.
- `src/support_agent/models.py`: typed case, tool result, workflow definition, and per-fact source/revision structures.
- `schemas/workflow.schema.json`: formal JSON Schema (Draft 2020-12) for the workflow language.
- `docs/workflow-definition-spec.md`: field-by-field runtime semantics and authoring rules for workflow JSON.
- `src/support_agent/workflow_loader.py`: JSON parsing, JSON Schema checks, semantic graph validation, and definition registry.
- `src/support_agent/store.py`: SQLite case and event persistence.
- `src/support_agent/workflow_engine.py`: deterministic node execution and transitions.
- `src/support_agent/tools.py`: tool protocol, registry, deterministic demo tools, and tool-result validation.
- `src/support_agent/agent.py`: model protocol plus deterministic demo agent for CLI tests.
- `src/support_agent/harness.py`: user-turn orchestration, skill loading, workflow resume/start, and tool mediation.
- `src/support_agent/planner.py`: normalize supported multiple goals and compose registered workflows without arbitrary execution plans.
- `src/support_agent/cli.py`: terminal conversation loop.
- `workflows/refund_request.json`: complete refund workflow definition.
- `workflows/subscription_cancellation.json`: complete cancellation workflow definition.
- `skills/refund_request/SKILL.md`: end-to-end refund SOP for the agent.
- `skills/subscription_cancellation/SKILL.md`: end-to-end cancellation SOP for the agent.
- `docs/workflows/`: generated readable workflow documentation.
- `tests/`: loader, engine, persistence, harness, planner, CLI, and end-to-end tests.

## Task 1: Python package and typed workflow data

**Files:**
- Create: `pyproject.toml`
- Create: `src/support_agent/__init__.py`
- Create: `src/support_agent/models.py`
- Create: `tests/test_models.py`

**Interfaces:**
- `ToolResult(status: str, data: dict[str, object], error: str | None = None)`
- `Case(case_id, workflow_id, workflow_version, current_node, status, facts, waiting_for_user, visit_counts)`
- `WorkflowDefinition(workflow_id, version, start, nodes)`

- [ ] **Step 1: Write failing model tests**

Test that `ToolResult` stores status/data and `Case` serializes to and from JSON without losing nested facts, workflow version, fact sources, or fact revisions.

- [ ] **Step 2: Run model tests and verify failure**

Run: `pytest tests/test_models.py -q`
Expected: FAIL because package and models do not exist yet.

- [ ] **Step 3: Add package metadata and minimal dataclasses**

Declare Python `>=3.11`, runtime dependency `jsonschema>=4.22`, and dev dependency `pytest>=8.0`. Implement `Case.to_dict()` and `Case.from_dict()` with only JSON-compatible values.

- [ ] **Step 4: Run model tests**

Run: `pytest tests/test_models.py -q`
Expected: PASS.

## Task 2: Workflow JSON Schema, loader, and static validation

**Files:**
- Create: `src/support_agent/workflow_loader.py`
- Create: `schemas/workflow.schema.json`
- Create: `workflows/refund_request.json`
- Create: `workflows/subscription_cancellation.json`
- Create: `tests/test_workflow_loader.py`

**Interfaces:**
- `load_workflow(path: Path) -> WorkflowDefinition`
- `validate_workflow(definition: WorkflowDefinition, tool_names: set[str]) -> None`
- `schemas/workflow.schema.json` declares the structural contract; semantic checks complement it.
- Supported node kinds: `ask`, `branch`, `action`, `respond`, `wait`, `end`.
- `WorkflowDefinition.nodes` maps node IDs to dictionaries; action result statuses map to target node IDs through `transitions`.

- [ ] **Step 1: Write loader tests first**

Cover a valid workflow, unknown node kind, missing target node, unregistered action tool, an action missing `on_guard_failure`, unsafe condition syntax, and a missing transition for a declared possible tool status.

- [ ] **Step 2: Run loader tests and verify failure**

Run: `pytest tests/test_workflow_loader.py -q`
Expected: FAIL because loader and definitions are absent.

- [ ] **Step 3: Implement JSON Schema validation and graph validation**

Use `json.loads` and `jsonschema.Draft202012Validator` against `schemas/workflow.schema.json`. Then validate start node, all referenced targets, registered tool names, and explicit action guard-failure routes. Parse branch expressions with a restricted evaluator supporting only dotted fact paths, string/number/bool/null literals, `==`, `!=`, `and`, and `or`; never call `eval`.

- [ ] **Step 4: Define refund and cancellation JSON workflows**

The refund graph must cover account verification, order lookup, refund-fact lookup, policy evaluation, channel routing, explicit refund confirmation, first-party submission, Apple/store guidance, and escalation. The cancellation graph must cover account verification, subscription lookup, channel routing, cancellation or store guidance, result reporting, and escalation.

- [ ] **Step 5: Run loader tests**

Run: `pytest tests/test_workflow_loader.py -q`
Expected: PASS, including both production demo JSON definitions loading successfully against the checked-in schema.

## Task 3: SQLite case store and deterministic workflow engine

**Files:**
- Create: `src/support_agent/store.py`
- Create: `src/support_agent/workflow_engine.py`
- Create: `tests/test_workflow_engine.py`
- Create: `tests/test_store.py`

**Interfaces:**
- `SQLiteCaseStore.create_case(workflow_id, workflow_version, start_node) -> Case`
- `SQLiteCaseStore.get_case(case_id) -> Case`
- `SQLiteCaseStore.save_case(case: Case) -> None`
- `SQLiteCaseStore.append_event(case_id, event_type, payload) -> None`
- `WorkflowEngine.advance(case: Case, workflow: WorkflowDefinition, tools: ToolRunner) -> EngineOutcome`
- `EngineOutcome(kind: Literal['ask', 'wait', 'finished'], reply_node: dict | None)`
- `ToolRunner.call(name: str, arguments: dict[str, object], idempotency_key: str | None = None) -> ToolResult`; Task 4's `ToolRegistry` implements this protocol.

- [ ] **Step 1: Write failing persistence tests**

Test case creation, JSON facts round trip, workflow version persistence, status update, and append-only event retrieval.

- [ ] **Step 2: Run persistence tests and verify failure**

Run: `pytest tests/test_store.py -q`
Expected: FAIL because the SQLite store is absent.

- [ ] **Step 3: Implement SQLite store**

Create `cases` and `case_events` tables on store initialization. Use parameterized SQL, JSON encode facts, and commit each case/event update in one transaction.

- [ ] **Step 4: Write failing engine tests**

Cover ask pause, branch choice, action success transition, guard failure without tool invocation, unknown tool status, missing guard route, max visit handling, end status, correction type validation, fact revision increment, invalidation, and rewind to the configured recomputation node. Use a recording fake tool to assert call count and arguments.

- [ ] **Step 5: Run engine tests and verify failure**

Run: `pytest tests/test_workflow_engine.py -q`
Expected: FAIL because engine is absent.

- [ ] **Step 6: Implement deterministic engine loop**

Advance automatically through branch/action/respond nodes until `ask`, `wait`, or `end`. For action nodes: compute unmet `requires`; if nonempty, record the unmet paths and route to `on_guard_failure` without calling the tool. Otherwise call the registered tool, persist its result, and choose the exact `transitions[result.status]`; an unknown status raises `WorkflowExecutionError` and blocks further actions.

- [ ] **Step 7: Run store and engine tests**

Run: `pytest tests/test_store.py tests/test_workflow_engine.py -q`
Expected: PASS.

## Task 4: Guarded tools and domain policy fixtures

**Files:**
- Create: `src/support_agent/tools.py`
- Create: `tests/test_tools.py`
- Modify: `workflows/refund_request.json`
- Modify: `workflows/subscription_cancellation.json`

**Interfaces:**
- `Tool.call(arguments: dict[str, object], idempotency_key: str | None) -> ToolResult`
- `ToolRegistry.register(name: str, tool: Tool) -> None`
- `ToolRegistry.call(name, arguments, idempotency_key=None) -> ToolResult`
- Demo tools return deterministic, structured statuses; no real payment or account system is contacted.

- [ ] **Step 1: Write tool registry and policy tests first**

Verify unknown tools are rejected, tool arguments are schema-checked, repeated refund idempotency keys return the original submission result, Apple orders cannot be submitted to first-party refunds, and eligibility comes only from the policy tool result.

- [ ] **Step 2: Run tool tests and verify failure**

Run: `pytest tests/test_tools.py -q`
Expected: FAIL because the tool registry is absent.

- [ ] **Step 3: Implement registry and deterministic demo tools**

Register OTP verification, order lookup, refund facts, policy evaluation, refund submission, subscription lookup, subscription cancellation, and human handoff tools. Validate tool outputs against declared status sets. Redact OTP values from events and errors.

- [ ] **Step 4: Run tool and workflow validation tests**

Run: `pytest tests/test_tools.py tests/test_workflow_loader.py -q`
Expected: PASS.

## Task 5: Agent protocol and harness conversation loop

**Files:**
- Create: `src/support_agent/agent.py`
- Create: `src/support_agent/harness.py`
- Create: `skills/refund_request/SKILL.md`
- Create: `skills/subscription_cancellation/SKILL.md`
- Create: `tests/test_harness.py`

**Interfaces:**
- `Agent.extract_fields(message: str, expected: list[str], skill_text: str) -> dict[str, object]`
- `Agent.write_reply(node: dict[str, object], facts: dict[str, object], skill_text: str) -> str`
- `Harness.handle_message(case_id: str | None, message: str) -> tuple[str, str]`
- Harness returns `(case_id, reply)`; Agent implementation is injectable; default demo Agent uses deterministic parsing/templates and makes no network calls.

- [ ] **Step 1: Write failing harness tests**

Cover initial workflow start, extraction only into declared ask fields, rejecting model-supplied trusted fields, skill loading by workflow, tool calls only through engine, resuming a waiting case, and no claim of refund success before a successful tool result.

- [ ] **Step 2: Run harness tests and verify failure**

Run: `pytest tests/test_harness.py -q`
Expected: FAIL because Agent and Harness modules are absent.

- [ ] **Step 3: Write the two end-to-end skills**

Each skill declares trigger, purpose, required facts, SOP summary, explanations, channel-specific handling, escalation conditions, and prohibited claims. `refund_request` references its workflow ID; cancellation references its own. Keep policy thresholds outside skill text. At any turn, harness checks for revisions to declared mutable inputs before treating the message as an answer to the current ask; on correction, call `WorkflowEngine.apply_user_corrections`, invalidate stale derived facts, and do not accept an old confirmation.

- [ ] **Step 4: Implement Agent protocol and demo Agent**

Implement deterministic extraction for dates, amounts, account hints, and yes/no confirmation needed by the examples. Use templates for questions/results. Keep the protocol replaceable with a model API later.

- [ ] **Step 5: Implement Harness turn handling**

Create or restore case, load pinned workflow and skill, extract only fields declared by the waiting ask node, validate types and sources, advance the engine, append redacted audit events, and return a reply only when the engine pauses or finishes. Never allow model output to write tool-owned facts.

- [ ] **Step 6: Run harness tests**

Run: `pytest tests/test_harness.py -q`
Expected: PASS.

## Task 6: Multiple-intent goal planner

**Files:**
- Create: `src/support_agent/planner.py`
- Modify: `src/support_agent/harness.py`
- Create: `tests/test_planner.py`
- Create: `tests/test_multi_intent.py`

**Interfaces:**
- Supported goals: `refund_charge`, `cancel_renewal`, `lookup_subscription`.
- `IntentPlanner.extract_goals(message: str) -> list[Goal]`
- `Goal(kind: str, account_scope: str, target_hint: dict[str, object])`
- `CasePlanner.validate_and_order(goals: list[Goal]) -> list[WorkflowTask]`
- Only registered workflow tasks and static dependency rules may enter a case.

- [ ] **Step 1: Write planner tests first**

Cover cancellation plus refund, account-scoped identity separation, duplicate goal deduplication, unsupported goal rejection, ambiguous family-account target requiring clarification, and partial completion when one child workflow fails.

- [ ] **Step 2: Run planner tests and verify failure**

Run: `pytest tests/test_planner.py tests/test_multi_intent.py -q`
Expected: FAIL because the planner is absent.

- [ ] **Step 3: Implement constrained goal planning**

Normalize recognized phrases into the fixed goal enum, preserve account scope for each goal, deduplicate identical goals, and topologically order only predefined dependencies. Do not let the model provide tool names, workflow JSON, or arbitrary graph edges. Return a clarification request for ambiguity and handoff for unsupported goals.

- [ ] **Step 4: Connect planner to case orchestration**

Represent each goal as a child workflow task under one case record. Share verified facts only within the same account scope; persist each child task state and report its result independently.

- [ ] **Step 5: Run planner and multi-intent tests**

Run: `pytest tests/test_planner.py tests/test_multi_intent.py -q`
Expected: PASS.

## Task 7: CLI, generated workflow documentation, and end-to-end verification

**Files:**
- Create: `src/support_agent/cli.py`
- Create: `src/support_agent/docgen.py`
- Create: `tests/test_cli.py`
- Create: `tests/test_end_to_end.py`
- Create: generated `docs/workflows/refund_request.md`
- Create: generated `docs/workflows/subscription_cancellation.md`
- Modify: `pyproject.toml`

**Interfaces:**
- CLI: `python -m support_agent.cli --db PATH --workflow WORKFLOW_ID`
- `render_workflow_docs(definition: WorkflowDefinition) -> str`
- `generate_docs(workflow_dir: Path, output_dir: Path) -> None`

- [ ] **Step 1: Write failing CLI and doc generation tests**

Test stdin/stdout conversation, exit command, persistence across CLI restart, and generated documentation listing all nodes, transitions, guards, and tools.

- [ ] **Step 2: Run CLI and documentation tests and verify failure**

Run: `pytest tests/test_cli.py -q`
Expected: FAIL because CLI and doc generator are absent.

- [ ] **Step 3: Implement CLI and documentation generator**

Use `argparse`; do not execute real financial operations. The CLI prints case ID and agent reply, accepts repeated user turns, and exits cleanly on `/exit`. The generator renders flow steps from loaded definitions and marks generated files with their source workflow ID/version.

- [ ] **Step 4: Generate workflow docs and run end-to-end scenarios**

Cover cross-account OTP then eligible first-party refund; Apple purchase guidance without internal refund call; failed identity blocking sensitive lookup; cancellation plus charge refund as separate outcomes; household account needing separate verification; tool error escalation; interruption and resume.

- [ ] **Step 5: Run full verification**

Run: `pytest -q`
Expected: all tests pass. Then run `python -m support_agent.cli --help` and a scripted CLI session against a temporary SQLite database.

## Spec Coverage Review

- Refund and cancellation flows: Tasks 2, 4, 5, and 7.
- Workflow schema, validation, execution, guards, state persistence/versioning: Tasks 1–3.
- Harness, tools, skills, audit, and trusted fact sources: Tasks 4–5.
- Multiple intents with constrained runtime composition: Task 6.
- Generated human-readable workflow docs and end-to-end scenarios: Task 7.
- Live payment-provider integration is intentionally excluded; tools are deterministic mocks for this CLI prototype.
