#!/usr/bin/env bash
# Deploy script for ArXivSum / PaperPulse.
# Installed at /usr/local/sbin/deploy-paperpulse on the droplet.
# Invoked by CI over SSH as the `deploy` user via sudo (NOPASSWD restricted to this script).
#
# Usage: deploy-paperpulse <image_tag> [--run-pipeline]
#   image_tag       Full git SHA tag pushed to GHCR (e.g. abc123def...)
#   --run-pipeline  Optional: after pulling images, run main.py once
#                   (used when the CI workflow detects changes under api/)

set -euo pipefail

IMAGE_TAG="${1:?image tag required (full git SHA)}"
RUN_PIPELINE="${2:-}"

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
