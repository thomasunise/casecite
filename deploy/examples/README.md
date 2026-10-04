# CD Workflow Templates

These are **example** GitHub Actions workflows for continuous deployment. They are not active — to use one, copy it into `.github/workflows/` and configure the required secrets.

Each template triggers after the CI pipeline (`ci.yml`) pushes a new Docker image to GHCR.

## Pick a Template

| Template | Target | Best For |
|----------|--------|----------|
| `deploy-coolify-webhook.yml` | Coolify | Instances managed by Coolify |
| `deploy-docker-compose.yml` | Any VPS via SSH | Hetzner, DigitalOcean, Linode, self-hosted — pins each deploy to the commit SHA |
| `deploy-azure.yml` | Azure Container Apps | Private client deployments on Azure |

Serverless targets (Cloud Run, Lambda) are not supported: the embedded
ChromaDB index needs a persistent local disk (see `docs/adr/004-deployment-topology.md`).

## How to Use

1. Copy the file you need:
   ```bash
   cp deploy/examples/deploy-coolify-webhook.yml .github/workflows/
   ```

2. Add the required GitHub secrets. Go to your repo → **Settings** → **Secrets and variables** → **Actions**.

3. Push to `main`. The CI pipeline runs first; on success, your CD workflow triggers. The templates deploy only for a push to this repository's `main` — a CI run for a pull request never deploys.

## Required Secrets per Template

### Coolify Webhook

| Secret | Description |
|--------|-------------|
| `COOLIFY_WEBHOOK_URL` | Deploy webhook URL from Coolify resource settings |

### Docker Compose (VPS)

Create a GitHub Environment named `production`, then add:

| Secret | Description |
|--------|-------------|
| `DEPLOY_HOST` | VPS IP address or hostname |
| `DEPLOY_USER` | SSH username (e.g. `root` or `deploy`) |
| `DEPLOY_SSH_KEY` | Private SSH key (ed25519 or RSA) |
| `DEPLOY_HOST_FINGERPRINT` | The server's SSH host-key fingerprint (`ssh-keygen -l -f /etc/ssh/ssh_host_ed25519_key.pub \| cut -d ' ' -f2`), so the key is never offered to an impostor host |
| `GHCR_PULL_TOKEN` | GitHub PAT with only `read:packages`, for `docker login` on the VPS (omit if the package is public) |

The image name comes from `CASECITE_IMAGE` in the server's `.env`
(default `ghcr.io/thomasunise/casecite`); the workflow writes the deployed
commit SHA to `CASECITE_TAG` there, so `CASECITE_TAG=<older-sha> docker compose
-f docker-compose.prod.yml up -d` is the rollback.

### Azure Container Apps

Create a GitHub Environment named `production`, then add:

| Secret | Description |
|--------|-------------|
| `AZURE_CLIENT_ID` | Service principal or managed identity client ID |
| `AZURE_TENANT_ID` | Azure AD tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `AZURE_RESOURCE_GROUP` | Resource group name |
| `AZURE_APP_NAME` | Container App name |

Deploys the image tagged with the commit SHA CI just built, not `:latest`. Uses Workload Identity Federation (OIDC) — no client secrets needed. See [Azure OIDC setup](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure).
