# `/goal` autonomy boundary

Rules for what Claude may do without per-turn confirmation when running under
`/goal`. Overrides nothing in `CLAUDE.md`; this just narrows the gate for
goal-mode runs.

When auto mode is on AND `/goal` is active, the items under **In-scope** run
without prompting. Everything under **Hard-gated** still requires explicit
confirmation in the current message, even mid-goal.

If a goal condition appears to require a hard-gated action, Claude must stop
the goal, surface the gap, and wait for instruction.

---

## In-scope (no per-action confirmation)

Filesystem (under `app/` and `docs/` only):
- Create, edit, delete files under `app/**` and `app/tests/**`
- Create, edit `docs/**`
- Read any file in the repo

Local commands:
- `pytest`, `python -m ...` against local code
- `pip install` into `app/.venv/` (for adding test deps already in `requirements.txt`)
- Read-only git: `git status`, `git diff`, `git log`, `git show`
- `sqlite3` against the local dev DB (`app/paperpulse.sqlite`) or test tmpdir DBs

Network:
- Local only: `curl http://localhost:*`, `curl http://127.0.0.1:*`

---

## Hard-gated (requires explicit confirmation in current message)

Even during an active `/goal` run, Claude must stop and ask before:

Git state changes:
- `git commit`, `git push`, `git pull`, `git rebase`, `git merge`
- Branch creation, deletion, checkout to a different branch
- Any `git reset`, `git restore`, `git clean`
- Tag creation or modification

Files outside `app/` and `docs/`:
- Anything under `api/`, `blog/`, `nginx/`, `systemd/`, `scripts/`
- `.github/**` (CI/CD)
- `docker-compose*.yml`, `Dockerfile*`
- `.gitignore`, `CLAUDE.md`, `setup.py`, `requirements.txt` at repo root
- This file (`docs/GOAL_AUTONOMY.md`) — boundary changes require human approval

External services:
- Any `curl`/`wget`/`httpx` to a non-localhost URL
- Any call to Gemini, Google APIs, GitHub API, DigitalOcean, OAuth providers
- Any `ssh`, `scp`, `rsync` to a remote
- Any `docker`, `docker compose` command
- Any deploy script under `scripts/`

Destructive ops:
- `rm -rf` of anything beyond the test tmpdir
- Dropping DB tables, truncating prod-shaped data
- Killing processes that aren't ones Claude started in this session
- `--no-verify`, `--force`, `--no-gpg-sign` flags on any command

PII / secrets:
- Reading or echoing `app/.env`, `api/.env`, `/var/lib/paperpulse/secrets/**`
- Writing real secrets into any file
- Logging email addresses or display names

---

## How to invoke a goal under this boundary

1. Make sure auto mode is on (`/auto`).
2. Set the goal with a condition expressed as a pytest assertion or curl-checkable HTTP response — see `docs/PHASE1_CHUNKS.md` for examples.
3. Claude works within the in-scope set; pauses when a hard-gated step is needed.

Example:
```
/goal pytest app/tests passes including new tests covering all acceptance criteria in docs/PHASE1_CHUNKS.md chunk 1
```
