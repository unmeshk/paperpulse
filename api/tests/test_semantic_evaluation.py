"""Offline evaluation behavior through real SDK transport, ledger, files and review records."""
import copy
import csv
import json
from pathlib import Path

import pytest

from api.evaluate_semantic import (Experiment, PROMPT_HASH, RUBRIC, check_dataset, gate, import_review,
                                   metrics, output_review_packet, read, report, review_packet, run,
                                   safe_output, verify_snapshots, write)
from api.model_budget import BudgetError, ModelBudget, initialize
from api.semantic import batches, identity, parse_response, validate
from api.semantic_capacity import capacity
from api.tests.test_model_budget import Clock, Provider, response


@pytest.fixture
def dataset():
    papers = {f"p{n}": {"id": f"p{n}", "paper_id": f"p{n}", "title": f"Paper {n}",
                         "abstract": f"A supported result. Paper p{n}.", "url": f"https://arxiv.org/abs/p{n}"}
              for n in range(14)}
    interests = {f"i{n}": f"Interest {n}" for n in range(8)}
    pairs = [{"interest": interest, "paper": f"p{n}", "split": "heldout" if n % 2 else "calibration",
              "label": "direct" if n < 2 else "unrelated", "reviewer": "fixture-human", "reviewed_at": "2030-01-02"}
             for interest in interests for n in range(14)]
    sources = []
    for n in range(3):
        paper = {"id": f"q{n}", "paper_id": f"q{n}", "title": "Daily candidate",
                 "abstract": "A supported result.", "url": f"https://arxiv.org/abs/q{n}"}
        papers[paper["id"]] = paper
        sources.append({"category": f"cs.X{n}", "day": "2030-01-02", "status": "complete",
                        "paper_ids": [paper["id"]], "review_interests": [f"i{n}"]})
    return {"version": 1, "papers": papers, "interests": interests, "pairs": pairs, "sources": sources,
            "daily_reviews": {f"i{n}/q{n}": {"label": "direct", "reviewer": "fixture-human"} for n in range(3)}}


@pytest.fixture
def rubric():
    return {"rubric": RUBRIC, "prompt_hash": PROMPT_HASH, "precision_target": .9, "recall_target": .8,
            "approved_by": "fixture-owner", "approved_at": "2030-01-02"}


class SemanticProvider(Provider):
    """Deterministic provider for control flow, not relevance-quality evidence."""

    accepted_ids = {"p0", "p1", "q0", "q1", "q2"}

    def handle(self, request):
        body = json.loads(request.content)
        if request.url.path.endswith(":generateContent"):
            prompt = body["contents"][0]["parts"][0]["text"]
            data = json.loads(prompt.split("\nData: ", 1)[1])
            if "phrase" in data:
                value = {"concept": "A focused concept.", "included_methods": ["One close method"],
                         "exclusions": ["Broad adjacency"], "ambiguity": ""}
            elif "scope" in data:
                value = [{"id": paper["id"], "relevance": "direct" if paper["id"] in self.accepted_ids
                          else "unrelated", "explanation": "A concrete connection."
                          if paper["id"] in self.accepted_ids else "", "evidence": "A supported result."
                          if paper["id"] in self.accepted_ids else ""} for paper in data["papers"]]
            else:
                value = [{"id": paper["id"], "summary": "A supported result."} for paper in data["papers"]]
            self.outcomes.append(response(json.dumps(value)))
        return super().handle(request)


@pytest.fixture
def live_fixture(tmp_path):
    directory = tmp_path / "budget"
    initialize(directory, "2030-01-02", 0, rpm=4000, tpm=4_000_000, rpd=150_000)
    clock = Clock()
    with ModelBudget(directory, clock=clock, sleep=clock.sleep) as budget:
        budget.state["evaluation_enabled"] = True
        budget._save()
        remote = SemanticProvider()
        remote.outcomes = []
        yield budget, remote
        remote.client.close()
        remote.http.close()


def test_shipped_dataset_and_identity_split(dataset):
    shipped = read(Path(__file__).parents[1] / "evaluation/dataset.json")
    counts = check_dataset(shipped)
    verify_snapshots(shipped, Path(__file__).parents[1] / "evaluation")
    assert counts["pairs"] >= 100 and counts["interests"] >= 8 and counts["reviewed_pairs"] == 0
    changed = copy.deepcopy(dataset)
    changed["papers"]["p1"]["paper_id"] = "p0"
    changed["papers"]["p1"]["url"] = "https://arxiv.org/abs/p0v2"
    with pytest.raises(ValueError, match="leaks"):
        check_dataset(changed)
    with pytest.raises(ValueError, match="human review"):
        check_dataset(shipped, reviewed=True)


def test_structured_validation_and_character_bounds(dataset):
    papers = [dataset["papers"]["p0"], dataset["papers"]["p1"]]
    valid = [{"id": paper["id"], "relevance": "direct", "explanation": "Connection.",
              "evidence": "A supported result."} for paper in papers]
    assert validate("match", valid, papers) == valid
    for invalid in [valid[:1], [valid[0], valid[0]], [{**valid[0], "id": "unknown"}, valid[1]],
                    [{**valid[0], "relevance": "maybe"}, valid[1]],
                    [{**valid[0], "evidence": "Invented result."}, valid[1]]]:
        with pytest.raises(ValueError):
            validate("match", invalid, papers)
    assert [len(batch) for batch in batches(papers, size=1)] == [1, 1]
    with pytest.raises(ValueError, match="Oversized"):
        list(batches([{**papers[0], "abstract": "x" * 24001}]))
    with pytest.raises(ValueError, match="Duplicate JSON"):
        parse_response('{"relevance":"direct","relevance":"unrelated"}')


def test_evaluation_disabled_before_any_http(tmp_path):
    directory = tmp_path / "budget"
    initialize(directory, "2030-01-02", 0, rpm=4000, tpm=4_000_000, rpd=150_000)
    remote = SemanticProvider()
    with ModelBudget(directory, clock=Clock()) as budget:
        with pytest.raises(BudgetError, match="activation"):
            Experiment(tmp_path / "experiment", budget, remote.client).call("scope", {"phrase": "x"})
    assert not remote.requests
    remote.client.close()
    remote.http.close()


def test_real_sdk_cache_reuse_and_pinned_heldout(dataset, rubric, live_fixture, tmp_path):
    budget, remote = live_fixture
    output = tmp_path / "experiment"
    path = run(dataset, output, "calibration", 5, budget, remote.client)
    first_requests = len(remote.requests)
    result = read(path)
    assert result["status"] == "complete" and len(result["scopes"]) == 8
    assert len(result["summaries"]) == 1  # Same accepted paper across eight interests.
    assert run(dataset, output, "calibration", 5, budget, remote.client) == path
    assert len(remote.requests) == first_requests
    with pytest.raises(ValueError, match="rubric"):
        run(dataset, output, "heldout", 25, budget, remote.client)
    assert len(remote.requests) == first_requests
    run(dataset, output, "heldout", 25, budget, remote.client, rubric)
    structured = remote.generations[-1]["generationConfig"]
    assert structured["responseMimeType"] == "application/json"
    assert "responseJsonSchema" in structured
    count_body = remote.requests[0][1]["generateContentRequest"]
    assert count_body["generationConfig"]["responseJsonSchema"]
    calls = [read(path) for path in (output / "calls").glob("*.json")]
    assert all(row["telemetry"][0]["thinking_tokens"] == 10 for row in calls)
    assert budget.state["days"]["2030-01-02"]["spent"] == len(calls) * 70000
    analysis = report(dataset, output)
    assert analysis["runs"][1]["quality"]["precision"] == 1
    renamed = copy.deepcopy(dataset)
    renamed["interests"]["i0"] = "Different interest"
    with pytest.raises(ValueError, match="phrases differ"):
        report(renamed, output)


def test_failed_response_is_saved_and_never_silently_recalled(live_fixture, tmp_path):
    budget, remote = live_fixture
    remote = Provider([response('{"concept": "missing fields"}')])
    experiment = Experiment(tmp_path, budget, remote.client)
    with pytest.raises(ValueError):
        experiment.call("scope", {"phrase": "test"})
    record = read(next((tmp_path / "calls").glob("*.json")))
    assert record["status"] == "failed" and record["raw"]
    assert record["telemetry"][0]["output_tokens"] == 30
    with pytest.raises(ValueError, match="Previous failed"):
        experiment.call("scope", {"phrase": "test"})
    assert len(remote.generations) == 1
    remote.client.close()
    remote.http.close()


def test_human_review_preserved_and_missing_summaries_count_as_misses(dataset, tmp_path):
    output = tmp_path / "review"
    review_packet(dataset, output)
    with pytest.raises(ValueError, match="overwrite"):
        review_packet(dataset, output)
    blank = copy.deepcopy(dataset)
    for pair in blank["pairs"]:
        pair.update(label=None, reviewer=None, reviewed_at=None)
    imported = import_review(blank, output / "pairs.csv", "fixture-human")
    assert check_dataset(imported, reviewed=True)["reviewed_pairs"] == 112
    rows = list(csv.DictReader((output / "pairs.csv").open()))
    rows[0]["abstract"] = "Changed source text"
    changed = output / "changed.csv"
    with changed.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="review text differs"):
        import_review(copy.deepcopy(dataset), changed, "fixture-human")
    cases = [{"interest": "i0", "paper": "p0", "label": "direct"}]
    decisions = {"i0/p0": {"relevance": "direct"}}
    assert metrics(cases, decisions, {})["fn"] == 1
    assert metrics(cases, decisions)["tp"] == 1
    assert metrics(cases, {}, {})["recall"] == 0


def test_output_isolation(dataset, tmp_path, monkeypatch):
    data_path = tmp_path / "input/dataset.json"
    write(data_path, dataset)
    monkeypatch.setenv("CONTENT_DIR", str(tmp_path / "content"))
    monkeypatch.setenv("GEMINI_BUDGET_DIR", str(tmp_path / "budget"))
    for output in (tmp_path, data_path.parent / "results", tmp_path / "content/results", tmp_path / "budget/results"):
        with pytest.raises(ValueError, match="overlaps"):
            safe_output(output, data_path)
    with pytest.raises(ValueError, match="overlaps"):
        safe_output(Path(__file__).parents[2] / "content/evaluation", data_path)
    assert safe_output(tmp_path / "isolated", data_path).is_dir()


def test_capacity_pending_and_human_gate(dataset, rubric, live_fixture, tmp_path):
    budget, remote = live_fixture
    remote.accepted_ids = remote.accepted_ids - {"q2"}
    dataset["daily_reviews"]["i2/q2"]["label"] = "unrelated"
    output = tmp_path / "experiment"
    pending = capacity(dataset, [])
    assert all(row["projection"] is None for row in pending["scenarios"])
    run(dataset, output, "heldout", 25, budget, remote.client, rubric)
    for source in dataset["sources"]:
        run(dataset, output, "whole_day", 25, budget, remote.client, rubric, source["category"])
    records = [read(path) for path in (output / "calls").glob("*.json")]
    runs = [read(path) for path in output.glob("run-*.json")]
    projected = capacity(dataset, records, runs=runs, limits={"rpm": 4000, "tpm": 4_000_000, "rpd": 150_000},
                         production_usd=.5, production_seconds=30)
    projected["analysis_hash"] = identity(projected)
    write(output / "capacity.json", projected)
    analysis = report(dataset, output)
    review_path = output_review_packet(output)
    rows = list(csv.DictReader(review_path.open()))
    decision = {"decision": "pass", "reviewer": "fixture-owner", "reviewed_at": "2030-01-02",
                "reason": "Synthetic fixture approves control flow only, not real semantic quality.",
                "report_hash": analysis["analysis_hash"], "capacity_hash": projected["analysis_hash"],
                "delivery_window_seconds": 3600, "finalization_buffer_seconds": 60, "candidate_pool": "cs.X0",
                "batch_size": 25}
    with pytest.raises(ValueError, match="explicit human review"):
        gate(dataset, output, decision)
    for row in rows:
        row["acceptable"] = "yes"
    with review_path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    assert gate(dataset, output, decision)["passed"]
    decision["delivery_window_seconds"] = 1
    with pytest.raises(ValueError, match="delivery window"):
        gate(dataset, output, decision)
