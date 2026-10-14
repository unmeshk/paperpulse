"""Single-host Gemini ledger and pipeline lock, independent of app SQLite.

Money is integer nanodollars. Never initialize automatically: a missing ledger
could be lost accounting, not a new installation. See the milestone 0 runbook
in docs/SEMANTIC_INTEREST_FEED_IMPLEMENTATION_PLAN.md before initialization.
"""
import argparse
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import fcntl
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import time
import uuid
from zoneinfo import ZoneInfo

from api.settings import (
    GEMINI_DAILY_NANODOLLARS,
    GEMINI_INPUT_NANODOLLARS,
    GEMINI_MODEL,
    GEMINI_OUTPUT_NANODOLLARS,
    budget_directory,
)

NY = ZoneInfo("America/New_York")
PACIFIC = ZoneInfo("America/Los_Angeles")
PRICING = [GEMINI_MODEL, GEMINI_INPUT_NANODOLLARS, GEMINI_OUTPUT_NANODOLLARS]


class BudgetError(RuntimeError):
    """Accounting is unavailable; stop model work."""


class BudgetExceeded(BudgetError):
    """The next call would exceed the daily allowance or completion reserve."""


class PipelineBusy(BudgetError):
    """Another process owns the pipeline lock."""


class DailyQuotaExceeded(BudgetError):
    """Provider daily quota is exhausted (Pacific day)."""


class RateLimited(BudgetError):
    """Quota pacing or provider cooldown exceeds this call's wait allowance."""


def _integer(value):
    return type(value) is int and value >= 0


def _day(timestamp, zone=NY):
    return datetime.fromtimestamp(timestamp, zone).date().isoformat()


def _empty_day(spent=0):
    return {"spent": spent, "pending": {}, "calls": 0, "input_tokens": 0, "output_tokens": 0}


@contextmanager
def pipeline_lock(directory):
    """Hold one nonblocking OS lock across retrieval, calls and publication.

    Args:
        directory: Shared durable directory, identical for pipeline/evaluation.
    Returns:
        Yields the locked file; closing it releases the lock even after a crash.
    """
    try:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        handle = (directory / "pipeline.lock").open("a+")
    except OSError as err:
        raise BudgetError("Cannot open pipeline lock") from err
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as err:
            raise PipelineBusy("Another pipeline or evaluation is running") from err
        except OSError as err:
            raise BudgetError("Cannot acquire pipeline lock") from err
        yield handle
    finally:
        handle.close()


class ModelBudget:
    """Ledger usable only inside its exclusive context.

    ponytail: one host, one sequential worker; use shared coordination if hosting
    ever spans machines. No separate DB, queue, or background accounting service.
    """

    def __init__(self, directory, *, clock=time.time, sleep=time.sleep):
        self.directory = Path(directory)
        self.path = self.directory / "ledger.json"
        self.clock = clock
        self.sleep = sleep
        self._lock = None
        self._poisoned = False

    def __enter__(self):
        if self._lock is not None:
            raise BudgetError("Accounting context cannot be nested")
        self._context = pipeline_lock(self.directory)
        self._lock = self._context.__enter__()
        self._owner = (os.getpid(), threading.get_ident())
        try:
            self.state = self._read()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *args):
        self._context.__exit__(*args)
        self._lock = None

    def _read(self):
        try:
            if self.path.is_symlink():
                raise ValueError("Ledger must share the lock's persistent directory")
            state = json.loads(self.path.read_text(encoding="utf-8"))
            self._validate(state)
            return state
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as err:
            raise BudgetError("Missing, corrupt, or incompatible Gemini ledger; paid calls disabled") from err

    @staticmethod
    def _validate(state):
        if type(state["version"]) is not int or state["version"] != 1 or state["pricing"] != PRICING:
            raise ValueError("Unsupported ledger/pricing version")
        if date.fromisoformat(state["start_day"]).isoformat() != state["start_day"]:
            raise ValueError("Invalid start date")
        for key in ("evaluation_enabled", "halted"):
            if type(state[key]) is not bool:
                raise ValueError("Invalid accounting flag")
        for key in ("last_seen", "cooldown_until"):
            if not isinstance(state[key], (int, float)) or not math.isfinite(state[key]) or state[key] < 0:
                raise ValueError("Invalid timestamp")
        if state["blocked_quota_day"] is not None:
            date.fromisoformat(state["blocked_quota_day"])
        for key in ("rpm", "tpm", "rpd"):
            if not _integer(state["limits"][key]) or state["limits"][key] < 1:
                raise ValueError("Invalid quota limits")
        if not state["days"] or state["start_day"] not in state["days"]:
            raise ValueError("Missing opening balance")
        for day, record in state["days"].items():
            if date.fromisoformat(day).isoformat() != day or day < state["start_day"]:
                raise ValueError("Invalid budget day")
            for key in ("spent", "calls", "input_tokens", "output_tokens"):
                if not _integer(record[key]):
                    raise ValueError("Invalid accounting total")
            for reservation in record["pending"].values():
                for key in ("amount", "input_tokens", "max_output_tokens"):
                    if not _integer(reservation[key]):
                        raise ValueError("Invalid reservation")
                if reservation["amount"] != (
                    reservation["input_tokens"] * GEMINI_INPUT_NANODOLLARS
                    + reservation["max_output_tokens"] * GEMINI_OUTPUT_NANODOLLARS
                ):
                    raise ValueError("Reservation amount mismatch")
        for day, count in state["quota_days"].items():
            date.fromisoformat(day)
            if not _integer(count):
                raise ValueError("Invalid quota count")
        for timestamp, tokens in state["recent"]:
            if not math.isfinite(timestamp) or timestamp < 0 or not _integer(tokens):
                raise ValueError("Invalid minute usage")

    def _check(self, purpose):
        if self._lock is None or self._lock.closed or self._poisoned:
            raise BudgetError("An intact ledger and exclusive accounting context are required")
        if self._owner != (os.getpid(), threading.get_ident()):
            raise BudgetError("Accounting context cannot be shared across processes or threads")
        if purpose not in ("production", "evaluation"):
            raise ValueError("Unknown model-call purpose")
        now = self.clock()
        if not math.isfinite(now) or now < self.state["last_seen"]:
            raise BudgetError("Clock moved backwards; paid calls disabled")
        if _day(now) < self.state["start_day"] or self.state["halted"]:
            raise BudgetError("Accounting has not started or requires operator review")
        if purpose == "evaluation" and not self.state["evaluation_enabled"]:
            raise BudgetError("Paid evaluation requires verified production accounting activation")
        return now

    def check_ready(self, purpose="production"):
        """Check activation and ownership without dispatching a request."""
        self._check(purpose)

    def _save(self):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory, delete=False) as file:
                temporary = file.name
                json.dump(self.state, file, allow_nan=False, sort_keys=True)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
            temporary = None
            descriptor = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except (OSError, ValueError, TypeError) as err:
            self._poisoned = True
            raise BudgetError("Cannot durably save accounting; paid calls disabled") from err
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    def _pace(self, input_tokens, purpose, wait_deadline):
        while True:
            now = self._check(purpose)
            quota_day = _day(now, PACIFIC)
            if (self.state["blocked_quota_day"] == quota_day
                    or self.state["quota_days"].get(quota_day, 0) >= self.state["limits"]["rpd"]):
                raise DailyQuotaExceeded("Gemini daily quota exhausted; no retry before Pacific reset")
            if input_tokens > self.state["limits"]["tpm"]:
                raise RateLimited("Request exceeds configured token-per-minute allowance")
            recent = [entry for entry in self.state["recent"] if entry[0] > now - 60]
            self.state["recent"] = recent
            delay = max(0, self.state["cooldown_until"] - now)
            if (len(recent) >= self.state["limits"]["rpm"]
                    or sum(entry[1] for entry in recent) + input_tokens > self.state["limits"]["tpm"]):
                delay = max(delay, min(entry[0] for entry in recent) + 60 - now)
            if delay <= 0:
                return now, quota_day
            if now + delay > wait_deadline:
                raise RateLimited("Gemini pacing exceeds this call's bounded wait")
            self.sleep(min(delay, 60))

    def reserve(self, input_tokens, max_output_tokens, *, purpose="production", keep_nanodollars=0, wait_seconds=120):
        """Persist a separate maximum charge for each attempt before dispatch.

        Args:
            input_tokens: Counted input including system instructions and margin.
            max_output_tokens: Hard generation cap, including thoughts.
            purpose: Production or gated evaluation, sharing the same allowance.
            keep_nanodollars: Capacity to leave for later summaries (calibrated in milestone 1).
            wait_seconds: Maximum quota/cooldown wait for this attempt.
        Returns:
            Tuple of dispatch-day and reservation ID for later reconciliation.
        """
        if not all(_integer(v) for v in (input_tokens, max_output_tokens, keep_nanodollars)):
            raise ValueError("Token and reserve amounts must be nonnegative integers")
        if (not isinstance(wait_seconds, (int, float)) or not math.isfinite(wait_seconds)
                or not 0 <= wait_seconds <= 120):
            raise ValueError("Quota wait must be between 0 and 120 seconds")
        amount = input_tokens * GEMINI_INPUT_NANODOLLARS + max_output_tokens * GEMINI_OUTPUT_NANODOLLARS
        now = self._check(purpose)
        day = self.state["days"].get(_day(now), _empty_day())
        committed = day["spent"] + sum(r["amount"] for r in day["pending"].values())
        if committed + amount + keep_nanodollars > GEMINI_DAILY_NANODOLLARS:
            raise BudgetExceeded("Gemini daily budget or completion reserve exhausted")
        now, quota_day = self._pace(input_tokens, purpose, now + wait_seconds)
        day_key = _day(now)
        day = self.state["days"].setdefault(day_key, _empty_day())
        # Pacing may have crossed New York midnight; recheck the dispatch day.
        committed = day["spent"] + sum(r["amount"] for r in day["pending"].values())
        if committed + amount + keep_nanodollars > GEMINI_DAILY_NANODOLLARS:
            raise BudgetExceeded("Gemini daily budget or completion reserve exhausted")
        key = uuid.uuid4().hex
        day["pending"][key] = {"amount": amount, "input_tokens": input_tokens, "max_output_tokens": max_output_tokens}
        day["calls"] += 1
        self.state["recent"].append([now, input_tokens])
        self.state["quota_days"][quota_day] = self.state["quota_days"].get(quota_day, 0) + 1
        self.state["last_seen"] = now
        self._save()
        return day_key, key

    def count_request(self, purpose="production"):
        """Account for the unbilled tokenizer request in request pacing too."""
        reservation = self.reserve(0, 0, purpose=purpose)
        self.reconcile(reservation, 0, 0)

    def reconcile(self, reservation, input_tokens, output_tokens):
        """Release unused reservation only when complete usage is known."""
        if not _integer(input_tokens) or not _integer(output_tokens):
            raise BudgetError("Invalid usage; maximum reservation retained")
        self._check("production")
        day_key, key = reservation
        day = self.state["days"][day_key]
        pending = day["pending"][key]
        actual = input_tokens * GEMINI_INPUT_NANODOLLARS + output_tokens * GEMINI_OUTPUT_NANODOLLARS
        exceeded = input_tokens > pending["input_tokens"] or output_tokens > pending["max_output_tokens"]
        day["spent"] += actual
        day["input_tokens"] += input_tokens
        day["output_tokens"] += output_tokens
        del day["pending"][key]
        if exceeded:
            self.state["halted"] = True
        self._save()
        if exceeded:
            raise BudgetError("Provider usage exceeded reservation bounds; accounting halted for review")

    def provider_delay(self, seconds, *, daily=False):
        """Persist provider feedback so restarting cannot bypass it."""
        now = self._check("production")
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Invalid provider delay")
        self.state["cooldown_until"] = max(self.state["cooldown_until"], now + seconds)
        if daily:
            self.state["blocked_quota_day"] = _day(now, PACIFIC)
        self.state["last_seen"] = now
        self._save()


def initialize(directory, start_day, opening_nanodollars, *, rpm, tpm, rpd):
    """Create accounting once under lock after operators stop untracked workers.

    Args:
        directory: Persistent accounting directory.
        start_day: Today with verified opening spend, or a future New York day.
        opening_nanodollars: Explicit conservative opening balance.
        rpm, tpm, rpd: Verified project limits; use 80 percent for headroom.
    Returns:
        None. Existing ledgers are never replaced.
    """
    start = date.fromisoformat(start_day)
    today = date.fromisoformat(_day(time.time()))
    if start.isoformat() != start_day or start < today or not _integer(opening_nanodollars):
        raise ValueError("Use today with verified spend, or a future start date")
    if start > today and opening_nanodollars != 0:
        raise ValueError("Future accounting starts with zero spend")
    if not all(_integer(v) and v >= 2 for v in (rpm, tpm, rpd)):
        raise ValueError("Supply verified positive project quotas (at least 2)")
    with pipeline_lock(directory):
        budget = ModelBudget(directory)
        if budget.path.exists() or budget.path.is_symlink():
            raise BudgetError("Ledger already exists; refusing to reset spend")
        budget.state = {
            "version": 1, "pricing": PRICING, "start_day": start_day,
            "evaluation_enabled": False, "halted": False, "last_seen": time.time(),
            "limits": {"rpm": rpm * 4 // 5, "tpm": tpm * 4 // 5, "rpd": rpd * 4 // 5},
            "days": {start_day: _empty_day(opening_nanodollars)}, "quota_days": {},
            "recent": [], "cooldown_until": 0, "blocked_quota_day": None,
        }
        budget._save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("initialize")
    init.add_argument("--start-day", required=True)
    init.add_argument("--opening-spend-usd", required=True)
    for name in ("rpm", "tpm", "rpd"):
        init.add_argument(f"--{name}", required=True, type=int)
    init.add_argument("--untracked-workers-stopped", required=True, action="store_true")
    enable = sub.add_parser("enable-evaluation")
    enable.add_argument("--production-controls-verified", required=True, action="store_true")
    sub.add_parser("status")
    args = parser.parse_args()
    try:
        directory = budget_directory()
        if args.command == "initialize":
            amount = Decimal(args.opening_spend_usd) * 1_000_000_000
            if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value():
                raise ValueError("Invalid opening spend")
            initialize(directory, args.start_day, int(amount), rpm=args.rpm, tpm=args.tpm, rpd=args.rpd)
        else:
            with ModelBudget(directory) as budget:
                if args.command == "enable-evaluation":
                    budget.check_ready()
                    budget.state["evaluation_enabled"] = True
                    budget._save()
                print(json.dumps(budget.state, indent=2, sort_keys=True))
    except (BudgetError, ValueError, InvalidOperation) as err:
        parser.exit(1, f"{err}\n")


if __name__ == "__main__":
    main()
