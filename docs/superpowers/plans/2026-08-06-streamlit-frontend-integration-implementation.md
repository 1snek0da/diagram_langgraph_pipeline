# Streamlit Frontend Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the six-page Streamlit terminal from `trading_agent_learn_frontend_backend_bundle.zip` onto the existing five-mode Task Router through an asynchronous FastAPI API backed by PostgreSQL.

**Architecture:** Streamlit depends only on an HTTP `AnalysisGateway`. FastAPI owns request validation and a bounded in-process executor, while `run_analysis`, Task Router, providers, and `PostgresAnalysisRepository` remain the only analysis implementation. PostgreSQL stores pending/running/terminal lifecycle state, node progress, history, and reports.

**Tech Stack:** Python 3.10+, LangGraph 1.2, Pydantic 2.12, PostgreSQL/psycopg 3.2, FastAPI 0.115+, Uvicorn 0.34+, Streamlit 1.28+, Plotly 5.15+, HTTPX 0.28+, pytest 8+

## Global Constraints

- Work only in `D:\diagram_langgraph_pipeline\.worktrees\frontend-integration` on `feature/frontend-integration`.
- Preserve all five Router values: `full`, `industry`, `fundamental`, `technical`, `market`.
- Every task requires a real ticker and analysis date, matching the current Router baseline `c6483db`.
- Port only the ZIP's UI, styles, models, and Gateway concepts; never import or copy its `multiple_agent_finance` Agent, Graph, Service, repository, or MySQL implementation.
- PostgreSQL is authoritative for lifecycle state, history, node progress, and reports.
- Streamlit must not import `runner`, `graph`, `service`, or repository modules.
- API responses and browser state must never include database passwords, Provider credentials, LLM keys, stack traces, or arbitrary server paths.
- Keep FastAPI and Streamlit optional under a `web` dependency extra so the existing CLI remains installable without them.
- Keep the product research-only: no broker connection, order model, or trade execution endpoint.
- Use TDD for every behavior and commit after every task.
- Run PowerShell commands from the worktree root. Use `D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe` for Python commands.

---

### Task 1: Preserve caller-owned run identity and expose degradation details

**Files:**
- Modify: `src/diagram_langgraph_pipeline/service.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: existing `RunOptions`, `run_analysis`, and `result_summary`.
- Produces: `RunOptions.run_id: str | None`; `run_analysis` passes a non-empty caller ID into LangGraph; `result_summary` returns `optional_node_statuses`.

- [ ] **Step 1: Write the failing service tests**

Extend the existing `test_market_service_skips_security_lookup_and_target_prefetch` in `tests/test_cli.py`. Add `run_id="run-api-1"` to its `RunOptions`, then add this assertion beside the existing initial-State assertions:

```python
assert initial["run_id"] == "run-api-1"
```

Add this independent summary test:

```python
def test_result_summary_exposes_optional_node_statuses(tmp_path):
    summary = result_summary(
        {
            "run_id": "run-1",
            "ticker": "AAPL",
            "optional_node_statuses": {
                "marginal_change": {"status": "skipped", "reason": "no licensed source"}
            },
        },
        {"provider_status_counts": {}},
        tmp_path / "report.md",
    )
    assert summary["optional_node_statuses"]["marginal_change"]["status"] == "skipped"
```

If the existing helpers have different names, extend the existing fixtures instead of introducing a second fake service stack.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pytest tests/test_cli.py -q --basetemp "$env:TEMP\dlp-web-task1-red"
```

Expected: FAIL because `RunOptions` rejects `run_id` and the summary omits `optional_node_statuses`.

- [ ] **Step 3: Add the minimal service changes**

Extend the dataclass and initial State construction:

```python
@dataclass(frozen=True)
class RunOptions:
    run_id: str | None = None
    ticker: str | None = None
    # keep every existing field unchanged


initial_state = {
    "task_type": plan.task_type.value,
    "ticker": ticker,
    # keep the existing state fields
}
if options.run_id:
    initial_state["run_id"] = options.run_id
state = run_research(initial_state, AgentDependencies(...))
```

Add the summary field without changing existing keys:

```python
"optional_node_statuses": state.get("optional_node_statuses", {}),
```

- [ ] **Step 4: Run focused and Router regression tests**

Run:

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pytest tests/test_cli.py tests/test_routing.py tests/test_task_router_pipeline.py -q --basetemp "$env:TEMP\dlp-web-task1-green"
```

Expected: all selected tests PASS.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/diagram_langgraph_pipeline/service.py tests/test_cli.py
git commit -m "feat: preserve API run identity"
```

---

### Task 2: Add the web lifecycle migration and repository query seam

**Files:**
- Create: `database/migrations/004_web_analysis_api.sql`
- Modify: `database/schema.sql`
- Modify: `src/diagram_langgraph_pipeline/providers/postgres_repository.py`
- Modify: `tests/test_database_migration.py`
- Create: `tests/test_web_repository.py`

**Interfaces:**
- Consumes: PostgreSQL tables `industries`, `securities`, `analysis_runs`, `node_runs`, `market_bars`, `final_reports`.
- Produces:
  - `create_pending_run(run_id: str, request: Mapping[str, Any]) -> None`
  - `update_run_lifecycle(run_id: str, status: str, *, error_code: str | None = None, error_summary: str | None = None) -> None`
  - `interrupt_incomplete_runs() -> int`
  - `get_run_record(run_id: str) -> dict[str, Any] | None`
  - `list_run_records(*, ticker: str | None, task_type: str | None, status: str | None, date_from: date | None, date_to: date | None, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]`
  - `list_node_records(run_id: str) -> list[dict[str, Any]]`
  - `get_report_record(run_id: str) -> dict[str, Any] | None`
  - `get_market_bar_records(ticker: str, start_date: date | None, end_date: date | None) -> list[dict[str, Any]]`

- [ ] **Step 1: Write migration assertions**

Add to `tests/test_database_migration.py`:

```python
def test_web_api_migration_extends_analysis_lifecycle():
    sql = Path("database/migrations/004_web_analysis_api.sql").read_text(encoding="utf-8").lower()
    assert "add column if not exists task_type" in sql
    assert "add column if not exists error_code" in sql
    assert "add column if not exists error_summary" in sql
    assert "'degraded'" in sql
    assert "'interrupted'" in sql
    assert "idx_analysis_runs_web_history" in sql
```

- [ ] **Step 2: Write repository contract tests**

Create `tests/test_web_repository.py` with a scripted fake connection matching the repository's existing context-manager usage:

```python
def test_create_pending_run_uses_placeholder_metadata(repository, cursor):
    repository.create_pending_run(
        "00000000-0000-0000-0000-000000000001",
        {
            "ticker": "AAPL",
            "industry_name": "Unknown",
            "as_of_date": date(2026, 8, 6),
            "investment_horizon": "medium",
            "task_type": "technical",
            "user_request": "",
            "max_retries": 1,
        },
    )
    sql_text = "\n".join(call.sql.lower() for call in cursor.calls)
    assert "insert into industries" in sql_text
    assert "insert into securities" in sql_text
    assert "insert into analysis_runs" in sql_text
    assert "'pending'" in sql_text


def test_interrupt_incomplete_runs_returns_affected_count(repository, cursor):
    cursor.rowcount = 2
    assert repository.interrupt_incomplete_runs() == 2
    assert "status='interrupted'" in cursor.calls[-1].sql.replace(" ", "").lower()
```

Also test that `list_run_records` clamps `limit` to `1..100`, uses bound parameters for filters, and returns the separate count.

- [ ] **Step 3: Run the new tests and verify RED**

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pytest tests/test_database_migration.py tests/test_web_repository.py -q --basetemp "$env:TEMP\dlp-web-task2-red"
```

Expected: FAIL because migration 004 and repository methods do not exist.

- [ ] **Step 4: Add the idempotent migration**

`database/migrations/004_web_analysis_api.sql` must contain concrete DDL:

```sql
ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS task_type TEXT NOT NULL DEFAULT 'full';
ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS error_code TEXT;
ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS error_summary TEXT;

ALTER TABLE analysis_runs DROP CONSTRAINT IF EXISTS analysis_runs_status_check;
ALTER TABLE analysis_runs ADD CONSTRAINT analysis_runs_status_check
CHECK (status IN ('pending','running','completed','degraded','failed','interrupted'));

CREATE INDEX IF NOT EXISTS idx_analysis_runs_web_history
ON analysis_runs (created_at DESC, task_type, status, ticker);
```

Do not insert into `schema_migrations` inside the SQL file. The existing database migration runner records integer version `4`, filename, and checksum after successful execution.

Mirror the final schema in `database/schema.sql` without changing unrelated tables.

- [ ] **Step 5: Implement narrow repository methods**

Use parameterized SQL only. `create_pending_run` must upsert `industry_name or "Unknown"`, upsert the ticker, and insert the pending row. `bootstrap_run` already uses `ON CONFLICT (id)` and will promote the same row to `running`.

Sanitize lifecycle failures before persistence:

```python
safe_summary = (error_summary or "")[:500]
cursor.execute(
    """
    UPDATE analysis_runs
       SET status=%s, error_code=%s, error_summary=%s, updated_at=now()
     WHERE id=%s
    """,
    (status, error_code, safe_summary or None, run_id),
)
```

Return JSON-ready dictionaries with ISO-compatible dates and no DSN or raw exception field.

- [ ] **Step 6: Run repository and migration tests**

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pytest tests/test_database_migration.py tests/test_web_repository.py tests/test_db_first_cache.py -q --basetemp "$env:TEMP\dlp-web-task2-green"
```

Expected: all selected tests PASS.

- [ ] **Step 7: Commit Task 2**

```powershell
git add database/schema.sql database/migrations/004_web_analysis_api.sql src/diagram_langgraph_pipeline/providers/postgres_repository.py tests/test_database_migration.py tests/test_web_repository.py
git commit -m "feat: persist web analysis lifecycle"
```

---

### Task 3: Define API schemas and Router-derived task metadata

**Files:**
- Create: `src/diagram_langgraph_pipeline/api/__init__.py`
- Create: `src/diagram_langgraph_pipeline/api/schemas.py`
- Create: `src/diagram_langgraph_pipeline/api/catalog.py`
- Create: `tests/api/test_schemas.py`
- Create: `tests/api/test_task_catalog.py`

**Interfaces:**
- Consumes: `TaskType`, `get_execution_plan`, `RunOptions`.
- Produces: `RunStatus`, `CreateAnalysisRunRequest.to_options(run_id)`, `TaskTypeResponse`, `AcceptedRunResponse`, `RunResponse`, `RunListResponse`, `NodeResponse`, `ReportResponse`, `MarketBarsResponse`, `ErrorEnvelope`, and `task_catalog(*, paid_sources_available: bool) -> list[TaskTypeResponse]`.

- [ ] **Step 1: Write schema validation tests**

Create `tests/api/test_schemas.py`:

```python
def test_create_request_maps_all_router_fields():
    request = CreateAnalysisRunRequest(
        ticker="aapl",
        task_type=TaskType.TECHNICAL,
        as_of_date=date(2026, 8, 6),
        report_days=70,
        technical_days=251,
        offline=True,
    )
    options = request.to_options("run-1")
    assert options.run_id == "run-1"
    assert options.ticker == "AAPL"
    assert options.task_type is TaskType.TECHNICAL
    assert options.offline is True


@pytest.mark.parametrize("ticker", ["", "   "])
def test_create_request_rejects_blank_ticker(ticker):
    with pytest.raises(ValidationError):
        CreateAnalysisRunRequest(ticker=ticker, task_type="market")


def test_create_request_rejects_inverted_windows():
    with pytest.raises(ValidationError, match="technical_days"):
        CreateAnalysisRunRequest(ticker="AAPL", report_days=70, technical_days=20)
```

- [ ] **Step 2: Write Router catalog tests**

Create `tests/api/test_task_catalog.py`:

```python
def test_catalog_is_derived_from_every_router_plan():
    records = task_catalog(paid_sources_available=False)
    assert [record.task_type for record in records] == list(TaskType)
    for record in records:
        plan = get_execution_plan(record.task_type)
        assert record.required_nodes == plan.required_nodes
        assert record.support_nodes == plan.support_nodes
        assert record.optional_nodes == plan.optional_nodes
        assert record.skipped_nodes == plan.skipped_nodes
        assert record.required_inputs == plan.required_inputs
        assert record.conclusion_scope == plan.conclusion_scope
        assert record.paid_sources_available is False
```

- [ ] **Step 3: Run the schema tests and verify RED**

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pytest tests/api/test_schemas.py tests/api/test_task_catalog.py -q --basetemp "$env:TEMP\dlp-web-task3-red"
```

Expected: collection FAIL because the API modules do not exist.

- [ ] **Step 4: Implement immutable Pydantic schemas**

Use frozen models and literal lifecycle states:

```python
RunStatus = Literal["pending", "running", "completed", "degraded", "failed", "interrupted"]

class ApiModel(BaseModel):
    model_config = ConfigDict(frozen=True)

class CreateAnalysisRunRequest(ApiModel):
    ticker: str = Field(min_length=1)
    task_type: TaskType = TaskType.FULL
    industry_name: str | None = None
    as_of_date: date = Field(default_factory=date.today)
    investment_horizon: Literal["short", "medium", "long"] = "medium"
    report_days: int = Field(default=70, ge=5, le=2000)
    technical_days: int = Field(default=251, ge=5, le=2000)
    llm: bool | None = None
    offline: bool = False
    refresh: bool = False
    allow_paid: bool = False

    @model_validator(mode="after")
    def validate_windows_and_modes(self):
        if self.technical_days < self.report_days:
            raise ValueError("technical_days must be greater than or equal to report_days")
        if self.offline and self.refresh:
            raise ValueError("offline and refresh are mutually exclusive")
        return self

    def to_options(self, run_id: str) -> RunOptions:
        return RunOptions(
            run_id=run_id,
            ticker=self.ticker.strip().upper(),
            task_type=self.task_type,
            industry_name=(self.industry_name or "").strip() or None,
            report_days=self.report_days,
            technical_days=self.technical_days,
            as_of=self.as_of_date,
            horizon=self.investment_horizon,
            llm=self.llm,
            offline=self.offline,
            refresh=self.refresh,
            allow_paid=self.allow_paid,
        )
```

Define response fields explicitly; do not expose `report_path`, DSN, settings, or raw exceptions.

- [ ] **Step 5: Implement `task_catalog()`**

Use `task_catalog(*, paid_sources_available: bool)`. A fixed Chinese display-copy map supplies only names/descriptions; derive every execution field from `get_execution_plan(task_type)`. `TaskTypeResponse` includes `paid_sources_available: bool`, supplied from server-side Provider configuration and never from the browser.

- [ ] **Step 6: Run schema, catalog, and Router tests**

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pytest tests/api/test_schemas.py tests/api/test_task_catalog.py tests/test_routing.py -q --basetemp "$env:TEMP\dlp-web-task3-green"
```

Expected: all selected tests PASS.

- [ ] **Step 7: Commit Task 3**

```powershell
git add src/diagram_langgraph_pipeline/api tests/api/test_schemas.py tests/api/test_task_catalog.py
git commit -m "feat: define web API contracts"
```

---

### Task 4: Build the bounded asynchronous analysis job service

**Files:**
- Create: `src/diagram_langgraph_pipeline/api/jobs.py`
- Create: `tests/api/test_jobs.py`

**Interfaces:**
- Consumes: `CreateAnalysisRunRequest`, `RunOptions`, `run_analysis`, `load_settings`, and Task 2 repository methods.
- Produces:
  - `AnalysisJobService.submit(request: CreateAnalysisRunRequest) -> UUID`
  - `AnalysisJobService.recover() -> int`
  - `AnalysisJobService.shutdown() -> None`
  - constructor injection for repository, settings, executor, and runner.

- [ ] **Step 1: Write lifecycle tests with an immediate executor**

Create `tests/api/test_jobs.py`:

```python
class ImmediateExecutor:
    def submit(self, function, *args):
        function(*args)
        return object()
    def shutdown(self, wait=True, cancel_futures=False):
        return None


class FakeApiRepository:
    def __init__(self):
        self.created_run_id = None
        self.statuses = []
        self.last_error_code = None
        self.last_error_summary = None

    def create_pending_run(self, run_id, request):
        self.created_run_id = run_id

    def update_run_lifecycle(self, run_id, status, *, error_code=None, error_summary=None):
        self.statuses.append(status)
        self.last_error_code = error_code
        self.last_error_summary = error_summary

    def interrupt_incomplete_runs(self):
        return 2


def make_service(repository, *, result=None, error=None):
    def runner(options, settings, event_callback=None):
        if error is not None:
            raise error
        summary = result or {"optional_node_statuses": {}}
        return summary, summary
    return AnalysisJobService(
        repository=repository,
        settings={"DATABASE_URL": "postgresql://test"},
        runner=runner,
        executor=ImmediateExecutor(),
    )


def test_submit_uses_one_run_id_for_database_and_runner():
    repository = FakeApiRepository()
    captured = {}

    def runner(options, settings, event_callback=None):
        captured["run_id"] = options.run_id
        return {"optional_node_statuses": {}}, {"optional_node_statuses": {}}

    service = AnalysisJobService(
        repository=repository,
        settings={"DATABASE_URL": "postgresql://test"},
        runner=runner,
        executor=ImmediateExecutor(),
    )
    run_id = service.submit(CreateAnalysisRunRequest(ticker="AAPL", task_type="technical"))
    assert str(run_id) == captured["run_id"] == repository.created_run_id
    assert repository.statuses == ["running", "completed"]


def test_optional_skip_finishes_as_degraded():
    repository = FakeApiRepository()
    service = make_service(
        repository,
        result={"optional_node_statuses": {"marginal_change": {"status": "skipped"}}},
    )
    service.submit(CreateAnalysisRunRequest(ticker="AAPL", task_type="fundamental"))
    assert repository.statuses[-1] == "degraded"


def test_runner_error_is_sanitized():
    repository = FakeApiRepository()
    service = make_service(repository, error=RuntimeError("secret-value"))
    service.submit(CreateAnalysisRunRequest(ticker="AAPL"))
    assert repository.last_error_code == "ANALYSIS_FAILED"
    assert repository.last_error_summary == "RuntimeError"
```

Also assert `recover()` calls `interrupt_incomplete_runs` and `shutdown()` delegates to the executor.

- [ ] **Step 2: Run the job tests and verify RED**

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pytest tests/api/test_jobs.py -q --basetemp "$env:TEMP\dlp-web-task4-red"
```

Expected: collection FAIL because `api.jobs` does not exist.

- [ ] **Step 3: Implement the job service**

Core execution must be deterministic and bounded:

```python
class AnalysisJobService:
    def __init__(self, repository, settings, *, runner=run_analysis, executor=None, max_workers=1):
        self._repository = repository
        self._settings = dict(settings)
        self._runner = runner
        self._executor = executor or ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="analysis-job",
        )

    def submit(self, request: CreateAnalysisRunRequest) -> UUID:
        run_id = uuid4()
        options = request.to_options(str(run_id))
        self._repository.create_pending_run(str(run_id), request.model_dump(mode="json"))
        self._executor.submit(self._execute, options)
        return run_id

    def _execute(self, options: RunOptions) -> None:
        run_id = str(options.run_id)
        self._repository.update_run_lifecycle(run_id, "running")
        try:
            state, summary = self._runner(options, self._settings)
        except Exception as exc:
            self._repository.update_run_lifecycle(
                run_id,
                "failed",
                error_code="ANALYSIS_FAILED",
                error_summary=type(exc).__name__,
            )
            return
        optional = summary.get("optional_node_statuses", {})
        status = "degraded" if any(
            item.get("status") in {"skipped", "degraded"} for item in optional.values()
        ) else "completed"
        self._repository.update_run_lifecycle(run_id, status)
```

Read `DLP_API_MAX_WORKERS` once in the application factory, parse it as `1..8`, and default to `1`.

- [ ] **Step 4: Run job tests**

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pytest tests/api/test_jobs.py -q --basetemp "$env:TEMP\dlp-web-task4-green"
```

Expected: all job tests PASS.

- [ ] **Step 5: Commit Task 4**

```powershell
git add src/diagram_langgraph_pipeline/api/jobs.py tests/api/test_jobs.py
git commit -m "feat: run analyses as bounded API jobs"
```

---

### Task 5: Expose the versioned FastAPI application

**Files:**
- Create: `src/diagram_langgraph_pipeline/api/errors.py`
- Create: `src/diagram_langgraph_pipeline/api/routes.py`
- Create: `src/diagram_langgraph_pipeline/api/app.py`
- Modify: `pyproject.toml`
- Create: `tests/api/test_app.py`
- Create: `tests/api/test_routes.py`

**Interfaces:**
- Consumes: Task 2 repository methods, `task_catalog()`, API schemas, `AnalysisJobService`.
- Produces: `create_app(repository=None, job_service=None, settings=None) -> FastAPI` and the eight `/api/v1` endpoints from the design.

- [ ] **Step 1: Add API dependency extra**

Modify `pyproject.toml`:

```toml
web = [
    "fastapi>=0.115,<1",
    "uvicorn>=0.34,<1",
    "streamlit>=1.28,<2",
    "plotly>=5.15,<7",
]
```

Keep `httpx` in core because the project already uses it.

- [ ] **Step 2: Install the worktree with web and test dependencies**

```powershell
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pip install -e ".[dev,web,postgres]"
```

Expected: installation exits `0` and imports `fastapi`, `streamlit`, and `plotly`.

- [ ] **Step 3: Write app and route tests**

Create `tests/api/test_app.py` and `tests/api/test_routes.py`:

```python
class FakeJobs:
    def __init__(self, run_id=UUID("00000000-0000-0000-0000-000000000001")):
        self.run_id = run_id
    def submit(self, request):
        return self.run_id
    def recover(self):
        return 0
    def shutdown(self):
        return None


class FakeRepository:
    def __init__(self, *, run=None, report=None, node_records=None):
        self.run = run
        self.report = report
        self.node_records = node_records or []
    def check_health(self):
        return {"status": "ok"}
    def get_run_record(self, run_id):
        return self.run
    def get_report_record(self, run_id):
        return self.report
    def list_node_records(self, run_id):
        return self.node_records


def complete_run_record(task_type="technical"):
    return {
        "run_id": "00000000-0000-0000-0000-000000000001",
        "ticker": "AAPL", "task_type": task_type, "status": "completed",
        "as_of_date": "2026-08-06", "investment_horizon": "medium",
        "created_at": "2026-08-06T00:00:00Z", "updated_at": "2026-08-06T00:01:00Z",
        "error_code": None, "error_summary": None,
    }


def test_health_reports_service_and_storage():
    client = TestClient(create_app(repository=FakeRepository(), job_service=FakeJobs()))
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"service": "ok", "storage": "ok"}


def test_submit_returns_202_and_poll_url():
    jobs = FakeJobs(run_id=UUID("00000000-0000-0000-0000-000000000001"))
    client = TestClient(create_app(repository=FakeRepository(), job_service=jobs))
    response = client.post(
        "/api/v1/analysis-runs",
        json={"ticker": "AAPL", "task_type": "technical", "as_of_date": "2026-08-06"},
    )
    assert response.status_code == 202
    assert response.json()["poll_url"].endswith("00000000-0000-0000-0000-000000000001")


def test_report_not_ready_returns_retryable_409():
    repository = FakeRepository(run={"status": "running"}, report=None)
    client = TestClient(create_app(repository=repository, job_service=FakeJobs()))
    response = client.get(
        "/api/v1/analysis-runs/00000000-0000-0000-0000-000000000001/report"
    )
    assert response.status_code == 409
    assert response.json()["error"]["retryable"] is True


def test_nodes_include_synthetic_skipped_records_from_router():
    run = complete_run_record(task_type="technical")
    repository = FakeRepository(run=run, node_records=[])
    client = TestClient(create_app(repository=repository, job_service=FakeJobs()))
    response = client.get(
        "/api/v1/analysis-runs/00000000-0000-0000-0000-000000000001/nodes"
    )
    by_name = {item["name"]: item for item in response.json()["items"]}
    assert by_name["stock_technical"]["role"] == "required"
    assert by_name["industry_report"] == {
        "name": "industry_report", "role": "skipped", "status": "skipped",
        "attempt_no": None, "started_at": None, "ended_at": None,
        "error_summary": None,
    }
```

Also cover task catalog, paginated history filters, node records, market bars, `404`, `422`, and storage `503`.

- [ ] **Step 4: Run API tests and verify RED**

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pytest tests/api -q --basetemp "$env:TEMP\dlp-web-task5-red"
```

Expected: FAIL because the application and routes do not exist.

- [ ] **Step 5: Implement stable error envelopes**

Use this public shape for every handled failure:

```python
class ApiError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str, *, retryable=False):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable
```

Install handlers for `ApiError`, `RunConfigurationError`, `DatabaseUnavailableError`, and unexpected exceptions. Unexpected exceptions return code `INTERNAL_ERROR`, message `Internal server error`, and never include `str(exc)`.

- [ ] **Step 6: Implement routes and application lifecycle**

The application factory must:

1. load settings when not injected;
2. require `DATABASE_URL`;
3. create `PostgresAnalysisRepository` and `AnalysisJobService` when not injected;
4. call `jobs.recover()` at startup;
5. call `jobs.shutdown()` at shutdown;
6. configure CORS from `DLP_CORS_ORIGINS`, defaulting to `http://127.0.0.1:8501,http://localhost:8501`.

Routes must only map repository records into response schemas; SQL stays in the repository. For `/nodes`, load the run's `task_type`, derive roles from `get_execution_plan`, merge actual `node_runs`, and synthesize one `status="skipped"` record for every planned skipped node. Never insert synthetic skipped rows into `node_runs`.

- [ ] **Step 7: Run API and existing CLI tests**

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pytest tests/api tests/test_cli.py tests/test_database_migration.py -q --basetemp "$env:TEMP\dlp-web-task5-green"
```

Expected: all selected tests PASS.

- [ ] **Step 8: Commit Task 5**

```powershell
git add pyproject.toml src/diagram_langgraph_pipeline/api tests/api
git commit -m "feat: expose versioned analysis API"
```

---

### Task 6: Port UI models, session state, and HTTP Gateway

**Files:**
- Create: `src/diagram_langgraph_pipeline/ui/__init__.py`
- Create: `src/diagram_langgraph_pipeline/ui/models.py`
- Create: `src/diagram_langgraph_pipeline/ui/gateway.py`
- Create: `src/diagram_langgraph_pipeline/ui/api_gateway.py`
- Create: `src/diagram_langgraph_pipeline/ui/state.py`
- Create: `tests/ui/test_models.py`
- Create: `tests/ui/test_gateway.py`
- Create: `tests/ui/test_state.py`
- Create: `tests/ui/fakes.py`

**Interfaces:**
- Consumes: FastAPI JSON contracts from Task 5.
- Produces:
  - `AnalysisGateway` protocol with `task_types`, `create_run`, `get_run`, `list_runs`, `get_nodes`, `get_report`, and `get_market_chart`;
  - immutable UI models `TaskTypeView`, `AnalysisRequest`, `AnalysisRun`, `NodeView`, `ReportView`, `MarketBar`, `MarketChart`;
  - `ApiAnalysisGateway(base_url: str, client: httpx.Client | None = None)`;
  - session helpers `initialize_ui_state`, `save_run`, `current_run`, `navigate`.
  - shared test doubles `FakeStreamlit`, `FakeGateway`, `five_task_views`, and `sample_market_chart` for Tasks 7-9.

- [ ] **Step 1: Port and rewrite model tests**

Use the ZIP's `tests/ui/test_ui_models.py`, `test_gateway_contract.py`, `test_api_gateway.py`, and `test_session_state.py` as behavioral references, but change imports to `diagram_langgraph_pipeline.ui` and expand the task enum to all five values.

Required assertions:

```python
def test_analysis_request_accepts_all_router_tasks():
    for task_type in TaskType:
        request = AnalysisRequest(ticker="AAPL", task_type=task_type)
        assert request.task_type is task_type


def test_gateway_never_maps_report_path_from_server_payload():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        "run_id": "00000000-0000-0000-0000-000000000001",
        "ticker": "AAPL", "task_type": "technical", "status": "completed",
        "created_at": "2026-08-06T00:00:00Z", "updated_at": "2026-08-06T00:01:00Z",
        "report_path": "C:/secret/report.md"
    }))
    client = httpx.Client(base_url="http://test", transport=transport)
    gateway = ApiAnalysisGateway("http://test", client=client)
    run = gateway.get_run("run-1")
    assert not hasattr(run, "report_path")
```

- [ ] **Step 2: Run UI foundation tests and verify RED**

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pytest tests/ui/test_models.py tests/ui/test_gateway.py tests/ui/test_state.py -q --basetemp "$env:TEMP\dlp-web-task6-red"
```

Expected: collection FAIL because the UI package does not exist.

- [ ] **Step 3: Implement focused immutable UI models**

Do not port evidence, decision, or local-backend types that the six pages do not consume. Use:

```python
class AnalysisRequest(FrozenModel):
    ticker: str
    task_type: TaskType
    industry_name: str | None = None
    as_of_date: date = Field(default_factory=date.today)
    investment_horizon: Literal["short", "medium", "long"] = "medium"
    report_days: int = 70
    technical_days: int = 251
    llm: bool | None = None
    offline: bool = False
    refresh: bool = False
    allow_paid: bool = False

class AnalysisRun(FrozenModel):
    run_id: str
    ticker: str
    task_type: TaskType
    status: RunStatus
    created_at: datetime
    updated_at: datetime
    error_code: str | None = None
    error_summary: str | None = None
```

- [ ] **Step 4: Implement HTTP-only Gateway and state**

`create_gateway()` reads `DLP_API_BASE_URL`, defaults to `http://127.0.0.1:8000`, and always returns `ApiAnalysisGateway`. Do not create a local direct-call Gateway.

Map HTTP failures to:

```python
GatewayRequestError(code: str, message: str, retryable: bool = False)
```

Session state stores only navigation, selected `run_id`, and cached view models; PostgreSQL remains authoritative.

Create `tests/ui/fakes.py` with deterministic recording doubles. `FakeGateway` implements every `AnalysisGateway` method and records `created_request`, `get_run_calls`, and `last_filters`. `FakeStreamlit` implements the methods used by the six pages (`columns`, `form`, `selectbox`, `text_input`, `date_input`, `checkbox`, `number_input`, `button`, `form_submit_button`, `markdown`, `write`, `error`, `warning`, `info`, `metric`, `dataframe`, `plotly_chart`, `download_button`, `rerun`) and appends rendered text, figures, and downloads to lists. `five_task_views()` must derive five fixtures from `task_catalog(paid_sources_available=False)`; `sample_market_chart()` returns two dated bars.

- [ ] **Step 5: Run UI foundation tests**

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pytest tests/ui/test_models.py tests/ui/test_gateway.py tests/ui/test_state.py -q --basetemp "$env:TEMP\dlp-web-task6-green"
```

Expected: all selected tests PASS.

- [ ] **Step 6: Commit Task 6**

```powershell
git add src/diagram_langgraph_pipeline/ui tests/ui/fakes.py tests/ui/test_models.py tests/ui/test_gateway.py tests/ui/test_state.py
git commit -m "feat: add Streamlit HTTP gateway"
```

---

### Task 7: Port the workspace and five-mode analysis form

**Files:**
- Create: `src/diagram_langgraph_pipeline/ui/components.py`
- Create: `src/diagram_langgraph_pipeline/ui/pages/__init__.py`
- Create: `src/diagram_langgraph_pipeline/ui/pages/workspace.py`
- Create: `src/diagram_langgraph_pipeline/ui/pages/new_analysis.py`
- Create: `tests/ui/test_workspace_page.py`
- Create: `tests/ui/test_new_analysis_page.py`

**Interfaces:**
- Consumes: `AnalysisGateway.task_types/list_runs/create_run`, UI models, session helpers.
- Produces: `workspace.render(st, gateway, state)` and `new_analysis.render(st, gateway, state)`.

- [ ] **Step 1: Write page tests with fake Streamlit and Gateway objects**

Port the ZIP's page-testing style and assert Router-specific behavior:

```python
def test_analysis_page_submits_selected_market_task():
    st = FakeStreamlit(submit=True, values={"任务类型": "market", "证券代码": "AAPL"})
    gateway = FakeGateway(task_types=five_task_views())
    state = {}
    render_new_analysis(st, gateway, state)
    assert gateway.created_request.task_type is TaskType.MARKET
    assert gateway.created_request.ticker == "AAPL"


def test_analysis_page_uses_router_metadata_for_scope_preview():
    st = FakeStreamlit(submit=False, values={"任务类型": "fundamental"})
    gateway = FakeGateway(task_types=five_task_views())
    render_new_analysis(st, gateway, {})
    assert "business" in st.rendered_text
    assert "marginal_change" in st.rendered_text
    assert "stock_technical" in st.rendered_text
```

The second assertion must show `stock_technical` under skipped scope, not active progress.

- [ ] **Step 2: Run page tests and verify RED**

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pytest tests/ui/test_workspace_page.py tests/ui/test_new_analysis_page.py -q --basetemp "$env:TEMP\dlp-web-task7-red"
```

Expected: collection FAIL because the pages do not exist.

- [ ] **Step 3: Port reusable ZIP components and workspace layout**

Port the heading, empty-state, status badge, and run-caption concepts. Replace every mojibake string with readable Simplified Chinese. Workspace metrics are computed from `gateway.list_runs(limit=20)` and must include total, running, failed/interrupted, and completed/degraded.

- [ ] **Step 4: Implement the metadata-driven form**

The task selectbox options come from `gateway.task_types()`. Always show ticker and date. Show investment horizon for `full`, `industry`, and `fundamental`; retain hidden default `medium` for `technical` and `market`.

Put these controls in an expander:

```text
report_days, technical_days, offline, refresh, llm, allow_paid
```

Disable `allow_paid` unless task metadata says `paid_sources_available=True`. Reject `offline and refresh` in the UI before calling the Gateway. After creation, save the returned run, navigate to `workflow`, and rerun.

- [ ] **Step 5: Run page and Gateway tests**

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pytest tests/ui/test_workspace_page.py tests/ui/test_new_analysis_page.py tests/ui/test_gateway.py -q --basetemp "$env:TEMP\dlp-web-task7-green"
```

Expected: all selected tests PASS.

- [ ] **Step 6: Commit Task 7**

```powershell
git add src/diagram_langgraph_pipeline/ui/components.py src/diagram_langgraph_pipeline/ui/pages tests/ui/test_workspace_page.py tests/ui/test_new_analysis_page.py
git commit -m "feat: add five-mode analysis form"
```

---

### Task 8: Port workflow, report, and persistent history pages

**Files:**
- Create: `src/diagram_langgraph_pipeline/ui/pages/workflow.py`
- Create: `src/diagram_langgraph_pipeline/ui/pages/report.py`
- Create: `src/diagram_langgraph_pipeline/ui/pages/history.py`
- Create: `tests/ui/test_workflow_page.py`
- Create: `tests/ui/test_report_page.py`
- Create: `tests/ui/test_history_page.py`

**Interfaces:**
- Consumes: `get_run`, `get_nodes`, `get_report`, `list_runs`, Router node-role fields.
- Produces: three page `render(st, gateway, state)` functions and `refresh_active_run(gateway, state, run)`.

- [ ] **Step 1: Write workflow polling and role-rendering tests**

```python
def test_workflow_refreshes_non_terminal_run_and_groups_node_roles():
    gateway = FakeGateway(
        run=running_run(),
        nodes=[
            NodeView(name="business", role="required", status="completed"),
            NodeView(name="marginal_change", role="optional", status="degraded"),
            NodeView(name="stock_technical", role="skipped", status="skipped"),
        ],
    )
    st = FakeStreamlit(buttons={"刷新状态": True})
    render_workflow(st, gateway, {"selected_run_id": "run-1"})
    assert gateway.get_run_calls == ["run-1"]
    assert "可选节点" in st.rendered_text
    assert "主动屏蔽" in st.rendered_text
    assert "失败" not in st.text_for("stock_technical")
```

- [ ] **Step 2: Write report and history tests**

```python
def test_report_download_uses_markdown_content_not_server_path():
    gateway = FakeGateway(report=ReportView(run_id="run-1", markdown="# 报告"))
    st = FakeStreamlit()
    render_report(st, gateway, {"selected_run_id": "run-1"})
    assert st.downloads[0].data == "# 报告"
    assert st.downloads[0].file_name == "research_run-1.md"


def test_history_sends_filters_to_gateway():
    gateway = FakeGateway(runs=[])
    st = FakeStreamlit(values={"证券代码": "AAPL", "任务类型": "technical", "状态": "completed"})
    render_history(st, gateway, {})
    assert gateway.last_filters == {
        "ticker": "AAPL", "task_type": "technical", "status": "completed"
    }
```

- [ ] **Step 3: Run the three page tests and verify RED**

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pytest tests/ui/test_workflow_page.py tests/ui/test_report_page.py tests/ui/test_history_page.py -q --basetemp "$env:TEMP\dlp-web-task8-red"
```

Expected: collection FAIL because the pages do not exist.

- [ ] **Step 4: Implement workflow and report behavior**

Terminal states are exactly:

```python
TERMINAL_STATUSES = {"completed", "degraded", "failed", "interrupted"}
```

Poll only on explicit refresh or Streamlit rerun; do not create an infinite sleep loop. Completed/degraded runs link to report. Failed/interrupted runs show `error_code` and safe summary. Report sections show scope, Review, missing data, degradation, Token usage, and Markdown.

- [ ] **Step 5: Implement database-backed history behavior**

History never reads `st.session_state["runs"]` as the source of truth. Send filters to `gateway.list_runs`, render server pagination, and save only the selected run ID before navigating.

- [ ] **Step 6: Run workflow, report, history, and state tests**

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pytest tests/ui/test_workflow_page.py tests/ui/test_report_page.py tests/ui/test_history_page.py tests/ui/test_state.py -q --basetemp "$env:TEMP\dlp-web-task8-green"
```

Expected: all selected tests PASS.

- [ ] **Step 7: Commit Task 8**

```powershell
git add src/diagram_langgraph_pipeline/ui/pages/workflow.py src/diagram_langgraph_pipeline/ui/pages/report.py src/diagram_langgraph_pipeline/ui/pages/history.py tests/ui/test_workflow_page.py tests/ui/test_report_page.py tests/ui/test_history_page.py
git commit -m "feat: add persistent research views"
```

---

### Task 9: Port market view, terminal styling, and Streamlit entry point

**Files:**
- Create: `src/diagram_langgraph_pipeline/ui/pages/market.py`
- Create: `src/diagram_langgraph_pipeline/ui/styles.py`
- Create: `streamlit_app.py`
- Modify: `src/diagram_langgraph_pipeline/ui/pages/__init__.py`
- Create: `tests/ui/test_market_page.py`
- Create: `tests/ui/test_streamlit_app.py`

**Interfaces:**
- Consumes: `get_market_chart`, all six page renderers, `create_gateway`, UI state.
- Produces: market chart page, `PAGE_RENDERERS`, and `streamlit_app.main(st_module=None, gateway=None)`.

- [ ] **Step 1: Write market and application-shell tests**

```python
def test_market_page_renders_candles_and_volume():
    gateway = FakeGateway(market_chart=sample_market_chart())
    st = FakeStreamlit(values={"证券代码": "AAPL"})
    render_market(st, gateway, {})
    figure = st.plotly_figures[0]
    assert {trace.type for trace in figure.data} == {"candlestick", "bar"}


def test_application_registers_all_six_pages():
    assert set(PAGE_RENDERERS) == {
        "workspace", "analysis", "workflow", "market", "report", "history"
    }
```

Also test that Gateway configuration errors render a Chinese error and do not crash the app.

- [ ] **Step 2: Run market and shell tests and verify RED**

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pytest tests/ui/test_market_page.py tests/ui/test_streamlit_app.py -q --basetemp "$env:TEMP\dlp-web-task9-red"
```

Expected: collection FAIL because the market page and entry point do not exist.

- [ ] **Step 3: Implement market rendering**

Use `plotly.graph_objects.Candlestick` and `Bar` with a shared date axis. Display API source and updated time. Empty data renders the shared empty state; it must not fabricate prices or indicators.

- [ ] **Step 4: Port and repair terminal styling**

Port the ZIP's dark terminal visual language, but replace all mojibake copy. Keep CSS scoped to Streamlit selectors, preserve visible focus styles, and use readable contrast for required/support/optional/skipped/failed states.

- [ ] **Step 5: Implement the six-page application shell**

Use these stable labels:

```python
PAGE_LABELS = {
    "研究工作台": "workspace",
    "新建分析": "analysis",
    "运行任务": "workflow",
    "行情视图": "market",
    "研究报告": "report",
    "历史记录": "history",
}
```

`main()` configures a wide layout, initializes state, creates one session Gateway, and dispatches through `PAGE_RENDERERS`.

- [ ] **Step 6: Run the complete UI suite**

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pytest tests/ui -q --basetemp "$env:TEMP\dlp-web-task9-green"
```

Expected: all UI tests PASS.

- [ ] **Step 7: Commit Task 9**

```powershell
git add streamlit_app.py src/diagram_langgraph_pipeline/ui tests/ui
git commit -m "feat: complete Streamlit research terminal"
```

---

### Task 10: Add launch scripts, documentation, and end-to-end verification

**Files:**
- Create: `scripts/start_api.ps1`
- Create: `scripts/start_streamlit.ps1`
- Modify: `.env.example`
- Modify: `README.md`
- Create: `tests/api/test_startup.py`
- Create: `tests/test_web_end_to_end.py`

**Interfaces:**
- Consumes: `diagram_langgraph_pipeline.api.app:create_app`, `streamlit_app.py`, existing five-mode offline fixtures.
- Produces: documented local launch commands and automated startup/contract coverage.

- [ ] **Step 1: Write startup import tests**

Create `tests/api/test_startup.py`:

```python
def test_fastapi_app_factory_imports():
    from diagram_langgraph_pipeline.api.app import create_app
    assert callable(create_app)


def test_streamlit_entrypoint_imports_without_starting_server():
    import streamlit_app
    assert callable(streamlit_app.main)


def test_launch_scripts_target_the_api_and_streamlit_entrypoints():
    api_script = Path("scripts/start_api.ps1").read_text(encoding="utf-8")
    ui_script = Path("scripts/start_streamlit.ps1").read_text(encoding="utf-8")
    assert "diagram_langgraph_pipeline.api.app:create_app" in api_script
    assert "--factory" in api_script
    assert "streamlit run streamlit_app.py" in ui_script


def test_env_example_lists_web_runtime_settings():
    text = Path(".env.example").read_text(encoding="utf-8")
    assert "DLP_API_BASE_URL=" in text
    assert "DLP_API_MAX_WORKERS=1" in text
    assert "DLP_CORS_ORIGINS=" in text
```

- [ ] **Step 2: Write five-mode API end-to-end tests**

Create `tests/test_web_end_to_end.py` with a synchronous executor, fake lifecycle repository, and the existing deterministic Router dependencies:

```python
@pytest.mark.parametrize("task_type", list(TaskType))
def test_api_runs_every_router_mode_to_a_terminal_report(task_type):
    app, repository = deterministic_web_app(task_type)
    client = TestClient(app)
    accepted = client.post(
        "/api/v1/analysis-runs",
        json={
            "ticker": "AAPL",
            "task_type": task_type.value,
            "as_of_date": "2026-08-06",
            "investment_horizon": "medium",
            "offline": True,
        },
    )
    run_id = accepted.json()["run_id"]
    run = client.get(f"/api/v1/analysis-runs/{run_id}").json()
    assert run["status"] in {"completed", "degraded"}
    assert client.get(f"/api/v1/analysis-runs/{run_id}/report").status_code == 200
```

- [ ] **Step 3: Run startup and end-to-end tests and verify RED**

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pytest tests/api/test_startup.py tests/test_web_end_to_end.py -q --basetemp "$env:TEMP\dlp-web-task10-red"
```

Expected: FAIL with `FileNotFoundError` for the two launch scripts and missing `DLP_` settings.

- [ ] **Step 4: Add launch scripts**

`scripts/start_api.ps1`:

```powershell
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
& .\.venv\Scripts\python.exe -m uvicorn diagram_langgraph_pipeline.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

`scripts/start_streamlit.ps1`:

```powershell
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not $env:DLP_API_BASE_URL) { $env:DLP_API_BASE_URL = 'http://127.0.0.1:8000' }
& .\.venv\Scripts\python.exe -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

Do not add a production supervisor or hidden combined launcher.

- [ ] **Step 5: Document exact configuration and startup flow**

Add to `.env.example`:

```dotenv
DLP_API_BASE_URL=http://127.0.0.1:8000
DLP_API_MAX_WORKERS=1
DLP_CORS_ORIGINS=http://127.0.0.1:8501,http://localhost:8501
```

README must document installation with `.[web,postgres]`, migration 004, separate API/Streamlit terminals, six pages, five task modes, persistent history, interrupted-run behavior, and the research-only disclaimer.

- [ ] **Step 6: Make end-to-end fixtures use existing deterministic Router data**

Reuse factories from `tests/test_task_router_pipeline.py`; do not duplicate node outputs. Inject the immediate executor and fake lifecycle repository around the real `run_research` path so no network, PostgreSQL, or LLM is called.

- [ ] **Step 7: Run the complete automated suite**

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m pytest -q --basetemp "$env:TEMP\dlp-web-full-suite"
```

Expected: all existing 132 tests and all new API/UI/web tests PASS with zero failures.

- [ ] **Step 8: Run import and help smoke checks**

```powershell
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -c "from diagram_langgraph_pipeline.api.app import create_app; assert callable(create_app)"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -c "import streamlit_app; assert callable(streamlit_app.main)"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m diagram_langgraph_pipeline --help
```

Expected: all commands exit `0`; CLI help still lists `run`, `data`, and `demo`.

- [ ] **Step 9: Verify no old backend package was imported**

```powershell
rg -n "multiple_agent_finance|LocalAnalysisGateway|pymysql|sqlalchemy" src tests streamlit_app.py
```

Expected: no matches. Mentions in design/plan documents are outside this command's scope.

- [ ] **Step 10: Check the final diff and commit Task 10**

```powershell
git diff --check
git status --short
git add scripts/start_api.ps1 scripts/start_streamlit.ps1 .env.example README.md tests/api/test_startup.py tests/test_web_end_to_end.py
git commit -m "docs: add web terminal launch workflow"
```

Expected: `git diff --check` emits no output; the commit contains only Task 10 files.

---

## Final Verification

- [ ] Run `git status --short --branch` and confirm the worktree is clean.
- [ ] Run the complete pytest command from Task 10 again and record the exact pass count.
- [ ] Start FastAPI with a configured test PostgreSQL database and verify `GET /api/v1/health` returns `200` without exposing the DSN.
- [ ] Start Streamlit, navigate through all six pages, submit one offline deterministic task, and verify workflow, report, history, and market pages render without mojibake.
- [ ] Confirm `feature/task-router-publish` and `main` worktrees remain unchanged.
