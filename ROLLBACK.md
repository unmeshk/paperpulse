# Rollback procedures

How to revert a bad deploy of the ArXivSum / PaperPulse stack on the droplet.

## Standard rollback (after at least one successful deploy)

Every successful CI run on `main` pushes images to GHCR tagged with that commit's full SHA. Those tags are immutable — they never get overwritten. Rolling back means redeploying with an older SHA.

```bash
# 1. Find the SHA you want to roll back to. Either:
#    (a) Look at git log on the droplet
cd /var/www/arxivsum && git log --oneline -10

#    (b) Look at the GitHub Actions history — every successful run shows its SHA
#        https://github.com/unmeshk/paperpulse/actions

# 2. Verify both images exist for that SHA before deploying
docker pull ghcr.io/unmeshk/paperpulse-api:<old_sha>
docker pull ghcr.io/unmeshk/paperpulse-blog:<old_sha>

# 3. Roll back — re-run the deploy script with the older tag
/usr/local/sbin/deploy-paperpulse <old_sha>
```

The script will `git reset --hard` to the old SHA (so the compose file + blog content match the images), pull the old images, and restart containers.

Time to roll back: ~30 seconds.

## Knowing what's currently deployed

```bash
# Image tag currently running
docker inspect $(docker compose -f /var/www/arxivsum/docker-compose.prod.yml ps -q api) \
  --format '{{.Config.Image}}'

# Or check git on the droplet (the deploy script pins HEAD via git reset --hard)
cd /var/www/arxivsum && git rev-parse HEAD
```

## First-deploy rollback (special case)

After the initial PR merges from `feat/ci-cd-pipeline`, there is no previous "image-based" version to roll back to. The pre-CI world ran the API via venv + cron, built the blog image locally, and had no `image:` references in the compose file.

### Option 1 — forward fix (preferred)

1. Revert the breaking commit on `main` via the GitHub UI ("Revert" button on the merge commit), then merge that revert PR.
2. CI builds new images for the revert commit.
3. Re-run the deploy script on the droplet with the new SHA.

Total time: ~5 minutes (mostly waiting for CI). Cleanest.

### Option 2 — manual restore to pre-CI state

Only use if a forward fix isn't viable.

```bash
cd /var/www/arxivsum

# Stop the new containers
docker compose -f docker-compose.prod.yml down

# Reset to the merge commit's parent (pre-CI compose file)
git reset --hard <pre-pr-merge-sha>

# Restore old .env files if you'd deleted them
# (Have them somewhere safe in advance — they're gone from the droplet otherwise.)

# Rebuild old way (this rebuilds locally, not from images)
docker compose -f docker-compose.prod.yml up -d --build

# Verify
docker compose -f docker-compose.prod.yml ps
```

## Dry-run test rollback (pre-merge)

If you used the dry-run procedure to test the new compose file + script before merging to main, and something went wrong:

```bash
cd /var/www/arxivsum

# Restore the original compose file from the backup made during dry-run
mv docker-compose.prod.yml.bak docker-compose.prod.yml

# Tear down everything and rebuild with old setup
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build

# Verify
docker compose -f docker-compose.prod.yml ps
```

The droplet still has the original code on disk (no `git reset --hard` runs during dry-run), so `--build` will rebuild from local source the same way it did before. Should fully restore the pre-test state.

## Mitigations to reduce first-deploy risk

Before merging the CI/CD PR to `main`:

1. Pull the soon-to-be-`latest` images locally and run them with `docker-compose.prod.yml` (using a stub secrets dir).
2. Run the dry-run procedure on the droplet using one of the feature-branch SHA-tagged images (if they're still in GHCR).
3. Confirm `/var/lib/paperpulse/secrets/gemini_api_key` exists and is readable by root.
4. Plan the merge for a time when you can immediately respond if something breaks.
