# CI/CD Implementation Plan

## Goal
Replace manual SSH-and-pull deploys with a push-to-main → auto-deploy pipeline. Remove `.env` files from the droplet. Reduce blast radius if GitHub Actions or the droplet is compromised.

## Target architecture

```
GitHub Actions
   |
   | build + test + push Docker images
   v
GHCR (GitHub Container Registry)
   |
   | SSH as deploy user, restricted to one deploy command
   v
Droplet (/var/www/arxivsum)
   |
   | docker compose pull
   | docker compose up -d
   v
nginx -> Jekyll container
      -> API container (with scheduled daily job inside)
```

## Secrets model
- App runtime secrets live in `/var/lib/paperpulse/secrets/` on droplet, root-owned, `chmod 600`
- Referenced via Docker Compose secrets, mounted at `/run/secrets/<name>` inside containers
- App reads from `/run/secrets/<name>` first, falls back to `os.getenv()` for local dev / forks
- GitHub Actions only holds infrastructure secrets: `DEPLOY_SSH_PRIVATE_KEY`, `DROPLET_HOST`

## Implementation steps

### 1. Containerize the API
- Finish `api/Dockerfile` (current one is half-baked, references Flask but `main.py` is a pipeline script)
- Add `api` service to `docker-compose.prod.yml`
- Code change: read secrets from `/run/secrets/<name>` first, fall back to `os.getenv()`
- Keep `load_dotenv()` for local dev compatibility

### 2. CI builds and pushes images
- GitHub Actions workflow on push to `main`:
  - Run tests
  - Build `paperpulse-api` and `paperpulse-blog` images
  - Tag with git SHA
  - Push to GHCR

### 3. Server-side secret files
- One-time setup: `scp` secret files to `/var/lib/paperpulse/secrets/`
- Reference in `docker-compose.prod.yml` as Docker Compose secrets
- Update `.dockerignore` to ensure no secret/log files leak into images:
  - `blog/_site/`
  - `blog/.jekyll-cache/`
  - `*.log`
  - `*.pkl`

### 4. Deploy script on droplet
- `/usr/local/sbin/deploy-paperpulse <image_tag>`
- Pulls images, runs `docker compose up -d --remove-orphans`
- Prunes old images
- Optionally triggers one-shot run of API pipeline if `api/` changed (smart deploy)

### 5. Deploy user
- Create `deploy` user on droplet
- SSH `authorized_keys` restricted via `command="..."` to the deploy script only
- Sudoers grants NOPASSWD only for `/usr/local/sbin/deploy-paperpulse`
- Add SSH public key to droplet, private key to GitHub Actions secrets

### 6. Replace cron with systemd timer invoking one-shot container
- systemd unit `paperpulse-daily.service` runs `docker compose -f /var/www/arxivsum/docker-compose.prod.yml run --rm api python -m api.main`
- systemd timer `paperpulse-daily.timer` schedules it daily
- `Persistent=true` catches up missed runs after downtime
- Logs via `journalctl -u paperpulse-daily`
- Secrets come via Docker Compose secrets at container start — host has zero secrets
- Remove crontab entry on droplet

### 7. Cleanup
- Remove `.env` files from droplet
- Rotate Gemini API key and Mixpanel token (assume any past `.env` value is compromised)
- Set Gemini spend cap as defense-in-depth
- `git rm --cached api/.env blog/.env` if tracked; verify `.gitignore` covers `.env` files

## Out of scope (for now)
- External secrets manager (Vault, Doppler) — overkill at single-droplet scale
- Multi-droplet / staging environments

## Open questions to resolve during implementation
- For step 2: public or private GHCR images? (repo is public, so either works)
