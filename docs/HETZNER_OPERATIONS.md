# Hetzner migration operations

Apply the privacy-policy change only at cutover. During private rehearsal,
DigitalOcean remains the production writer and the Hetzner daily timer stays disabled.

## Installed host configuration

- Repo: `/var/www/arxivsum`.
- SQLite/content/secrets: `/var/lib/paperpulse/{db,content,secrets}`.
- Checked DB backups: `/var/lib/paperpulse/backups`, root-only.
- Install `scripts/backup-paperpulse-db.py` as
  `/usr/local/sbin/backup-paperpulse-db.py` (root-owned, mode 755).
- Install `systemd/paperpulse-db-backup.{service,timer}` under
  `/etc/systemd/system/` (mode 644). Run `systemctl daemon-reload`.
- Enable the DB-backup timer at cutover. It runs at 00:30 UTC before the
  provider's observed 02–06 UTC backup window. Check the provider window
  again if configuration changes. Run the service manually for a verified
  backup immediately after final sync.
- Only blog/app/nginx restart automatically. CI starts these services;
  API runs only via its daily systemd timer or explicit pipeline request.
- Install the updated deploy script at `/usr/local/sbin/deploy-paperpulse`.
  Updating its repository copy does not update the installed host script.

## Renewal cron

Install on Hetzner after DNS cutover:

```cron
0 0,12 * * * cd /var/www/arxivsum && /usr/bin/docker compose -f docker-compose.prod.yml run --rm certbot renew --quiet && /usr/bin/docker compose -f docker-compose.prod.yml exec -T nginx nginx -t && /usr/bin/docker compose -f docker-compose.prod.yml exec -T nginx nginx -s reload
```

Run the certificate renewal dry-run after both DNS records resolve to Hetzner.
Check nginx reload separately; an ordinary dry-run does not establish hook execution.

## Recovery and retention

Verify provider backups complete and the database-backup service succeeds daily.
Seven provider slots are a rotation count, not guaranteed seven-day expiry if
new backups fail. Monitor/remove stale provider backups, manual snapshots,
and migration copies. Local DB copies are pruned only after a successful backup.

For a DB restore, stop the app and daily pipeline, retain a current checked
backup, restore into a clean DB directory, and run SQLite integrity/foreign-key
checks before reopening writes. Never restore a stale pre-cutover DB after
Hetzner accepts writes. Reverse-sync current state for a post-cutover rollback.

Keep the DO forwarding bridge for at least 48–72 hours and until real scheduled
publishing, certificate renewal, CI deploy, and isolated restore checks pass.
Remove stale migration data within seven days of cutover. DO resource deletion
requires separate owner approval.
