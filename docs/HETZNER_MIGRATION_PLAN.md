# DigitalOcean to Hetzner migration

Status: closed. Owner confirmed the Hetzner move complete on 2026-10-05 and
requested resuming product work. Production is hosted in Helsinki. The proposal
below is historical; see WORKLOG.md for execution and close-out. This document
is no longer an active plan.

## Frozen initial proposal (v1)

Keep the existing single-host Docker Compose architecture and both public hostnames. Create an x86 Hetzner Cloud server in Ashburn with Ubuntu 24.04, a public IPv4, local disk, and daily backups. Measure current resource use before selecting the server size; provision at least 4 GB RAM and 40 GB disk as an initial sizing assumption. Copy application state and certificates over SSH, restore the same deployed image SHA, and test using local hostname overrides before changing DNS. Freeze writes for a final SQLite backup and content sync. Switch both DNS records, make Hetzner the only writer, switch GitHub deployment secrets, and enable its daily timer. Keep DO available for rollback for 48–72 hours. Update the privacy policy and retire DO after a successful scheduled run, deployment, certificate renewal check, and backup restore drill.

## Research and constraints

- Production state is host-mounted, not inside images: [compose](../docker-compose.prod.yml), lines 15–19, 35–37, 56–59. Public posts are ignored by Git and therefore require a host-to-host copy: [.gitignore](../.gitignore), `blog/_posts/*`.
- SQLite uses WAL: [schema](../app/schema.sql). The deploy script resets the host checkout to current `origin/main`, while selecting images by supplied SHA: [deploy script](../scripts/deploy-paperpulse.sh), lines 37–52. Freeze deploys and align the checkout and all images during migration.
- TLS terminates in nginx with separate certificate directories for both hostnames: [nginx config](../nginx/nginx.conf). Preserve the complete Certbot directory, including symlinks and renewal configuration.
- OAuth callbacks use the existing hostname; nginx forwarding and `FORWARDED_ALLOW_IPS` are required: [compose](../docker-compose.prod.yml), lines 39–42. Preserve the session secret to preserve valid browser sessions.
- GitHub deploy uses `DROPLET_HOST`, `DROPLET_KNOWN_HOSTS`, and `DEPLOY_SSH_PRIVATE_KEY`: [workflow](../.github/workflows/deploy.yml), lines 137–151. Names can stay during migration.
- Only one host may run the daily timer: [timer](../systemd/paperpulse-daily.timer), lines 7–10. Its persistent setting can trigger a catch-up run when first enabled.
- Privacy text currently names DO/New York and seven-day backups: [policy](../blog/privacy.markdown), lines 29–39.
- Hetzner describes application-data transfer and explicitly requires stopping writes for the final backup: [migration guide](https://docs.hetzner.com/cloud/servers/getting-started/migrate-data/).
- Ashburn is a supported US-East location: [locations](https://docs.hetzner.com/cloud/general/locations/). Select an available x86 AMD plan there; current CI builds on Ubuntu x86 and declares no multi-architecture platforms.
- Public connectivity needs a Primary IP: [server overview](https://docs.hetzner.com/cloud/servers/overview/). Keep IPv4 for browser/client compatibility; configure IPv6 only if tested.
- Provider backups have seven rotating slots and exclude attached Volumes: [backup overview](https://docs.hetzner.com/cloud/servers/backups-snapshots/overview/). Running-server copies have no consistency guarantee; deleted-server backups disappear, while snapshots persist: [backup FAQ](https://docs.hetzner.com/cloud/servers/backups-snapshots/faq/).
- Backups cost 20% of server price; IPs and snapshots are billed separately: [billing FAQ](https://docs.hetzner.com/cloud/billing/faq/). Obtain the actual plan quote at provisioning; no fixed price assumed.
- Use provider firewall rules for public ports: [firewalls](https://docs.hetzner.com/cloud/firewalls/overview/).

## Senior review

Isolated review completed 2026-10-02 against frozen v1, repository code, and primary documentation. Diagnosis: **fog** — the architecture fit, but operational gates were underspecified.

### Blockers resolved in v2

- **Writer fencing:** Google OAuth callback GETs write to SQLite as well as settings/deletion POSTs ([auth](../app/auth.py), lines 48–86; [routes](../app/routes.py), lines 102–174). Stop the old app, drain the pipeline, freeze deploys, and use forwarding during DNS propagation.
- **Stale rollback:** hard deletion means returning to the old DB can resurrect accounts ([routes](../app/routes.py), lines 163–166). Define separate pre-write and post-write rollback; reverse-sync current state after cutover writes.
- **SQLite WAL transfer:** WAL is enabled ([schema](../app/schema.sql), line 1). Use a consistent `.backup`, verify integrity and hashes, and replace the rehearsal DB with its app stopped. [SQLite backup API](https://www.sqlite.org/backup.html), fetched 2026-10-02.

### Major issues resolved in v2

- Pin bootstrap checkout and image digests; the current deploy script combines supplied image SHA with current `main` ([script](../scripts/deploy-paperpulse.sh), lines 41–52).
- Recreate forced-command SSH, sudoers, registry/repository access, and workable hosted-runner firewall access ([setup](DROPLET_SETUP.md), sections 3–7).
- Migrate renewal automation as well as certificate files; compose defines a Certbot service but no scheduler ([compose](../docker-compose.prod.yml), lines 65–70).
- Distinguish seven rotating backup slots from guaranteed seven-day expiry and application-consistent SQLite backups. [Hetzner FAQ](https://docs.hetzner.com/cloud/servers/backups-snapshots/faq/), fetched 2026-10-02.
- Avoid accidental API runs during rehearsal and persistent-timer catch-up; verify produced artifacts because exceptions can be caught without a failing process exit ([main](../api/main.py); [timer](../systemd/paperpulse-daily.timer), line 10).

Preserved from v1: single-host Compose, x86 images, existing hostnames/session secret, measured sizing, HTTPS rehearsal, and bounded DO overlap.

## Promoted plan (v2)

### Goal and scope

Move the public blog and personalized app to Hetzner with existing URLs, accounts, category choices, content history, sessions, and daily publishing preserved. Pause product work during migration. Preserve the current Docker Compose, GHCR, nginx, Certbot, SQLite, and systemd architecture. No Kubernetes, database replacement, DNS-provider move, or ARM port is needed.

Default assumptions awaiting owner preference: Ashburn, US East; brief personalized-app maintenance window allowed. The public blog can remain available. This is a plan, not a record of current production state: live server sizes, DNS ownership, certificates, deployed SHA, and backup status must be inventoried before execution.

### 1. Inventory and freeze deployments

Do this before buying the final server or scheduling cutover.

- Inventory DO CPU/RAM, peak memory, disk use/free space, Docker image use, content sizes, current deployed image tags/digests, host Git revision and changes, numeric ownership, OS, timezone, firewall, cron/systemd jobs, and certificate expiry/renewal method. Record metadata only; never secrets or user identities in the plan/worklog.
- Inventory A, AAAA, CNAME, TTL, DNS provider, and whether changing DNS depends on keeping the DO account active. Keep DNS service where it is; migrating hosting does not require moving nameservers or mail/MX records.
- Check GHCR pulls and GitHub repository access required by the root-run deploy script. Record the existing deploy key restriction and sudoers rule.
- Freeze merges/production deploys and drain already-running or queued deployment jobs. Record a migration image SHA shared by all three images and its matching checkout, plus the exact digests of nginx/Certbot and other floating-tag images. Use those captured digests during bootstrap, then resume normal image policy after acceptance. If actual production differs, resolve that difference before proceeding.
- Lower both site DNS TTLs to 300 seconds at least one previous TTL before cutover. Cached records can outlive the intended window; plan for that.

**Done when:** state manifest and restore paths are complete; deploys frozen; old DNS values saved; provisioning quote reviewed.

### 2. Provision one Hetzner Cloud server

- Choose an available **x86 AMD server in Ashburn**, Ubuntu 24.04 LTS, public Primary IPv4, daily backups, and local root disk. Initial sizing target: at least 2 vCPU, 4 GB RAM, 40 GB disk, increased if the inventory or headroom warrants it. This is a sizing estimate, not a guaranteed plan SKU. Maintain at least 30% free disk after staging images and data; previous production ran out of disk from image accumulation.
- Budget: selected US-region server quote plus backups (20% of server price), IPv4, tax, temporary overlap with DO, and any snapshots/traffic charges. Prices and regional availability must be checked in Console when provisioning. [Hetzner billing](https://docs.hetzner.com/cloud/billing/faq/).
- Add admin SSH keys at creation. Configure a Hetzner Firewall: public TCP 80/443; TCP 22 from admin addresses, temporarily DO for transfer, and a workable CI SSH policy. GitHub-hosted runners have changing source addresses, so an admin-only SSH allowlist breaks deployment. For this existing forced-command/key-only setup, permit CI SSH access without inventing a static runner IP; use broad TCP 22 if necessary, with password login disabled. [Firewall behavior](https://docs.hetzner.com/cloud/firewalls/overview/).
- Install Docker Engine and Compose V2 from Docker's official apt repository, Git, rsync, sqlite3, and timezone data. [Docker Ubuntu installation](https://docs.docker.com/engine/install/ubuntu/).
- Recreate `/var/www/arxivsum`, `/var/lib/paperpulse/{db,content,secrets}`, and logs. Preserve numeric permissions; the blog container needs UID 1000 write access ([Dockerfile](../Dockerfile.jekyll), lines 10–16). Keep secrets root-owned and mode 600.
- Recreate the forced-command `deploy` user and root-owned `/usr/local/sbin/deploy-paperpulse` using [existing setup](DROPLET_SETUP.md). Verify the new SSH host fingerprint through Hetzner Console before pinning it; `ssh-keyscan` alone does not establish trust.
- Install the daily units but leave the timer disabled. Configure services to recover after reboot: current compose has no restart policy, so add `restart: unless-stopped` to blog/app/nginx in a small migration prep change, or explicitly install a boot service that starts those services. Do not apply automatic restart to the one-shot API pipeline.

**Done when:** verified SSH, Docker/Compose, image pulls, storage permissions, firewall access, and disabled timer. No public DNS changes yet.

### 3. Copy state and rehearse

Transfer over SSH with permissions and symlinks preserved. Use dedicated temporary transfer access, removed after migration.

| State | Source and destination path | Treatment |
| --- | --- | --- |
| Public archive | `/var/www/arxivsum/blog/_posts/` | Required: ignored by Git; copy all posts |
| Feed archive | `/var/lib/paperpulse/content/` | Copy all dated category Markdown |
| User database | `/var/lib/paperpulse/db/paperpulse.sqlite` | Restore a SQLite backup, not a raw live-file copy |
| Secrets | `/var/lib/paperpulse/secrets/` | Preserve Gemini/OAuth/session values; never commit or print |
| TLS | `/var/www/arxivsum/certbot/` | Copy complete `conf` and webroot, preserving symlinks/private-key permissions |
| Operational state | Logs, relevant units/cron, deploy configuration | Preserve needed logs and rebuild host-specific configuration |

Clone/check out the matching application revision and overlay generated posts/content. Do not copy Docker's storage directory or the old OS wholesale. Reuse GHCR images, including the pinned Jekyll image behavior. Do not run the normal deploy script against an older SHA while `main` has newer host-mounted assets; its `git reset --hard origin/main` would mismatch the checkout and images.

Use SQLite `.backup` for the staging DB. The backup API provides a consistent DB copy, including committed WAL data. [SQLite backup documentation](https://www.sqlite.org/backup.html).

Start blog/app/nginx using the migration SHA; tag that API image as local `latest` for the timer. Avoid `compose up` of the entire stack during rehearsal: that would also start the one-shot API. Keep the new app reachable only to testers while it contains a staging production DB. Use laptop hosts-file overrides for both existing domains to test real HTTPS and OAuth before DNS changes; Google redirect URLs remain unchanged because hostnames remain unchanged.

Rehearse blog/archive/privacy/login, actual OAuth round-trip, existing session, category settings, feed dates, Markdown links, logout, and deletion using a disposable account. Do not mutate real-user settings on the staging copy. Test nginx forwarding, `/healthz`, certificate chains, reboot recovery, and restore integrity. A successful startup can silently create an empty DB; verify counts/content against the manifest, not just HTTP 200.

**Done when:** both sites work via the Hetzner IP with their production hostnames, no unexpected pipeline execution, and restore/reboot checks pass. Rehearsal DB will be replaced at final sync.

### 4. Final sync and cutover

Schedule outside the 6am Eastern pipeline window. Aim for 10–20 minutes of personalized-app maintenance; actual duration comes from the rehearsal. DNS convergence is separate and may take longer.

1. On DO, disable the daily timer and confirm no pipeline/container run is active. Let any active run finish before freezing content. Keep Hetzner's timer disabled.
2. Put both personalized-app entry points into maintenance. Stop the DO app so OAuth callbacks, signups, settings, and deletions cannot write. Stop the Hetzner staging app too. Keep the DO public blog serving during the transfer.
3. Create the final SQLite `.backup` after writers stop; run `PRAGMA integrity_check` and `PRAGMA foreign_key_check`, and record non-PII table counts. Transfer that standalone backup plus final posts/content delta. Restore into a clean destination DB directory; do not leave WAL/SHM files from the rehearsal DB beside the replacement database. Retain the pre-cutover backup briefly for rollback.
4. Verify backup checksum, DB counts, file manifest, secret permissions, TLS expiry, and matching image/checkout versions. Start the Hetzner app behind maintenance; perform restricted checks.
5. Configure DO nginx to forward the app hostname to **Hetzner's fixed IP over verified HTTPS**, preserving Host and forwarding headers, setting TLS SNI to the app hostname, and trusting the certificate chain. Use the IP as upstream, not public DNS, to avoid looping while old DNS remains cached. Keep DO's local app stopped. Validate nginx configuration and reload explicitly; compose does not automatically reload a bind-mounted config change.
6. Open the Hetzner app for public traffic. DO and Hetzner now lead to the same writable app, including clients with old DNS. Update **both hostnames' A records**. Update or remove old **AAAA** records too; never leave IPv6 pointing to DO unintentionally. Proxy the blog from DO as well if identical fresh content is required during propagation; otherwise its copied archive remains readable while the pipeline is paused.
7. Replace GitHub `DROPLET_HOST` and `DROPLET_KNOWN_HOSTS` with Hetzner values. Install the existing CI public key or update `DEPLOY_SSH_PRIVATE_KEY` if using a new pair. Keep secret names for now; provider-neutral renaming can wait. Test the real deploy path after DNS/private smoke checks pass. Temporarily stop the DO forwarding bridge from being overwritten by a stray deploy; deploy freeze remains until the CI target is verified.
8. Confirm DO timer disabled; enable only Hetzner timer. Inspect persistent-timer catch-up behavior before enabling, and avoid duplicate manual plus scheduled runs. Restore DNS TTL to the normal value after stabilization.

**Done when:** DNS and old-IP traffic reach the same app, writes persist only on Hetzner, CI deploy targets Hetzner, and only its timer is active.

### 5. Backup, renewal, and first scheduled run

- Enable seven-slot provider backups on local disk. Add a daily SQLite online backup on the root disk with atomic completion, integrity verification, and at most seven days of retained files. This gives consistent DB restore material inside server backups; provider disk copies of a running server are not application-consistent by guarantee. [Hetzner backup FAQ](https://docs.hetzner.com/cloud/servers/backups-snapshots/faq/).
- Restore a backup into an isolated temporary server/DB and verify schema, counts, and feed content. Disable timers and public app access on the restore target. Daily backups imply up to roughly one day of DB changes at risk; cross-provider/off-host DB copies are optional if a stronger recovery target is wanted.
- Inspect and migrate the actual Certbot renewal timer/cron, webroot paths, and nginx reload hook. Compose's `certbot` service alone does not schedule renewal. Once DNS points to Hetzner, run a renewal dry run for both certificates and verify reload behavior separately or with supported `--run-deploy-hooks`; ordinary dry-run does not establish that the reload hook ran. HTTP-01 uses port 80 and the challenge path. [Let's Encrypt challenges](https://letsencrypt.org/docs/challenge-types/).
- Watch the first actual scheduled pipeline run. Verify new public post and relevant non-empty category blurbs, Jekyll refresh, host logs, disk space, and journal. Check artifacts, not merely service exit status: pipeline code catches exceptions and can still exit successfully ([pipeline](../api/main.py)). If arXiv has no new papers, record that and wait for the next publishing day or use a restricted mocked smoke run; do not manufacture public content.
- Publish the privacy-policy update at cutover: Hetzner and chosen location, temporary DO migration copy, actual backups/retention, and new last-updated date. Seven backup slots are not an unconditional seven-day expiry if new backups fail; monitor/prune stale snapshots and copies to honor the policy. Manual Hetzner snapshots persist until deleted. Never claim they expire automatically.

**Done when:** successful scheduled publishing, verified CI deploy, certificate renewal test, tested restore, and accurate public privacy text.

### 6. Retire DO

Keep the old host as a forwarding bridge for at least 48–72 hours and longer if the first real publishing run/backup validation is still pending. The old DB is stale after cutover; isolate it from all application writes and logins. Avoid prolonged retention of deleted user data: remove stale migration DB copies within seven days, and rely on a reverse sync of current Hetzner state if rollback is needed.

After acceptance, remove temporary transfer keys, DO forwarding/credentials, and unneeded migration backups. Verify DNS/mail are independent before deleting any DO account resources. Delete the droplet and inventory/delete its unwanted snapshots/backups according to the retention commitment. Keep any DO DNS zone if it still hosts the domain. Update README and operational runbooks to name Hetzner. Delete temporary Hetzner snapshots and restore servers too; stopped servers still incur charges. [Hetzner locations and billing](https://docs.hetzner.com/cloud/general/locations/).

### Rollback rules

**Before Hetzner accepts public writes:** keep the new app blocked, restore original DO nginx config, start the old app, point any changed DNS back to DO, restore GitHub deploy secrets, and enable only the DO timer. Discard rehearsal state.

**After Hetzner accepts public writes:** a DNS-only rollback loses new accounts/settings/deletions and can resurrect deleted accounts. Freeze writes at both entry points, stop Hetzner pipeline/app, take a fresh consistent backup of its current DB, and reverse-sync that DB plus new posts/content to DO with both apps stopped. Clear stale destination WAL/SHM only after all DB users stop; validate integrity/counts. Then start DO as sole writer and switch routing/DNS/CI/timer back. If reverse-sync is impossible, keep maintenance active and make any data-loss decision explicit; never silently restore the stale pre-cutover DB.

Prefer fixing/redeploying the app on Hetzner over moving the DB back when only code is broken. The pre-cutover host is a routing/code fallback, not an automatically safe database rollback.

### Owner decisions before execution

- Region: default Ashburn preserves US hosting; European location is a price/latency/data-location tradeoff.
- Acceptable maintenance window and data-recovery target: default brief app maintenance, daily backups.
- Server budget after live inventory and Console quote.
- DNS provider/account access and intended cutover time.

No answer is needed to review this plan. Provisioning, secret transfer, production cutover, and DO deletion are future execution steps.

## Delta from v1

- Replaced generic write freeze with app shutdown, pipeline drain, deploy freeze, and old-host forwarding.
- Split rollback at the first public Hetzner write; added reverse transfer to preserve updates and deletions.
- Specified consistent SQLite transfer, clean restore, checksums, counts, and archive manifests.
- Added complete image/checkout pinning, SSH/CI setup, reboot recovery, and certificate-renewal checks.
- Added explicit backup consistency, temporary-copy expiry, privacy update, and artifact-based scheduled-run acceptance.
