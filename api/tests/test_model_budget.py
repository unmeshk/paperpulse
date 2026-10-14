"""Budget invariants with real files, locks and SDK HTTP serialization; no network."""
from datetime import datetime
import json
import os
import subprocess
import sys

from google import genai
from google.genai import types
import httpx
import pytest

from api.model_budget import (
    BudgetError, BudgetExceeded, DailyQuotaExceeded, ModelBudget, PipelineBusy, RateLimited,
    initialize,
)
from api.model_calls import InvalidModelResponse, ModelUnavailable, SYSTEM_INSTRUCTION, generate_text


class Clock:
    def __init__(self, timestamp=None):
        self.now = timestamp or datetime.fromisoformat("2030-01-02T12:00:00-05:00").timestamp()
        self.waits = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        assert 0 < seconds <= 60
        self.waits.append(seconds)
        self.now += seconds


@pytest.fixture
def ledger(tmp_path):
    directory = tmp_path / "budget"
    initialize(directory, "2030-01-02", 0, rpm=4000, tpm=4_000_000, rpd=150_000)
    return directory


def read_state(directory):
    return json.loads((directory / "ledger.json").read_text())


def response(text="Summary", prompt=100, output=20, thoughts=10, finish="STOP"):
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}],
        "usageMetadata": {
            "promptTokenCount": prompt, "candidatesTokenCount": output,
            "thoughtsTokenCount": thoughts, "totalTokenCount": prompt + output + thoughts,
        },
    }


class Provider:
    """Real SDK against a deterministic in-process HTTP transport."""
    def __init__(self, outcomes=None, count=100):
        self.outcomes = list(outcomes or [response()])
        self.count = count
        self.requests = []
        self.generations = []
        self.http = httpx.Client(transport=httpx.MockTransport(self.handle))
        self.client = genai.Client(api_key="not-a-real-key", vertexai=False,
                                  http_options=types.HttpOptions(httpx_client=self.http))

    def handle(self, request):
        body = json.loads(request.content)
        self.requests.append((request.url.path, body, request.extensions))
        if request.url.path.endswith(":countTokens"):
            return httpx.Response(200, json={"totalTokens": self.count})
        self.generations.append(body)
        outcome = self.outcomes.pop(0)
        if callable(outcome):
            outcome = outcome()
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, tuple):
            return httpx.Response(outcome[0], json=outcome[1], headers=outcome[2] if len(outcome) > 2 else {})
        return httpx.Response(200, json=outcome)

    def close(self):
        self.client.close()


@pytest.fixture
def provider():
    providers = []

    def make(*args, **kwargs):
        value = Provider(*args, **kwargs)
        providers.append(value)
        return value

    yield make
    for value in providers:
        value.close()


def test_full_input_count_and_thinking_usage_reconcile(ledger, provider):
    clock = Clock()
    remote = provider()
    with ModelBudget(ledger, clock=clock, sleep=clock.sleep) as budget:
        assert generate_text(remote.client, budget, "Paper abstract: 量子 😀", 100) == "Summary"
    state = read_state(ledger)
    day = state["days"]["2030-01-02"]
    assert day["spent"] == 100 * 250 + 30 * 1500
    assert day["pending"] == {}
    assert day["input_tokens"] == 100
    assert day["output_tokens"] == 30
    counted = remote.requests[0][1]["generateContentRequest"]
    generated = remote.generations[0]
    assert counted["contents"] == generated["contents"]
    assert counted["systemInstruction"] == generated["systemInstruction"]
    assert counted["systemInstruction"]["parts"][0]["text"] == SYSTEM_INSTRUCTION
    assert generated["generationConfig"]["maxOutputTokens"] == 100
    assert generated["generationConfig"]["candidateCount"] == 1
    assert remote.requests[0][2]["timeout"]["read"] == 60
    assert clock.waits == []


def test_exact_ceiling_and_summary_reserve_survive_restart(ledger):
    clock = Clock()
    with ModelBudget(ledger, clock=clock) as budget:
        # 10M output tokens cost exactly $15; reserve API tests integer arithmetic.
        pending = budget.reserve(0, 10_000_000)
        with pytest.raises(BudgetExceeded):
            budget.reserve(1, 0)
        budget.reconcile(pending, 0, 9_999_999)
        with pytest.raises(BudgetExceeded):
            budget.reserve(0, 1, keep_nanodollars=1)
    with ModelBudget(ledger, clock=clock) as budget:
        budget.reserve(0, 1)
        with pytest.raises(BudgetExceeded):
            budget.reserve(1, 0)


def test_timeout_retry_has_distinct_persisted_reservation(ledger, provider):
    clock = Clock()
    observed = []

    def timeout():
        state = read_state(ledger)
        observed.append(len(state["days"]["2030-01-02"]["pending"]))
        raise httpx.ReadTimeout("simulated")

    remote = provider([timeout, response()])
    with ModelBudget(ledger, clock=clock, sleep=clock.sleep) as budget:
        assert generate_text(remote.client, budget, "paper", 100) == "Summary"
    day = read_state(ledger)["days"]["2030-01-02"]
    assert observed == [1]  # on disk before the provider receives anything
    assert len(remote.generations) == 2
    assert len(day["pending"]) == 1
    assert next(iter(day["pending"].values()))["amount"] == 132 * 250 + 100 * 1500
    assert day["spent"] == 100 * 250 + 30 * 1500
    assert clock.waits == [1]
    with ModelBudget(ledger, clock=clock) as budget:
        assert budget.state["days"]["2030-01-02"]["pending"] == day["pending"]


def test_sdk_never_performs_unreserved_hidden_retries(ledger, provider):
    clock = Clock()
    remote = provider([(503, {"error": {"message": "unavailable"}})] * 3)
    with ModelBudget(ledger, clock=clock, sleep=clock.sleep) as budget:
        with pytest.raises(ModelUnavailable):
            generate_text(remote.client, budget, "paper")
    assert len(remote.generations) == 3
    assert len(read_state(ledger)["days"]["2030-01-02"]["pending"]) == 3
    assert clock.waits == [1, 2]


@pytest.mark.parametrize("bad", [
    {"candidates": [{"content": {"parts": [{"text": "summary"}]}, "finishReason": "STOP"}]},
    {**response(), "usageMetadata": {"promptTokenCount": 100}},
    {**response(), "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 20,
                                     "thoughtsTokenCount": 10, "totalTokenCount": 120}},
])
def test_unknown_usage_never_refunds_reservation(ledger, provider, bad):
    clock = Clock()
    remote = provider([bad])
    with ModelBudget(ledger, clock=clock) as budget:
        with pytest.raises(BudgetError, match="usage"):
            generate_text(remote.client, budget, "paper", 100)
    day = read_state(ledger)["days"]["2030-01-02"]
    assert day["spent"] == 0
    assert len(day["pending"]) == 1
    assert len(remote.generations) == 1


def test_usage_beyond_reserved_bounds_halts_future_calls(ledger, provider):
    clock = Clock()
    remote = provider([response(prompt=200)])
    with ModelBudget(ledger, clock=clock) as budget:
        with pytest.raises(BudgetError, match="exceeded"):
            generate_text(remote.client, budget, "paper", 100)
    with ModelBudget(ledger, clock=clock) as budget:
        with pytest.raises(BudgetError, match="review"):
            generate_text(remote.client, budget, "paper", 100)
    assert len(remote.generations) == 1
    assert read_state(ledger)["days"]["2030-01-02"]["spent"] == 200 * 250 + 30 * 1500


@pytest.mark.parametrize("finish,text", [("MAX_TOKENS", "cut off"), ("STOP", "")])
def test_invalid_output_is_charged_and_retries_bounded(ledger, provider, finish, text):
    clock = Clock()
    remote = provider([response(text=text, finish=finish)] * 3)
    with ModelBudget(ledger, clock=clock, sleep=clock.sleep) as budget:
        with pytest.raises(InvalidModelResponse):
            generate_text(remote.client, budget, "paper", 100)
    day = read_state(ledger)["days"]["2030-01-02"]
    assert day["spent"] == 3 * (100 * 250 + 30 * 1500)
    assert day["pending"] == {}
    assert len(remote.generations) == 3


def test_daily_quota_persists_until_pacific_not_new_york_midnight(ledger, provider):
    clock = Clock(datetime.fromisoformat("2030-01-02T23:59:00-05:00").timestamp())
    remote = provider([(429, {"error": {"details": [{"violations": [
        {"quotaId": "GenerateRequestsPerDayPerProjectPerModel"}]}]}}), response()])
    with ModelBudget(ledger, clock=clock) as budget:
        with pytest.raises(DailyQuotaExceeded):
            generate_text(remote.client, budget, "paper", 100)
    clock.now += 120  # New York budget rolls over; provider quota does not.
    with ModelBudget(ledger, clock=clock) as budget:
        with pytest.raises(DailyQuotaExceeded):
            generate_text(remote.client, budget, "paper", 100)
    assert len(remote.generations) == 1
    clock.now += 3 * 3600
    with ModelBudget(ledger, clock=clock) as budget:
        assert generate_text(remote.client, budget, "paper", 100) == "Summary"
    state = read_state(ledger)
    assert len(state["days"]["2030-01-02"]["pending"]) == 1
    assert state["days"]["2030-01-03"]["spent"] > 0


def test_retry_guidance_and_unknown_429_have_bounded_wait(ledger, provider):
    clock = Clock()
    remote = provider([(429, {"error": {"details": [{"retryDelay": "7s"}]}}, {"retry-after": "12"}), response()])
    with ModelBudget(ledger, clock=clock, sleep=clock.sleep) as budget:
        assert generate_text(remote.client, budget, "paper", 100) == "Summary"
    assert clock.waits == [12]
    remote = provider([(429, {"error": {}}, {"retry-after": "3600"})])
    with ModelBudget(ledger, clock=clock, sleep=clock.sleep) as budget:
        with pytest.raises(RateLimited):
            generate_text(remote.client, budget, "paper", 100)
    with ModelBudget(ledger, clock=clock, sleep=clock.sleep) as budget:
        with pytest.raises(RateLimited):
            generate_text(remote.client, budget, "paper", 100)
    assert len(remote.generations) == 1


def test_request_and_token_pacing_survive_restart(ledger):
    clock = Clock()
    with ModelBudget(ledger, clock=clock, sleep=clock.sleep) as budget:
        budget.state["limits"]["rpm"] = 2
        budget.state["limits"]["tpm"] = 100
        budget.reserve(60, 0)
    with ModelBudget(ledger, clock=clock, sleep=clock.sleep) as budget:
        budget.reserve(60, 0)
        assert clock.waits == [60]
        budget.reserve(0, 0)
        budget.reserve(0, 0)
        assert clock.waits == [60, 60]
        with pytest.raises(RateLimited):
            budget.reserve(101, 0)


@pytest.mark.parametrize("hour", ["2030-03-10T01:59:00-05:00", "2030-11-03T01:59:00-04:00"])
def test_dst_does_not_reset_new_york_budget(ledger, hour):
    clock = Clock(datetime.fromisoformat(hour).timestamp())
    with ModelBudget(ledger, clock=clock) as budget:
        budget.reserve(0, 10_000_000)
    clock.now += 120
    with ModelBudget(ledger, clock=clock) as budget:
        with pytest.raises(BudgetExceeded):
            budget.reserve(0, 1)


def test_call_crossing_midnight_reconciles_dispatch_day(ledger, provider):
    clock = Clock(datetime.fromisoformat("2030-01-02T23:59:59-05:00").timestamp())

    def finish_next_day():
        clock.now += 2
        return response()

    remote = provider([finish_next_day, response()])
    with ModelBudget(ledger, clock=clock) as budget:
        generate_text(remote.client, budget, "paper", 100)
        generate_text(remote.client, budget, "paper", 100)
    state = read_state(ledger)
    for key in ("2030-01-02", "2030-01-03"):
        assert state["days"][key]["spent"] == 100 * 250 + 30 * 1500
        assert state["days"][key]["pending"] == {}
    assert len(state["quota_days"]) == 1


def test_evaluation_uses_production_balance_only_after_activation(ledger, provider):
    clock = Clock()
    remote = provider()
    with ModelBudget(ledger, clock=clock) as budget:
        with pytest.raises(BudgetError, match="evaluation"):
            generate_text(remote.client, budget, "paper", purpose="evaluation")
        assert remote.requests == []
        budget.state["evaluation_enabled"] = True
        budget._save()
        budget.reserve(0, 10_000_000)
    with ModelBudget(ledger, clock=clock) as budget:
        with pytest.raises(BudgetExceeded):
            generate_text(remote.client, budget, "paper", purpose="evaluation")
        assert remote.generations == []


def test_missing_corrupt_and_deleted_ledgers_fail_closed(ledger):
    clock = Clock()
    with pytest.raises(BudgetError):
        with ModelBudget(ledger / "missing", clock=clock):
            pass
    for content in ("{bad json", "{}", '{"version": 1}', 'null'):
        (ledger / "ledger.json").write_text(content)
        with pytest.raises(BudgetError):
            with ModelBudget(ledger, clock=clock):
                pass
    (ledger / "ledger.json").unlink()
    with pytest.raises(BudgetError):
        with ModelBudget(ledger, clock=clock):
            pass


def test_reservation_write_failure_prevents_dispatch(ledger, provider, monkeypatch):
    clock = Clock()
    remote = provider()
    original = os.replace
    calls = 0

    def fail_reservation(source, target):
        nonlocal calls
        calls += 1
        if calls >= 3:  # count request reserve/reconcile succeed, paid reservation fails
            raise OSError("disk full")
        return original(source, target)

    with ModelBudget(ledger, clock=clock) as budget:
        monkeypatch.setattr(os, "replace", fail_reservation)
        with pytest.raises(BudgetError, match="durably"):
            generate_text(remote.client, budget, "paper")
        with pytest.raises(BudgetError):
            budget.reserve(0, 1)
    assert remote.generations == []


def test_reconcile_write_failure_retains_disk_reservation(ledger, provider, monkeypatch):
    clock = Clock()
    remote = provider()
    original = os.replace
    calls = 0

    def fail_reconciliation(source, target):
        nonlocal calls
        calls += 1
        if calls == 4:
            raise OSError("disk full")
        return original(source, target)

    with ModelBudget(ledger, clock=clock) as budget:
        monkeypatch.setattr(os, "replace", fail_reconciliation)
        with pytest.raises(BudgetError):
            generate_text(remote.client, budget, "paper")
    monkeypatch.setattr(os, "replace", original)
    with ModelBudget(ledger, clock=clock) as budget:
        assert len(budget.state["days"]["2030-01-02"]["pending"]) == 1


def test_process_crash_releases_lock_but_preserves_reservation(ledger):
    script = """
import os
from api.model_budget import ModelBudget
with ModelBudget(os.environ['TEST_LEDGER'], clock=lambda: 1893589200.0) as budget:
    budget.reserve(0, 10_000_000)
    os._exit(17)
"""
    result = subprocess.run([sys.executable, "-c", script], env={**os.environ, "TEST_LEDGER": str(ledger)},
                            capture_output=True, timeout=10)
    assert result.returncode == 17, result.stderr.decode()
    with ModelBudget(ledger, clock=lambda: 1893589201.0) as budget:
        with pytest.raises(BudgetExceeded):
            budget.reserve(1, 0)


def test_competing_process_cannot_acquire_lock(ledger):
    script = """
import os
from api.model_budget import ModelBudget, PipelineBusy
try:
    with ModelBudget(os.environ['TEST_LEDGER']):
        raise SystemExit(2)
except PipelineBusy:
    raise SystemExit(0)
"""
    with ModelBudget(ledger):
        result = subprocess.run([sys.executable, "-c", script], env={**os.environ, "TEST_LEDGER": str(ledger)},
                                capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr.decode()


def test_initialization_never_replaces_ledger_and_future_start_blocks(ledger):
    before = (ledger / "ledger.json").read_bytes()
    with pytest.raises(BudgetError, match="already exists"):
        initialize(ledger, "2030-01-02", 0, rpm=10, tpm=1000, rpd=100)
    assert (ledger / "ledger.json").read_bytes() == before
    with ModelBudget(ledger) as budget:
        with pytest.raises(BudgetError, match="not started"):
            budget.reserve(0, 1)


def test_cli_seeds_verified_spend_and_gates_evaluation(tmp_path):
    from zoneinfo import ZoneInfo

    env = {**os.environ, "GEMINI_BUDGET_DIR": str(tmp_path)}
    command = [sys.executable, "-m", "api.model_budget"]
    day = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    result = subprocess.run(command + ["initialize", "--start-day", day, "--opening-spend-usd", "14.999999999",
                                      "--rpm", "4000", "--tpm", "4000000", "--rpd", "150000",
                                      "--untracked-workers-stopped"], env=env, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr.decode()
    with ModelBudget(tmp_path) as budget:
        with pytest.raises(BudgetExceeded):
            budget.reserve(1, 0)
    result = subprocess.run(command + ["enable-evaluation", "--production-controls-verified"], env=env,
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr.decode()
    assert read_state(tmp_path)["evaluation_enabled"] is True


def test_budget_context_rejects_concurrent_thread_use(ledger):
    from concurrent.futures import ThreadPoolExecutor

    with ModelBudget(ledger, clock=Clock()) as budget, ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(BudgetError, match="threads"):
            pool.submit(budget.reserve, 100, 100).result()
    assert read_state(ledger)["days"]["2030-01-02"]["calls"] == 0


def test_backward_clock_cannot_refund_or_open_new_budget(ledger):
    clock = Clock()
    with ModelBudget(ledger, clock=clock) as budget:
        budget.reserve(100, 100)
    clock.now -= 1
    with ModelBudget(ledger, clock=clock) as budget:
        with pytest.raises(BudgetError, match="backwards"):
            budget.reserve(100, 100)


@pytest.fixture
def pipeline(tmp_path, monkeypatch, provider):
    from zoneinfo import ZoneInfo
    from api import settings
    from api import agent as agent_module

    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    from api import main as main_module

    directory = tmp_path / "budget"
    day = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    initialize(directory, day, 0, rpm=4000, tpm=4_000_000, rpd=150_000)
    monkeypatch.setenv("GEMINI_BUDGET_DIR", str(directory))
    monkeypatch.setenv("PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("PROJECT_ENV", "prod")
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-key")
    monkeypatch.setattr(settings, "CONTENT_DIR", str(tmp_path / "content"))
    # Missing app SQLite must not bypass accounting for the public fallback.
    monkeypatch.setattr(settings, "APP_DB_PATH", str(tmp_path / "missing.sqlite"))
    (tmp_path / "blog" / "_posts").mkdir(parents=True)
    remote = provider([response(), response()])
    monkeypatch.setattr(agent_module, "create_client", lambda key: remote.client)
    paper = {"title": "Paper", "authors": ["Author"], "summary": "Abstract", "url": "https://arxiv.org/abs/1234.5678"}
    monkeypatch.setattr(main_module.ArxivClient, "retrieve_daily_results", lambda self: [paper])
    monkeypatch.setattr(main_module.ArxivClient, "retrieve_results_by_category", lambda self, slugs: {"cs.AI": [paper]})
    return main_module, directory, remote, day


def test_public_category_fallback_and_rerun_share_one_ledger(pipeline, tmp_path):
    main_module, directory, remote, day = pipeline
    assert main_module.main() == 0
    assert list((tmp_path / "blog" / "_posts").glob("*.markdown"))
    assert (tmp_path / "content" / day / "cs.AI.md").read_text() == "Summary"
    assert read_state(directory)["days"][day]["spent"] == 2 * 70_000
    remote.outcomes = [response(), response()]
    assert main_module.main() == 0
    assert read_state(directory)["days"][day]["spent"] == 4 * 70_000
    assert len(remote.generations) == 4


def test_pipeline_missing_ledger_stops_before_retrieval(pipeline, monkeypatch):
    main_module, directory, remote, day = pipeline
    (directory / "ledger.json").unlink()

    def forbidden(*args):
        pytest.fail("Retrieval occurred without accounting")

    monkeypatch.setattr(main_module.ArxivClient, "retrieve_daily_results", forbidden)
    assert main_module.main() == 1
    assert remote.requests == []


def test_duplicate_pipeline_skips_all_work(pipeline, monkeypatch):
    main_module, directory, remote, day = pipeline
    with ModelBudget(directory):
        assert main_module.main() == 0
    assert remote.requests == []


def test_budget_exhaustion_keeps_completed_public_output(pipeline, tmp_path):
    main_module, directory, remote, day = pipeline
    with ModelBudget(directory) as budget:
        budget.state["days"][day]["spent"] = 15_000_000_000 - (132 * 250 + 5000 * 1500)
        budget._save()
    remote.outcomes = [response(output=4990, thoughts=10)]
    assert main_module.main() == 1
    assert len(remote.generations) == 1
    posts = list((tmp_path / "blog" / "_posts").glob("*.markdown"))
    assert len(posts) == 1 and "Summary" in posts[0].read_text()
    assert not (tmp_path / "content").exists()
    assert read_state(directory)["days"][day]["spent"] <= 15_000_000_000


def test_budget_exhaustion_preserves_completed_batch_without_paid_combine(pipeline, tmp_path, monkeypatch):
    from api.agent import Agent

    main_module, directory, remote, day = pipeline
    with ModelBudget(directory) as budget:
        budget.state["days"][day]["spent"] = 15_000_000_000 - (132 * 250 + 5000 * 1500)
        budget._save()
    monkeypatch.setattr(Agent, "_batch_papers", lambda self, papers, *args: [papers, papers])
    remote.outcomes = [response(output=4990, thoughts=10)]
    assert main_module.main() == 1
    assert len(remote.generations) == 1
    posts = list((tmp_path / "blog" / "_posts").glob("*.markdown"))
    assert len(posts) == 1 and "Summary" in posts[0].read_text()


def test_accounting_halt_is_not_swallowed_by_category_writer(tmp_path):
    from api.feeds import generate_category_blurbs

    class StoppedAgent:
        def identify_important_papers(self, papers):
            raise BudgetError("ledger unavailable")

    with pytest.raises(BudgetError):
        generate_category_blurbs({"cs.AI": [{}]}, StoppedAgent(), tmp_path, "2030-01-02")
    assert list(tmp_path.iterdir()) == []


def test_invalid_count_never_dispatches_paid_generation(ledger, provider):
    clock = Clock()
    remote = provider(count=None)
    with ModelBudget(ledger, clock=clock, sleep=clock.sleep) as budget:
        with pytest.raises(InvalidModelResponse):
            generate_text(remote.client, budget, "paper")
    assert len(remote.requests) == 3
    assert remote.generations == []
    assert read_state(ledger)["days"]["2030-01-02"]["spent"] == 0


def test_permanent_provider_error_does_not_retry(ledger, provider):
    remote = provider([(403, {"error": {"message": "secret prompt must not enter logs"}})])
    with ModelBudget(ledger, clock=Clock()) as budget:
        with pytest.raises(ModelUnavailable, match="HTTP 403") as exc:
            generate_text(remote.client, budget, "paper")
    assert "secret" not in str(exc.value)
    assert len(remote.generations) == 1
    assert len(read_state(ledger)["days"]["2030-01-02"]["pending"]) == 1


@pytest.mark.parametrize("field,value", [("spent", -1), ("spent", True), ("pending", []), ("calls", "0")])
def test_invalid_accounting_fields_fail_closed(ledger, field, value):
    state = read_state(ledger)
    state["days"]["2030-01-02"][field] = value
    (ledger / "ledger.json").write_text(json.dumps(state))
    with pytest.raises(BudgetError):
        with ModelBudget(ledger):
            pytest.fail("Invalid ledger accepted")


def test_daily_request_guard_survives_restart(ledger):
    clock = Clock()
    with ModelBudget(ledger, clock=clock) as budget:
        budget.state["limits"]["rpd"] = 1
        budget.reserve(0, 1)
    with ModelBudget(ledger, clock=clock) as budget:
        with pytest.raises(DailyQuotaExceeded):
            budget.reserve(0, 1)


def test_completed_batches_publish_when_combine_would_exceed_budget(pipeline, tmp_path, monkeypatch):
    from api.agent import Agent

    main_module, directory, remote, day = pipeline
    with ModelBudget(directory) as budget:
        budget.state["days"][day]["spent"] = 15_000_000_000 - 2 * (132 * 250 + 5000 * 1500)
        budget._save()
    monkeypatch.setattr(Agent, "_batch_papers", lambda self, papers, *args: [papers, papers])
    remote.outcomes = [response(text="First", output=4990, thoughts=10),
                       response(text="Second", output=4990, thoughts=10)]
    assert main_module.main() == 1
    assert len(remote.generations) == 2
    posts = list((tmp_path / "blog" / "_posts").glob("*.markdown"))
    assert len(posts) == 1 and "First\n\nSecond" in posts[0].read_text()
