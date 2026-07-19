#!/usr/bin/env bash
# Deploy script for ArXivSum / PaperPulse.
# Installed at /usr/local/sbin/deploy-paperpulse on the droplet, root-owned.
# Invoked via sudo (NOPASSWD restricted to this script for the `deploy` user).
#
# Two invocation paths:
#   1. CI over SSH. The `deploy` user's authorized_keys forces a single
#      command="sudo --preserve-env=SSH_ORIGINAL_COMMAND /usr/local/sbin/deploy-paperpulse".
#      The git SHA arrives in $SSH_ORIGINAL_COMMAND.
#   2. Manual on droplet: sudo /usr/local/sbin/deploy-paperpulse <git_sha> [--run-pipeline]
#
# Input is validated strictly (40-char hex SHA). Defense in depth on top of the
# sudoers + authorized_keys restrictions.

set -euo pipefail

# Read tag from $1 (manual) or $SSH_ORIGINAL_COMMAND (SSH-forced-command).
IMAGE_TAG="${1:-${SSH_ORIGINAL_COMMAND:-}}"
RUN_PIPELINE="${2:-}"

if [ -z "$IMAGE_TAG" ]; then
    echo "Usage: deploy-paperpulse <git_sha> [--run-pipeline]" >&2
    exit 1
fi

# Strict input validation. Reject anything that isn't a 40-char hex git SHA.
if ! [[ "$IMAGE_TAG" =~ ^[a-f0-9]{40}$ ]]; then
    echo "Refusing to deploy: image tag must be a 40-char git SHA, got: $IMAGE_TAG" >&2
    exit 1
fi

REPO_DIR="/var/www/arxivsum"
COMPOSE_FILE="${REPO_DIR}/docker-compose.prod.yml"

cd "$REPO_DIR"

# Refresh blog content + compose file from main.
# Images carry the code; this only refreshes host-mounted assets and the
# compose file itself (so layouts, _config.yml, nginx.conf etc. stay in sync
# with whatever the new images expect).
git fetch origin main
git reset --hard origin/main

export IMAGE_TAG

# Pull new images from GHCR.
docker compose -f "$COMPOSE_FILE" pull

# Keep the local :latest tag pointing at the image just deployed. The systemd
# timer runs `docker compose run` without IMAGE_TAG, so it resolves to local
# :latest — without this it keeps running whatever :latest was last pulled.
docker tag "ghcr.io/unmeshk/paperpulse-api:${IMAGE_TAG}" ghcr.io/unmeshk/paperpulse-api:latest

# Recreate containers with the new images. --remove-orphans cleans up any
# services that have been removed from the compose file.
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

# Optionally run the daily pipeline once (CI sets this when api/ changed).
if [ "$RUN_PIPELINE" = "--run-pipeline" ]; then
    docker compose -f "$COMPOSE_FILE" run --rm api python -m api.main
fi

# Clean up dangling image layers from previous deploys.
docker image prune -f

# Prune old SHA-tagged paperpulse images, keeping the two newest per repo
# (the set just deployed + one rollback target). Each deploy leaves a
# ~1.4GB image set; unpruned, the disk fills after a handful of deploys
# (it broke a deploy on 2026-07-18). GHCR retains every tag, so anything
# removed here can be re-pulled for a deeper rollback.
for repo in paperpulse-api paperpulse-blog paperpulse-app; do
    docker image ls --format '{{.Tag}}\t{{.CreatedAt}}' "ghcr.io/unmeshk/${repo}" \
        | grep -E '^[a-f0-9]{40}' \
        | sort -t$'\t' -k2 -r \
        | tail -n +3 \
        | cut -f1 \
        | sed "s|^|ghcr.io/unmeshk/${repo}:|" \
        | xargs -r docker rmi || true
done
