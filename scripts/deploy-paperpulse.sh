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

# Recreate containers with the new images. --remove-orphans cleans up any
# services that have been removed from the compose file.
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

# Optionally run the daily pipeline once (CI sets this when api/ changed).
if [ "$RUN_PIPELINE" = "--run-pipeline" ]; then
    docker compose -f "$COMPOSE_FILE" run --rm api python -m api.main
fi

# Clean up dangling image layers from previous deploys.
docker image prune -f
