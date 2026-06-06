# Droplet setup for automated CI deploys

One-time setup to wire the GitHub Actions `deploy` job into the droplet. Do this after the CI/CD PR has merged to `main` (so the deploy script exists at `scripts/deploy-paperpulse.sh` on the droplet).

All commands run as **root** on the droplet unless otherwise noted.

## 1. Create the `deploy` user

```bash
# Create user with no password, no shell warmth, no home extras
useradd --create-home --shell /bin/bash --comment "CI deploy" deploy

# Lock the password — only key-based SSH allowed
passwd -l deploy

# Set up .ssh dir
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
```

The `deploy` user has a shell (needed so `command="..."` in `authorized_keys` can execute), but the locked password and forced-command restriction below mean it can only run the deploy script — no interactive sessions.

## 2. Generate the SSH keypair

**On your laptop**, generate a dedicated keypair just for CI:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/paperpulse-deploy -C "paperpulse-ci-deploy" -N ""
```

Two files appear:
- `~/.ssh/paperpulse-deploy` — private key (goes into GitHub Actions secret)
- `~/.ssh/paperpulse-deploy.pub` — public key (goes onto droplet)

## 3. Install the public key with command-restriction

Copy the contents of `~/.ssh/paperpulse-deploy.pub` (a single line starting with `ssh-ed25519 …`). Then on droplet:

```bash
# Edit /home/deploy/.ssh/authorized_keys
cat > /home/deploy/.ssh/authorized_keys <<'EOF'
command="sudo --preserve-env=SSH_ORIGINAL_COMMAND /usr/local/sbin/deploy-paperpulse",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty <PASTE_PUBLIC_KEY_HERE>
EOF

# Replace <PASTE_PUBLIC_KEY_HERE> with the actual line from ~/.ssh/paperpulse-deploy.pub
nano /home/deploy/.ssh/authorized_keys   # or your editor

# Perms
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
```

What this does:
- Every SSH login as `deploy` is forced through `sudo … /usr/local/sbin/deploy-paperpulse`, regardless of what the client tries to run
- The argument the client sent (the git SHA) lands in `$SSH_ORIGINAL_COMMAND`
- `sudo --preserve-env=SSH_ORIGINAL_COMMAND` carries that env var into the privileged execution
- `no-pty`, `no-*-forwarding` disable shell access, port forwarding, X11, agent forwarding

## 4. Sudoers fragment

```bash
cat > /etc/sudoers.d/deploy-paperpulse <<'EOF'
# Allow the deploy user to run exactly one root-owned script, with SSH_ORIGINAL_COMMAND preserved.
deploy ALL=(root) NOPASSWD: SETENV: /usr/local/sbin/deploy-paperpulse
EOF

chmod 440 /etc/sudoers.d/deploy-paperpulse

# Validate the new fragment doesn't break sudo
visudo -cf /etc/sudoers.d/deploy-paperpulse
# Expected: "/etc/sudoers.d/deploy-paperpulse: parsed OK"
```

## 5. Install the deploy script

```bash
cd /var/www/arxivsum
git fetch origin main
git reset --hard origin/main

install -m 755 -o root -g root scripts/deploy-paperpulse.sh /usr/local/sbin/deploy-paperpulse

# Verify
ls -la /usr/local/sbin/deploy-paperpulse
# Expected: -rwxr-xr-x 1 root root <size> <date> /usr/local/sbin/deploy-paperpulse
```

## 6. Capture ssh-keyscan output for GitHub Actions

**On your laptop:**

```bash
ssh-keyscan -t ed25519 <DROPLET_IP>
```

Copy the entire output (a single line starting with the IP, then `ssh-ed25519`, then the host key). You'll paste this into the `DROPLET_KNOWN_HOSTS` secret.

## 7. Configure GitHub Actions secrets

In GitHub → Settings → Secrets and variables → Actions → New repository secret, add three:

- **`DEPLOY_SSH_PRIVATE_KEY`** — entire contents of `~/.ssh/paperpulse-deploy` (the private key file). Include the `-----BEGIN OPENSSH PRIVATE KEY-----` / `-----END OPENSSH PRIVATE KEY-----` lines.
- **`DROPLET_HOST`** — your droplet's IP address.
- **`DROPLET_KNOWN_HOSTS`** — the line(s) from `ssh-keyscan` in step 6.

## 8. Create the `production` GitHub Environment

GitHub → Settings → Environments → New environment → name it `production`.

Recommended protection rules:
- **Required reviewers** — add yourself. Each deploy will pause for your approval in the GH UI before running.
- **Deployment branches** — restrict to `main` only.

Without protection rules, deploys run automatically on every push to `main`.

## 9. Smoke test

The cleanest test: open a tiny PR on `main` that changes one harmless file (e.g., a comment in README), merge it, watch:

1. The `test` job runs (~30s)
2. The `build` job runs and pushes images to GHCR (~2 min)
3. The `deploy` job pauses for approval (if you configured protection rules). Approve it.
4. The `deploy` job SSHes into the droplet and runs the deploy script
5. The deploy script git-resets the droplet to the merge commit's SHA, pulls images, recreates containers

Verify on droplet after deploy:

```bash
docker compose -f /var/www/arxivsum/docker-compose.prod.yml ps
# All services should show "Up"

cd /var/www/arxivsum && git rev-parse HEAD
# Should match the merge commit SHA
```

If anything goes sideways, see `ROLLBACK.md`.

## Manual deploy (no SSH path)

You can also invoke the deploy script directly on the droplet:

```bash
sudo /usr/local/sbin/deploy-paperpulse <40-char-git-sha>

# Or with optional pipeline trigger
sudo /usr/local/sbin/deploy-paperpulse <40-char-git-sha> --run-pipeline
```

CI never passes `--run-pipeline`. Daily pipeline runs via the systemd timer (step 6 of the CI/CD plan).
