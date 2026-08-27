# Deploy CaseCite on Coolify

## The 10-Minute Guide

---

## STEP 1: Push Code to GitHub (3 min)

### If you don't have Git installed:
Download from: https://git-scm.com/downloads

### Push your code:

1. Open **PowerShell** (Windows) or **Terminal** (Mac)

2. Go to your project folder:
```
cd path\to\casecite
```

3. Create a GitHub repo at https://github.com/new
   - Name: `casecite`
   - Your fork can be **private** (fine for your own deployment under the source-available license)
   - Click **Create repository**

4. Push your code (copy these one at a time):
```
git init
git add .
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/casecite.git
git push -u origin main
```

✅ **Done!** Your code is on GitHub.

---

## STEP 2: Open Coolify (30 sec)

1. Open your browser
2. Go to your Coolify dashboard: `http://YOUR_HETZNER_IP:8000`
3. Log in

---

## STEP 3: Connect GitHub (2 min)

1. Click **⚙️ Settings** (bottom left)
2. Click **Sources**
3. Click **+ Add New**
4. Click **GitHub App**
5. Click **Register Now** button
6. GitHub opens → Click **Install**
7. Pick **"Only select repositories"**
8. Choose your `casecite` repo
9. Click **Install**
10. You're back in Coolify → Click **Save**

✅ **Done!** GitHub is connected.

---

## STEP 4: Create Your App (2 min)

1. Click **Projects** (left menu)
2. Click **+ Add**
3. Name: `CaseCite`
4. Click **Save**
5. Click on your new project
6. Click **+ New Resource**
7. Click **Public Repository** or **Private Repository (with GitHub App)**
8. Pick your `casecite` repo

### Configure Build Settings:

```
┌────────────────────────────────────────────┐
│                                            │
│  Build Pack:     Dockerfile               │
│                                            │
│  Dockerfile:     /Dockerfile              │
│                                            │
│  Port:           80                        │
│                                            │
└────────────────────────────────────────────┘
```

9. Click **Save**

---

## STEP 5: Add Your Settings (1 min)

1. Click **Environment Variables** tab
2. Click **Add** for each one:

| Variable | Value |
|----------|-------|
| `OPENAI_API_KEY` | `sk-your-key-here` |
| `SECRET_KEY` | output of `openssl rand -hex 32` (must be ≥ 32 chars) |
| `ENCRYPTION_SALT` | output of `openssl rand -hex 16` (never change after first run) |
| `AUDIT_HMAC_KEY` | output of `openssl rand -hex 32` |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/casecite` |
| `REDIS_URL` | `redis://:password@host:6379/0` |
| `CORS_ORIGINS` | `https://your-domain.com` |
| `ALLOWED_HOSTS` | `your-domain.com` |
| `TRUSTED_PROXIES` | your proxy's Docker subnet (e.g. `10.0.0.0/8`) — **required behind Traefik** |

Generate the three secrets locally first:

```bash
openssl rand -hex 32   # SECRET_KEY and AUDIT_HMAC_KEY (run twice)
openssl rand -hex 16   # ENCRYPTION_SALT
```

The app fails closed on startup if any required secret is missing or left as a placeholder.

### Where to get OpenAI key:
1. Go to https://platform.openai.com/api-keys
2. Click **Create new secret key**
3. Copy it

---

## STEP 6: Set Your Domain (1 min)

1. Click **Settings** tab (or **Domain** tab)
2. Enter your domain (the same host you put in `CORS_ORIGINS` / `ALLOWED_HOSTS`):
```
app.yourdomain.com
```
3. Turn ON **Generate SSL Certificate** ✅
4. Click **Save**

### Don't forget DNS!
In your domain provider (GoDaddy, Namecheap, Cloudflare):
```
Type:  A
Name:  app
Value: YOUR_HETZNER_IP
```

---

## STEP 7: Deploy! 🚀 (5 min)

1. Click the big **Deploy** button
2. Watch the logs (it shows what's happening)
3. Wait for green checkmark ✅

---

## Deployment Complete

Open: **https://app.yourdomain.com**

You should see the CaseCite login page.

---

## What to Do Next

1. **Register the first account** - it becomes the admin (set `REGISTRATION_BOOTSTRAP_TOKEN` first if the instance is already reachable)
2. **Upload documents** - Click Documents → Upload
3. **Test a query** - Ask it a legal question

---

## Quick Fixes

### ❌ "502 Bad Gateway"
→ Click **Restart** in Coolify, wait 2 min

### ❌ "Page not found"
→ Check domain spelling in Coolify settings

### ❌ "Build failed"
→ Check you added OPENAI_API_KEY in environment variables

### ❌ Site loads but no AI response
→ Your OpenAI key might be wrong or expired

### ❌ DNS not working
→ Wait 15 min, DNS can be slow

---

## Commands Cheat Sheet

### Update your site after making changes:
```
git add .
git commit -m "updated something"
git push
```
Then click **Deploy** in Coolify (or it auto-deploys).

### Check if it's working:
Visit: `https://app.yourdomain.com/health`
Should say: `{"status": "healthy"}`

---

## Repository Files

```
CaseCite
├── Dockerfile         ← Coolify builds this (frontend + backend in one image)
├── start.sh           ← Container entrypoint
├── nginx.unified.conf ← In-container web server config
├── frontend/          ← React SPA (built during the image build)
└── backend/
    └── app/           ← FastAPI application
```

---

## Need Help?

1. **Coolify Docs**: https://coolify.io/docs
2. **OpenAI Status**: https://status.openai.com
3. **Check Logs**: Coolify → Your Project → Logs tab
