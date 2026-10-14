"""Measured capacity projections; unavailable measurements stay unavailable."""
import math

from api.settings import GEMINI_INPUT_NANODOLLARS, GEMINI_OUTPUT_NANODOLLARS

from api.semantic import batches, identity


def capacity(data, records, *, runs=(), limits=None, production_usd=None, production_seconds=None, size=25):
    """Project real source pools at 60/100 interests, including delivery reserves.

    Assumes cold caches and distinct per-interest eligible pools. Reports an
    all-accepted upper bound separately from the observed whole-day acceptance rate.
    Scope creation is a separate cold-start surcharge, zero for ready scopes.
    """
    runs = [run for run in runs if run["contract"]["size"] == size]
    effective = {key: value * 4 // 5 for key, value in limits.items()} if limits else None
    pools = [(source["category"], source["paper_ids"]) for source in data["sources"]]
    pools.append(("union_of_three_categories", sorted({paper for _, ids in pools for paper in ids})))
    whole_day_ids = {key for run in runs if run["contract"]["split"] == "whole_day"
                     for key in run.get("call_ids", [])}
    samples = {}
    for stage in ("scope", "match", "summary"):
        calls = [record for record in records if record["contract"]["stage"] == stage
                 and (stage == "scope" or not whole_day_ids or identity(record["contract"]) in whole_day_ids)]
        valid = [record for record in calls if record["status"] == "success"]
        papers = sum(record.get("paper_count", 0) for record in valid)
        count = len(valid) if stage == "scope" else papers
        attempts = [attempt for record in calls for attempt in record["telemetry"]]
        known = [attempt for attempt in attempts if "input_tokens" in attempt]
        if not count or len(known) != len(attempts) or len(valid) != len(calls):
            samples[stage] = None
            continue
        samples[stage] = {
            "usd_per_item": sum(row["input_tokens"] * GEMINI_INPUT_NANODOLLARS
                                + row["output_tokens"] * GEMINI_OUTPUT_NANODOLLARS for row in known) / 1e9 / count,
            "seconds_per_item": sum(row["seconds"] for row in attempts) / count,
            "p95_seconds_per_item": sorted(
                sum(row["seconds"] for row in record["telemetry"]) / (1 if stage == "scope" else record["paper_count"])
                for record in valid)[math.ceil(.95 * len(valid)) - 1],
            # Count endpoint plus generate endpoint; retry counts conservatively add both.
            "requests_per_item": 2 * len(attempts) / count,
            "reserved_tokens_per_item": sum(row["input_bound"] + row["output_bound"] for row in attempts) / count,
            "measured_items": count,
            "batch_sizes": sorted({record.get("paper_count", 0) for record in valid}),
            "max_call_reservation_usd": max(row["input_bound"] * GEMINI_INPUT_NANODOLLARS
                                            + row["output_bound"] * GEMINI_OUTPUT_NANODOLLARS
                                            for row in attempts) / 1e9,
        }
    natural_rates = [sum(row["relevance"] != "unrelated" for row in run["decisions"].values()) / len(run["decisions"])
                     for run in runs if run["contract"]["split"] == "whole_day" and run["status"] == "complete"
                     and run["decisions"]]
    measured_categories = {run["contract"]["category"] for run in runs
                           if run["contract"]["split"] == "whole_day" and run["status"] == "complete"}
    result = {"assumptions": ["cold matching/summary caches", "all accepted pairs require distinct summaries",
                               "whole candidate pool eligible per interest", "pacing uses reserved token bounds",
                               "scope cold-start surcharge reported separately", "no unmeasured retry discount"],
              "samples": samples, "batch_size": size, "whole_day_acceptance_rates": natural_rates,
              "effective_quota_limits": effective,
              "scenarios": [], "recommendation": "pending_live_measurements"}
    ready = (all(samples.values()) and limits is not None and production_usd is not None
             and production_seconds is not None
             and measured_categories == {source["category"] for source in data["sources"]}
             and all(run["contract"]["quota_limits"] == effective for run in runs))
    for category, ids in pools:
        papers = [data["papers"][paper] for paper in ids]
        batch_counts = {str(size): len(list(batches(papers, size=size))) for size in (5, 15, 25)}
        for interests in (60, 100):
            scenario = {"candidate_pool": category, "papers_per_interest": len(papers), "interests": interests,
                        "matching_batches": {size: count * interests for size, count in batch_counts.items()},
                        "projection": None}
            if ready:
                # Extrapolate observed natural prevalence; also retain the all-accepted upper bound.
                items = len(papers) * interests
                matching, summary, scope = (samples[key] for key in ("match", "summary", "scope"))
                summaries = math.ceil(items * max(natural_rates))
                usd = production_usd + items * matching["usd_per_item"] + summaries * summary["usd_per_item"]
                upper_usd = production_usd + items * (matching["usd_per_item"] + summary["usd_per_item"])
                scope_usd = interests * scope["usd_per_item"]
                requests = items * matching["requests_per_item"] + summaries * summary["requests_per_item"]
                tokens = items * matching["reserved_tokens_per_item"] + summaries * summary["reserved_tokens_per_item"]
                seconds = max(items * matching["p95_seconds_per_item"] + summaries * summary["p95_seconds_per_item"],
                              requests / effective["rpm"] * 60, tokens / effective["tpm"] * 60)
                startup_seconds = max(interests * scope["p95_seconds_per_item"],
                                      interests * scope["requests_per_item"] / effective["rpm"] * 60,
                                      interests * scope["reserved_tokens_per_item"] / effective["tpm"] * 60)
                scenario["projection"] = {
                    "steady_usd_at_max_observed_acceptance": usd, "all_accepted_steady_usd_upper_bound": upper_usd,
                    "projected_summary_count": summaries, "cold_scope_usd": scope_usd,
                    "within_15_usd_cold": usd + scope_usd <= 15,
                    "steady_seconds": seconds + production_seconds,
                    "cold_seconds": seconds + startup_seconds + production_seconds,
                    "summary_reserve_for_one_measured_batch_usd": summary["max_call_reservation_usd"],
                    "daily_requests_within_80pct_rpd": requests + interests * scope["requests_per_item"]
                    <= effective["rpd"],
                    "finalization_buffer_seconds": None,
                }
            result["scenarios"].append(scenario)
    if ready:
        result["recommendation"] = "owner_review_required_for_acceptance_rate_summary_reuse_and_delivery_window"
    return result
