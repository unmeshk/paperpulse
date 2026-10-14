"""Isolated, opt-in semantic evaluation; ordinary CI never dispatches paid calls.

Run ``python -m api.evaluate_semantic --help`` for offline and live commands.
"""
import argparse
import csv
import gzip
import hashlib
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import math
import os
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as ET

from api.arxiv_client import ArxivClient
from api.model_budget import BudgetError, ModelBudget
from api.model_calls import create_client, generate_text
from api.semantic import LABELS, VERSION, batches, identity, parse_response, request, validate
from api.semantic_capacity import capacity
from api.settings import (GEMINI_INPUT_NANODOLLARS, GEMINI_MODEL, GEMINI_OUTPUT_NANODOLLARS,
                          budget_directory, get_secret)

DATASET_VERSION = 1
PROMPT_HASH = identity([VERSION, *(request(stage, {}) for stage in ("scope", "match", "summary"))])
RUBRIC = (
    "direct: main contribution concerns the conventional focused concept. "
    "close: substantive connection explicitly included in that scope. "
    "unrelated: broad adjacency, incidental wording, excluded methods or uncertain connection. "
    "Accept direct and close. Judge title and abstract only, never the model's decision as ground truth. "
    "Record ambiguity for owner resolution. Review generated scopes, explanations and summaries separately. "
    "Unsupported claims include stronger findings than the abstract reports. Missing decisions or summaries "
    "are delivery failures, not negatives removed from scoring."
)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    """Atomically store local experiment artifacts, never public feed files."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")
        temporary = Path(file.name)
    temporary.replace(path)


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def capture_rss(category, path):
    """Read a downloaded RSS snapshot, retaining complete latest-date membership."""
    raw = Path(path).read_bytes()
    if Path(path).suffix == ".gz":
        raw = gzip.decompress(raw)
    root = ET.fromstring(raw)
    items = root.findall(".//item")
    if not items:
        raise ValueError("Snapshot has no items; cannot establish a complete daily batch")
    dates = [parsedate_to_datetime(item.findtext("pubDate") or "").date() for item in items]
    source_day = max(dates)
    papers = {}
    revisions = {}
    client = ArxivClient()
    for item, day in zip(items, dates):
        if day != source_day:
            continue
        entry = client._process_paper_entry(item)
        if not entry["title"] or not entry["summary"] or not entry["url"].startswith("https://arxiv.org/abs/"):
            raise ValueError("Incomplete paper input or unexpected source URL")
        canonical = re.sub(r"v\d+$", "", entry["url"].removeprefix("https://arxiv.org/abs/"))
        paper_id = canonical + "-" + identity([entry["title"], entry["summary"]])[:12]
        paper = {"id": paper_id, "paper_id": canonical, "title": entry["title"],
                 "abstract": entry["summary"], "url": entry["url"]}
        if canonical in revisions and revisions[canonical] != paper_id:
            raise ValueError("Conflicting paper revisions within snapshot")
        revisions[canonical] = paper_id
        if paper_id in papers and papers[paper_id] != paper:
            raise ValueError("Conflicting paper revisions within snapshot")
        papers[paper_id] = paper
    source = {"category": category, "day": source_day.isoformat(), "captured_at": timestamp(),
              "url": f"https://rss.arxiv.org/rss/{category}", "raw_sha256": hashlib.sha256(raw).hexdigest(),
              "paper_ids": sorted(papers), "status": "complete"}
    return source, papers


def check_dataset(data, *, reviewed=False):
    if data.get("version") != DATASET_VERSION:
        raise ValueError("Unsupported evaluation dataset version")
    papers = data["papers"]
    interests = data["interests"]
    if not isinstance(papers, dict) or len(interests) < 8 or len(data["pairs"]) < 100:
        raise ValueError("Need at least 100 pairs and eight interests")
    for paper_id, paper in papers.items():
        if paper.get("id") != paper_id or not all(isinstance(paper.get(key), str) and paper[key].strip()
                                                 for key in ("title", "abstract", "url", "paper_id")):
            raise ValueError("Invalid immutable paper input")
        canonical = re.sub(r"v\d+$", "", paper["url"].removeprefix("https://arxiv.org/abs/"))
        if not paper["url"].startswith("https://arxiv.org/abs/") or paper["paper_id"] != canonical:
            raise ValueError("Paper identity must match its canonical arXiv URL")
    for phrase in interests.values():
        if not isinstance(phrase, str) or not 1 <= len(phrase.strip()) <= 100:
            raise ValueError("Invalid interest phrase")
    seen = set()
    splits = {}
    interest_splits = set()
    for pair in data["pairs"]:
        key = (pair["interest"], pair["paper"])
        if key in seen or key[0] not in interests or key[1] not in papers:
            raise ValueError("Duplicate or unknown evaluation pair")
        seen.add(key)
        split = pair["split"]
        canonical = re.sub(r"v\d+$", "", papers[key[1]]["paper_id"])
        if split not in ("calibration", "heldout") or splits.setdefault(canonical, split) != split:
            raise ValueError("Paper identity leaks between calibration and held-out data")
        interest_splits.add((key[0], split))
        if pair.get("label") not in (*LABELS, None):
            raise ValueError("Invalid human label")
        if reviewed and (pair.get("label") is None or not pair.get("reviewer") or not pair.get("reviewed_at")):
            raise ValueError("Every curated pair needs human review before scoring")
    if any((interest, split) not in interest_splits for interest in interests for split in ("calibration", "heldout")):
        raise ValueError("Every interest needs calibration and held-out cases")
    for source in data.get("sources", []):
        ids = source["paper_ids"]
        if source["status"] != "complete" or not ids or len(set(ids)) != len(ids) or set(ids) - papers.keys():
            raise ValueError("Incomplete source snapshot")
        if any(splits.get(papers[key]["paper_id"]) == "calibration" for key in ids):
            raise ValueError("Whole-day review leaks calibration paper identities")
        if not source.get("review_interests") or set(source["review_interests"]) - interests.keys():
            raise ValueError("Unknown complete-day review interest")
    return {"papers": len(papers), "pairs": len(seen), "interests": len(interests),
            "reviewed_pairs": sum(pair.get("label") is not None and bool(pair.get("reviewer"))
                                  and bool(pair.get("reviewed_at")) for pair in data["pairs"]),
            "splits": {split: sum(pair["split"] == split for pair in data["pairs"])
                       for split in ("calibration", "heldout")},
            "sources": [{key: source[key] for key in ("category", "day", "status")} |
                        {"papers": len(source["paper_ids"])} for source in data.get("sources", [])]}


def verify_snapshots(data, root):
    """Prove saved whole-day candidate membership matches the archived raw source."""
    root = Path(root).resolve()
    for source in data["sources"]:
        path = (root / source["snapshot_file"]).resolve()
        if root not in path.parents:
            raise ValueError("Snapshot path escapes source archive")
        actual, papers = capture_rss(source["category"], path)
        if any(actual[key] != source[key] for key in ("day", "raw_sha256", "paper_ids", "status")):
            raise ValueError("Candidate membership differs from archived complete-day source")
        if any(data["papers"].get(key) != paper for key, paper in papers.items()):
            raise ValueError("Paper inputs differ from archived RSS source")


def safe_output(path, dataset):
    """Keep live writes outside production paths, source data and authoritative accounting."""
    path = Path(path).resolve()
    repository = Path(__file__).resolve().parents[1]
    protected = [Path(dataset).resolve().parent, repository / "blog", repository / "content"]
    for name in ("CONTENT_DIR", "GEMINI_BUDGET_DIR"):
        if os.getenv(name):
            protected.append(Path(os.environ[name]).resolve())
    for root in protected:
        if path == root or root in path.parents or path in root.parents:
            raise ValueError("Evaluation output overlaps source, public content or accounting storage")
    path.mkdir(parents=True, exist_ok=True)
    return path


def rubric_check(rubric):
    if (not rubric.get("approved_by") or not rubric.get("approved_at") or rubric.get("rubric") != RUBRIC
            or rubric.get("prompt_hash") != PROMPT_HASH):
        raise ValueError("Owner-approved rubric and frozen prompt version required for held-out evaluation")
    for key in ("precision_target", "recall_target"):
        if type(rubric.get(key)) not in (int, float) or not 0 < rubric[key] <= 1:
            raise ValueError("Numeric owner-approved quality targets required")


def review_packet(data, output):
    """Export human labels and complete-day candidates without model-derived ground truth."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    names = ["pairs", *(f"daily-{source['category']}-{source['day']}" for source in data.get("sources", []))]
    if any(path.exists() for path in [output / "rubric.json", *(output / f"{name}.csv" for name in names)]):
        raise ValueError("Refusing to overwrite existing human review work")
    write(output / "rubric.json", {"rubric": RUBRIC, "prompt_hash": PROMPT_HASH, "precision_target": .9,
                                   "recall_target": .8, "approved_by": None, "approved_at": None})
    for name, rows in [("pairs", data["pairs"]), *( (f"daily-{source['category']}-{source['day']}",
                       [{"interest": interest, "paper": paper_id, "split": "whole_day", "label": None}
                        for interest in source["review_interests"] for paper_id in source["paper_ids"]])
                      for source in data.get("sources", []))]:
        path = output / f"{name}.csv"
        if path.exists():
            raise ValueError(f"Refusing to overwrite review work: {path}")
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=["interest", "paper", "split", "phrase", "title", "url",
                                                      "abstract", "label", "note"])
            writer.writeheader()
            for row in rows:
                paper = data["papers"][row["paper"]]
                writer.writerow({**{key: row.get(key, "") for key in ("interest", "paper", "split", "label", "note")},
                                 "phrase": data["interests"][row["interest"]],
                                 **{key: paper[key] for key in ("title", "url", "abstract")}})


def import_review(data, path, reviewer):
    """Record explicitly supplied human judgments; never fill missing judgments with predictions."""
    if not reviewer.strip():
        raise ValueError("Reviewer identity required")
    pairs = {(row["interest"], row["paper"]): row for row in data["pairs"]}
    daily = {(interest, paper_id) for source in data.get("sources", [])
             for interest in source["review_interests"] for paper_id in source["paper_ids"]}
    seen = set()
    for row in csv.DictReader(Path(path).open(encoding="utf-8", newline="")):
        key = (row["interest"], row["paper"])
        if key in seen or (key not in pairs and key not in daily):
            raise ValueError("Duplicate or unknown review ID")
        seen.add(key)
        paper = data["papers"][key[1]]
        if (row.get("phrase") != data["interests"][key[0]]
                or any(row.get(field) != paper[field] for field in ("title", "url", "abstract"))):
            raise ValueError("Human review text differs from frozen dataset")
        if not row["label"]:
            continue
        if row["label"] not in LABELS:
            raise ValueError("Human labels must be direct, close or unrelated")
        review = {"label": row["label"], "note": row.get("note", ""),
                  "reviewer": reviewer, "reviewed_at": timestamp()}
        if row["split"] == "whole_day" and key in daily:
            data.setdefault("daily_reviews", {})["/".join(key)] = review
        elif key in pairs and row["split"] == pairs[key]["split"]:
            pairs[key].update(review)
        else:
            raise ValueError("Review split does not match frozen dataset")
    return data


class Experiment:
    """Content-addressed successful response cache, sharing the production lock and ledger."""

    def __init__(self, output, budget, client):
        self.output, self.budget, self.client = Path(output), budget, client
        self.used = set()

    def call(self, stage, data, papers=()):
        prompt, schema, cap = request(stage, data)
        contract = {"stage": stage, "model": GEMINI_MODEL, "version": VERSION, "prompt": prompt, "data": data,
                    "schema": schema, "max_tokens": cap}
        key = identity(contract)
        self.used.add(key)
        path = self.output / "calls" / f"{key}.json"
        if path.exists():
            record = read(path)
            if record.get("contract") != contract:
                raise ValueError("Experiment cache contract mismatch")
            if record.get("status") != "success":
                raise ValueError("Previous failed call retained; review it before creating another experiment")
            return validate(stage, record["parsed"], papers)
        record = {"contract": contract, "started_at": timestamp(), "telemetry": [], "status": "started",
                  "paper_count": len(papers), "input_characters": len(prompt)}
        # A crash after dispatch retains both its ledger reservation and an unfinished artifact.
        write(path, record)
        try:
            raw = generate_text(self.client, self.budget, prompt, cap, purpose="evaluation",
                                response_schema=schema, telemetry=record["telemetry"])
            record["raw"] = raw
            record["parsed"] = parse_response(raw)
            result = validate(stage, record["parsed"], papers)
            record["status"] = "success"
            return result
        except Exception as error:
            record.update(status="failed", error=type(error).__name__)
            raise
        finally:
            record["finished_at"] = timestamp()
            write(path, record)


def run(data, output, split, size, budget, client, rubric=None, category=None):
    check_dataset(data)
    if split not in ("calibration", "heldout", "whole_day") or type(size) is not int or not 1 <= size <= 25:
        raise ValueError("Invalid experiment split or batch size")
    if split in ("heldout", "whole_day"):
        rubric_check(rubric or {})
    budget.check_ready("evaluation")
    experiment = Experiment(output, budget, client)
    if split == "whole_day":
        sources = [source for source in data.get("sources", []) if source["category"] == category]
        if len(sources) != 1:
            raise ValueError("Select one captured complete-day category")
        source = sources[0]
        cases = [{"interest": interest, "paper": paper_id} for interest in source["review_interests"]
                 for paper_id in source["paper_ids"]]
    else:
        cases = [pair for pair in data["pairs"] if pair["split"] == split]
    list(batches([data["papers"][key] for key in dict.fromkeys(case["paper"] for case in cases)], size=size))
    # Freeze membership and prompts before the first paid request. Labels may be reviewed separately.
    contract = {"split": split, "category": category, "size": size, "prompt_hash": PROMPT_HASH,
                "papers": {case["paper"]: data["papers"][case["paper"]] for case in cases},
                "interests": data["interests"], "cases": [{key: row[key] for key in ("interest", "paper")}
                                                          for row in cases],
                "quota_limits": dict(budget.state["limits"]),
                "rubric": rubric if split in ("heldout", "whole_day") else None}
    key = identity(contract)
    path = Path(output) / f"run-{key}.json"
    if path.exists():
        result = read(path)
        if result["contract"] != contract:
            raise ValueError("Frozen experiment contract mismatch")
    else:
        result = {"contract": contract, "started_at": timestamp(), "status": "started",
                  "scopes": {}, "decisions": {}, "summaries": {}, "call_ids": []}
        write(path, result)
    def checkpoint():
        result["call_ids"] = sorted(set(result.get("call_ids", [])) | experiment.used)
        write(path, result)
    try:
        accepted = {}
        for interest in sorted({case["interest"] for case in cases}):
            scope = experiment.call("scope", {"phrase": data["interests"][interest]})
            result["scopes"][interest] = scope
            candidates = [data["papers"][case["paper"]] for case in cases if case["interest"] == interest]
            for batch in batches(candidates, size=size):
                decisions = experiment.call("match", {"scope": scope, "papers": batch}, batch)
                for decision in decisions:
                    result["decisions"][f"{interest}/{decision['id']}"] = decision
                    if decision["relevance"] != "unrelated":
                        accepted[decision["id"]] = data["papers"][decision["id"]]
                checkpoint()
                # Complete accepted work promptly; generic summaries are reused across interests.
                missing = [paper for paper_id, paper in accepted.items() if paper_id not in result["summaries"]]
                for group in batches(missing, size=size):
                    for summary in experiment.call("summary", {"papers": group}, group):
                        result["summaries"][summary["id"]] = summary["summary"]
                    checkpoint()
        result.update(status="complete", finished_at=timestamp())
    except Exception as error:
        result.update(status="incomplete", error=type(error).__name__, finished_at=timestamp())
        raise
    finally:
        checkpoint()
    return path


def wilson(positive, total):
    if not total:
        return None
    p, z = positive / total, 1.96
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0, center - margin), min(1, center + margin)]


def metrics(cases, decisions, summaries=None):
    """Score delivered feed papers; missing decisions/summaries remain missed relevant papers."""
    tp = fp = fn = tn = missing = 0
    for case in cases:
        key = f"{case['interest']}/{case['paper']}"
        decision = decisions.get(key)
        truth = case["label"] != "unrelated"
        delivered = (decision is not None and decision["relevance"] != "unrelated"
                     and (summaries is None or case["paper"] in summaries))
        missing += decision is None or (summaries is not None and decision["relevance"] != "unrelated"
                                       and case["paper"] not in summaries)
        tp += truth and delivered
        fp += not truth and delivered
        fn += truth and not delivered
        tn += not truth and not delivered
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "missing": missing,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "precision_95pct_wilson": wilson(tp, tp + fp), "recall_95pct_wilson": wilson(tp, tp + fn)}


def report(data, output):
    report = {"dataset": check_dataset(data), "model": GEMINI_MODEL, "version": VERSION,
              "prompt_hash": PROMPT_HASH, "generated_at": timestamp(), "runs": [], "stages": {},
              "gate": "pending_live_measurements_and_human_review"}
    for path in sorted(Path(output).glob("run-*.json")):
        result = read(path)
        contract = result["contract"]
        cases = contract["cases"]
        if contract["prompt_hash"] != PROMPT_HASH or any(
                data["papers"].get(key) != paper for key, paper in contract["papers"].items()):
            raise ValueError("Report input or prompt version differs from frozen run")
        if any(data["interests"].get(key) != phrase for key, phrase in contract["interests"].items()):
            raise ValueError("Report interest phrases differ from frozen run")
        run_report = {"file": path.name, "split": contract["split"], "size": contract["size"],
                      "category": contract["category"], "status": result["status"], "cases": len(cases),
                      "decisions": len(result["decisions"]), "delivered_papers": len(result["summaries"]),
                      "quality": "pending_human_labels"}
        run_calls = [read(Path(output) / "calls" / f"{key}.json") for key in result.get("call_ids", [])]
        run_attempts = [attempt for record in run_calls for attempt in record["telemetry"]]
        run_report["sample_measurements"] = {
            "unique_call_artifacts": len(run_calls), "attempts": len(run_attempts),
            "seconds_including_pacing": sum(row["seconds"] for row in run_attempts),
            "actual_matching_batch_sizes": sorted({record["paper_count"] for record in run_calls
                                                   if record["contract"]["stage"] == "match"}),
            "invalid_or_failed": sum(record["status"] != "success" for record in run_calls),
            "cache_attribution": "Reused artifacts retain original measured cost; do not sum run costs as new spend",
        }
        if contract["split"] == "whole_day":
            reviews = data.get("daily_reviews", {})
        else:
            reviews = {f"{pair['interest']}/{pair['paper']}": pair for pair in data["pairs"]}
        if cases and all(reviews.get(f"{case['interest']}/{case['paper']}", {}).get("reviewer")
                         and reviews[f"{case['interest']}/{case['paper']}"].get("label") in LABELS for case in cases):
            labeled = [{**case, "label": reviews[f"{case['interest']}/{case['paper']}"]["label"]} for case in cases]
            if contract["split"] in ("heldout", "whole_day"):
                rubric_check(contract["rubric"])
            if contract["split"] == "heldout":
                check_dataset(data, reviewed=True)
            run_report["quality"] = metrics(labeled, result["decisions"], result["summaries"])
            run_report["matching_quality"] = metrics(labeled, result["decisions"])
        report["runs"].append(run_report)
    for stage in ("scope", "match", "summary"):
        records = [read(path) for path in Path(output).glob("calls/*.json")]
        records = [row for row in records if row["contract"]["stage"] == stage]
        attempts = [attempt for row in records for attempt in row["telemetry"]]
        known = [row for row in attempts if "input_tokens" in row]
        unknown = [row for row in attempts if row["status"] == "uncertain" and not row.get("reconciled")]
        report["stages"][stage] = {
            "calls": len(records), "attempts": len(attempts),
            "invalid_or_failed": sum(row["status"] != "success" for row in records),
            "input_tokens": sum(row["input_tokens"] for row in known),
            "output_tokens_including_thoughts": sum(row["output_tokens"] for row in known),
            "thinking_tokens": sum(row["thinking_tokens"] for row in known),
            "known_cost_usd": sum(row["input_tokens"] * GEMINI_INPUT_NANODOLLARS
                                  + row["output_tokens"] * GEMINI_OUTPUT_NANODOLLARS for row in known) / 1e9,
            "uncertain_reserved_usd": sum(row["input_bound"] * GEMINI_INPUT_NANODOLLARS
                                           + row["output_bound"] * GEMINI_OUTPUT_NANODOLLARS for row in unknown) / 1e9,
            "accounting_note": "Ledger is authoritative; reported usage may coexist with an uncertain reservation",
            "seconds": sum(row["seconds"] for row in attempts),
            "p95_attempt_seconds": sorted(row["seconds"] for row in attempts)[math.ceil(.95 * len(attempts)) - 1]
            if attempts else None,
        }
    report["analysis_hash"] = identity({key: value for key, value in report.items() if key != "generated_at"})
    write(Path(output) / "report.json", report)
    return report


def output_review_rows(output):
    rows = []
    for path in sorted(Path(output).glob("run-*.json")):
        result = read(path)
        for interest, scope in result["scopes"].items():
            rows.append({"run": path.name, "kind": "scope", "id": interest,
                         "source": result["contract"]["interests"][interest], "text": json.dumps(scope)})
        for key, decision in result["decisions"].items():
            if decision["relevance"] == "unrelated":
                continue
            paper = result["contract"]["papers"][decision["id"]]
            rows.append({"run": path.name, "kind": "explanation", "id": key,
                         "source": paper["abstract"], "text": json.dumps(decision)})
        for paper_id, summary in result["summaries"].items():
            rows.append({"run": path.name, "kind": "summary", "id": paper_id,
                         "source": result["contract"]["papers"][paper_id]["abstract"], "text": summary})
    return rows


def output_review_packet(output):
    """Export generated text for human factual/scope review, without self-grading."""
    rows = output_review_rows(output)
    path = Path(output) / "output-review.csv"
    if path.exists():
        raise ValueError("Refusing to overwrite human output review")
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["run", "kind", "id", "source", "text", "acceptable", "note"])
        writer.writeheader()
        writer.writerows(rows)
    return path


def gate(data, output, decision):
    """Audit an explicit owner decision against reviewed relevance and measured capacity."""
    check_dataset(data, reviewed=True)
    measured = report(data, output)
    forecast = read(Path(output) / "capacity.json")
    if (decision.get("report_hash") != measured["analysis_hash"]
            or decision.get("capacity_hash") != forecast["analysis_hash"]):
        raise ValueError("Owner decision must reference the exact reviewed report and capacity")
    if (not decision.get("reviewer") or not decision.get("reviewed_at") or not decision.get("reason")
            or decision.get("decision") not in ("pass", "fail")):
        raise ValueError("Explicit owner gate decision and dated reviewer identity required")
    size = decision.get("batch_size")
    if type(size) is not int or not 1 <= size <= 25 or forecast["batch_size"] != size:
        raise ValueError("Gate batch size must match measured capacity")
    heldout = [run for run in measured["runs"] if run["split"] == "heldout" and run["size"] == size]
    daily = [run for run in measured["runs"] if run["split"] == "whole_day" and run["size"] == size]
    if not heldout or {run["category"] for run in daily} != {source["category"] for source in data["sources"]}:
        raise ValueError("Held-out and all complete-day evaluations required")
    expected = {(row["run"], row["kind"], row["id"]): row for row in output_review_rows(output)}
    actual = {}
    with (Path(output) / "output-review.csv").open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            key = (row["run"], row["kind"], row["id"])
            if (key in actual or key not in expected
                    or any(row[field] != expected[key][field] for field in ("source", "text"))):
                raise ValueError("Generated-output human review coverage or text mismatch")
            actual[key] = row
    if set(expected) != set(actual) or any(row["acceptable"] not in ("yes", "no") for row in actual.values()):
        raise ValueError("Every generated scope/explanation/summary needs explicit human review")
    failures = []
    whole_day_totals = {kind: {key: 0 for key in ("tp", "fp", "fn", "tn", "missing")}
                        for kind in ("quality", "matching_quality")}
    whole_day_targets = set()
    for run_report in heldout + daily:
        if run_report["status"] != "complete" or not isinstance(run_report["quality"], dict):
            failures.append("Incomplete run or missing whole-day human labels")
            continue
        frozen = read(Path(output) / run_report["file"])["contract"]
        targets = frozen["rubric"]
        if run_report["split"] == "whole_day":
            whole_day_targets.add((targets["precision_target"], targets["recall_target"]))
            for kind, totals in whole_day_totals.items():
                for key in totals:
                    totals[key] += run_report[kind][key]
            continue
        for metric in ("precision", "recall"):
            target = targets.get(f"{metric}_target")
            if type(target) not in (float, int) or not 0 < target <= 1:
                raise ValueError("Approved numeric whole-feed targets required")
            # Both matcher and delivered-feed quality must pass; undefined precision fails.
            for quality in (run_report["quality"], run_report["matching_quality"]):
                if quality[metric] is None or quality[metric] < target:
                    failures.append(f"{run_report['file']}: {metric} below approved target")
    if len(whole_day_targets) != 1:
        failures.append("Complete-day runs need one approved quality rubric")
    else:
        precision_target, recall_target = next(iter(whole_day_targets))
        for totals in whole_day_totals.values():
            precision = totals["tp"] / (totals["tp"] + totals["fp"]) if totals["tp"] + totals["fp"] else None
            recall = totals["tp"] / (totals["tp"] + totals["fn"]) if totals["tp"] + totals["fn"] else None
            if precision is None or precision < precision_target or recall is None or recall < recall_target:
                failures.append("Aggregate whole-day quality below approved targets")
    if any(row["acceptable"] == "no" for row in actual.values()):
        failures.append("Human review rejected scope or found unsupported generated text")
    window = decision.get("delivery_window_seconds")
    buffer = decision.get("finalization_buffer_seconds")
    if not all(type(value) in (int, float) and math.isfinite(value) and value > 0 for value in (window, buffer)):
        raise ValueError("Owner-approved delivery window and finalization buffer required")
    if forecast["recommendation"] == "pending_live_measurements":
        failures.append("Capacity lacks real measurements or verified production quotas/overhead")
    for interests in (60, 100):
        candidates = [row for row in forecast["scenarios"] if row["interests"] == interests
                      and row["candidate_pool"] == decision.get("candidate_pool")]
        if len(candidates) != 1 or candidates[0]["projection"] is None:
            failures.append("Owner must select one measured eligible candidate pool")
            continue
        projected = candidates[0]["projection"]
        if not projected["within_15_usd_cold"] or not projected["daily_requests_within_80pct_rpd"]:
            failures.append(f"{interests}-interest scenario exceeds budget or provider quota")
        if projected["cold_seconds"] + buffer > window:
            failures.append(f"{interests}-interest scenario exceeds delivery window")
    if decision["decision"] == "pass" and failures:
        raise ValueError("Gate cannot pass: " + "; ".join(sorted(set(failures))))
    result = {"decision": decision, "passed": decision["decision"] == "pass" and not failures,
              "whole_day_counts": whole_day_totals, "failures": sorted(set(failures)), "checked_at": timestamp()}
    write(Path(output) / "gate.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "review-packet", "import-review", "run", "report", "capacity", "output-review", "gate"):
        child = sub.add_parser(command)
        child.add_argument("--dataset", type=Path, required=True)
        if command == "validate":
            child.add_argument("--snapshots", type=Path)
        if command != "validate":
            child.add_argument("--output", type=Path, required=True)
        if command == "import-review":
            child.add_argument("--csv", type=Path, nargs="+", required=True)
            child.add_argument("--reviewer", required=True)
        if command == "gate":
            child.add_argument("--decision", type=Path, required=True)
        if command == "run":
            child.add_argument("--live", action="store_true", required=True)
            child.add_argument("--split", choices=["calibration", "heldout", "whole_day"], required=True)
            child.add_argument("--size", type=int, choices=range(1, 26), default=25)
            child.add_argument("--rubric", type=Path)
            child.add_argument("--category")
        if command == "capacity":
            child.add_argument("--size", type=int, choices=range(1, 26), default=25)
            child.add_argument("--quota-evidence", type=Path)
            child.add_argument("--production-overhead-usd", type=float)
            child.add_argument("--production-overhead-seconds", type=float)
    args = parser.parse_args()
    data = read(args.dataset)
    counts = check_dataset(data)
    if args.command == "validate":
        if args.snapshots:
            verify_snapshots(data, args.snapshots)
            counts["raw_snapshots_verified"] = True
        print(json.dumps(counts, indent=2))
        return
    output = safe_output(args.output, args.dataset)
    if args.command == "review-packet":
        review_packet(data, output)
    elif args.command == "import-review":
        for path in args.csv:
            data = import_review(data, path, args.reviewer)
        destination = output / "reviewed-dataset.json"
        if destination.exists():
            raise ValueError("Refusing to overwrite reviewed dataset; choose a new output directory")
        write(destination, data)
    elif args.command == "report":
        print(json.dumps(report(data, output), indent=2))
    elif args.command == "output-review":
        print(output_review_packet(output))
    elif args.command == "gate":
        print(json.dumps(gate(data, output, read(args.decision)), indent=2))
    elif args.command == "capacity":
        limits = None
        evidence = None
        if args.quota_evidence:
            evidence = read(args.quota_evidence)
            if not all(evidence.get(key) for key in ("verified_by", "verified_at", "project")):
                raise ValueError("Verified provider project and quota evidence required")
            limits = evidence["limits"]
            if any(type(limits[key]) is not int or limits[key] < 1 for key in ("rpm", "tpm", "rpd")):
                raise ValueError("Invalid provider limits")
        for number in (args.production_overhead_usd, args.production_overhead_seconds):
            if number is not None and (not math.isfinite(number) or number < 0):
                raise ValueError("Production overhead must be measured, finite and nonnegative")
        records = [read(path) for path in output.glob("calls/*.json")]
        runs = [read(path) for path in output.glob("run-*.json")]
        result = capacity(data, records, runs=runs, limits=limits, production_usd=args.production_overhead_usd,
                          production_seconds=args.production_overhead_seconds, size=args.size)
        result["quota_evidence"] = evidence
        result["production_overhead_usd"] = args.production_overhead_usd
        result["production_overhead_seconds"] = args.production_overhead_seconds
        result["analysis_hash"] = identity(result)
        write(output / "capacity.json", result)
        print(json.dumps(result, indent=2))
    elif args.command == "run":
        # Never initialize, enable, copy or reset accounting from this runner.
        # Same production directory and OS lock; purpose="evaluation" gates every call.
        rubric = read(args.rubric) if args.rubric else None
        with ModelBudget(budget_directory()) as budget:
            budget.check_ready("evaluation")
            with create_client(get_secret("gemini_api_key")) as client:
                print(run(data, output, args.split, args.size, budget, client, rubric, args.category))


if __name__ == "__main__":
    main()
