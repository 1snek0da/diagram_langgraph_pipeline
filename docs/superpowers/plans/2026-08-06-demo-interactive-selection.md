# Demo Interactive Selection Implementation Plan

> **For agentic workers:** Implement task-by-task with tests after each change.

**Goal:** Make the offline `demo` command choose among the five Router task types with arrow keys and Enter.

**Architecture:** Keep the existing fixed offline fixtures and `run_research` call. Add a small terminal menu helper in `cli.py`; the selected `TaskType` is inserted into the demo state so the existing Router controls node execution and report scope.

**Tech Stack:** Python, Typer, pytest, existing LangGraph runner.

## Global Constraints

- Do not modify database schema, PostgreSQL repository, or real `run` behavior.
- Demo remains offline and must not require PostgreSQL, network access, or LLM configuration.
- The menu must support Up/Down movement, wrap around at the ends, and Enter confirmation.
- The five options must be `full`, `industry`, `fundamental`, `technical`, `market`, with `full` initially selected.

---

### Task 1: Add testable terminal menu selection

**Files:**
- Modify: `src/diagram_langgraph_pipeline/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Add a helper that accepts a key-reading function and returns `TaskType`, allowing tests to inject key sequences without a real terminal.
- Recognize ANSI/Windows-compatible Up, Down, and Enter sequences; ignore unrelated keys.

- [ ] Write failing tests for initial selection, Down/Up movement, wrap-around, and Enter confirmation.
- [ ] Implement the minimal menu helper and rendering function.
- [ ] Run the focused CLI tests and confirm they pass.
- [ ] Commit as `feat: add interactive demo task menu`.

### Task 2: Connect the menu to offline demo execution

**Files:**
- Modify: `src/diagram_langgraph_pipeline/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- `demo` calls the menu helper, writes the selected task value into the existing demo state, and keeps the existing fixture providers.

- [ ] Add tests that invoke the demo command with a mocked selection and verify `task_type` reaches `run_research`.
- [ ] Add coverage for all five task values and ensure the demo remains database-free.
- [ ] Run the focused demo tests.
- [ ] Commit as `feat: make demo task selectable`.

### Task 3: Verify user-facing behavior and regression safety

**Files:**
- Modify: `README.md`

- [ ] Document the arrow-key/Enter interaction and the optional non-interactive test helper behavior.
- [ ] Run the full test suite with a writable basetemp directory.
- [ ] Run `python -m diagram_langgraph_pipeline demo` once in a terminal-compatible session and record the selected task/output.
- [ ] Commit as `docs: document interactive demo selection`.
