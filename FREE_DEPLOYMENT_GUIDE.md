# Deploy NETS Tender Scout: 100% Free (Step by Step)

Everything below is free. The only cost is the Anthropic API for AI-powered proposal writing (~$0.50 per proposal). The scraping, database, server, and dashboard are all free.

---

## Overview: What Goes Where

```
GitHub (your code)
    |
    |-- GitHub Actions (free cron job, scrapes Sindh Bank daily)
    |       |
    |       v
    |   Supabase (free PostgreSQL database)
    |       ^
    |       |
    +-- Render.com (free server, runs dashboard + API)
            |
            v
        Your browser (http://your-app.onrender.com)
```

---

## STEP 1: Create a GitHub Account (if you don't have one)

1. Go to https://github.com
2. Click "Sign up"
3. Use your email, create a username, set a password
4. Verify your email

---

## STEP 2: Create a Supabase Database (free PostgreSQL)

This is where all your tender data lives. Free tier gives you 500MB, which is enough for tens of thousands of tenders.

1. Go to https://supabase.com
2. Click "Start your project" and sign in with your GitHub account
3. Click "New Project"
4. Fill in:
   - **Project name**: `nets-tender-scout`
   - **Database password**: choose a strong password and SAVE IT (you need it later)
   - **Region**: choose the closest to Pakistan (e.g., "South Asia (Mumbai)")
5. Click "Create new project". Wait 2 minutes for it to set up.
6. Once ready, click "Settings" (gear icon, bottom left)
7. Click "Database" in the left menu
8. Scroll to "Connection string" section
9. Click "URI" tab
10. Copy the connection string. It looks like:

```
postgresql://postgres.[something]:YOUR-PASSWORD@aws-0-ap-south-1.pooler.supabase.com:6543/postgres
```

11. Replace `YOUR-PASSWORD` in that string with the password you chose in step 4

**Save this connection string. You need it in Steps 3 and 4.**

---

## STEP 3: Upload the Code to GitHub

1. Go to https://github.com/new
2. Fill in:
   - **Repository name**: `nets-tender-scout`
   - **Visibility**: Private (recommended) or Public
3. Click "Create repository"
4. You will see instructions. Follow the "push an existing repository" section:

**On your computer, open a terminal/command prompt:**

```bash
cd Desktop/nets-tender-scout

git init
git add .
git commit -m "Initial commit: NETS Tender Scout"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/nets-tender-scout.git
git push -u origin main
```

Replace `YOUR-USERNAME` with your GitHub username.

If you don't have Git installed:
- **Windows**: download from https://git-scm.com/download/win
- **Mac**: type `git` in Terminal, it will prompt to install

5. Refresh your GitHub repository page. You should see all the files.

### Add Your Secrets to GitHub

The scraper needs your database connection string. You must NOT put it in the code (anyone could see it).

1. On your GitHub repo page, click "Settings" tab
2. Click "Secrets and variables" > "Actions" in the left menu
3. Click "New repository secret"
4. Add these secrets one at a time:

| Secret name | Value |
|---|---|
| `DATABASE_URL` | Your Supabase connection string from Step 2 |
| `ANTHROPIC_API_KEY` | Your Anthropic API key (from https://console.anthropic.com/) |

---

## STEP 4: Deploy the Server on Render (free)

This runs your dashboard and API.

1. Go to https://render.com
2. Click "Get Started" and sign in with your GitHub account
3. Click "New" > "Web Service"
4. Connect your GitHub account if asked
5. Find and select your `nets-tender-scout` repository
6. Fill in:
   - **Name**: `nets-tender-scout`
   - **Region**: closest to you (e.g., Frankfurt or Singapore)
   - **Branch**: `main`
   - **Runtime**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free
7. Click "Advanced" and add these environment variables:

| Key | Value |
|---|---|
| `DATABASE_URL` | Your Supabase connection string from Step 2 |
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `SCAN_HOUR` | `5` |
| `SCAN_MINUTE` | `47` |
| `PYTHON_VERSION` | `3.12.0` |

8. Click "Create Web Service"
9. Wait 5 to 10 minutes for it to build and deploy

When it finishes, Render gives you a URL like:

```
https://nets-tender-scout.onrender.com
```

Open it in your browser. You should see the dashboard.

**Note**: on the free tier, Render spins down your server after 15 minutes of no visitors. The first visit after a spin-down takes about 30 seconds to load. This is normal.

---

## STEP 5: Test the Daily Scan

The GitHub Actions cron job runs automatically at 05:47 UTC every morning. But you can test it right now:

1. Go to your GitHub repo page
2. Click the "Actions" tab
3. Click "Daily Tender Scan" in the left menu
4. Click "Run workflow" > "Run workflow" (green button)
5. Wait 1 to 2 minutes
6. The workflow should show a green checkmark
7. Refresh your dashboard. Tenders should appear.

If you see a red X, click on the failed run to see what went wrong.

---

## STEP 6: Seed Demo Data (optional)

If the portal scan finds no tenders (e.g., portal is down), you can load demo data:

1. Go to your Render dashboard
2. Click on your `nets-tender-scout` service
3. Click "Shell" tab (top right)
4. Type: `python scripts/seed_data.py --demo`
5. Refresh your dashboard

---

## That's It. Here's What Runs Automatically:

| What | Where | When | Cost |
|---|---|---|---|
| Tender scraping | GitHub Actions | 05:47 UTC, Mon-Sat | Free |
| Dashboard + API | Render.com | Always on (spins up on visit) | Free |
| Database | Supabase | Always on | Free (500MB) |
| AI proposals | Anthropic API | When you trigger one | ~$0.50 each |

---

## Your URLs

| What | URL |
|---|---|
| Dashboard | `https://nets-tender-scout.onrender.com` |
| API docs | `https://nets-tender-scout.onrender.com/docs` |
| Health check | `https://nets-tender-scout.onrender.com/api/health` |
| Trigger scan | `https://nets-tender-scout.onrender.com/api/scan/trigger` |
| GitHub repo | `https://github.com/YOUR-USERNAME/nets-tender-scout` |
| Supabase DB | `https://supabase.com/dashboard` |

---

## How to Share with the Presales Team

Send them the Render URL. That's it. They open it in any browser, on any device. No install needed.

Example: "Open https://nets-tender-scout.onrender.com in your browser. Tenders update automatically every morning."

---

## Troubleshooting

### Dashboard shows no tenders
Run the GitHub Action manually (Step 5) or seed demo data (Step 6).

### Render shows "Build failed"
Check the build logs. Most common issue: a Python package failed to install. Make sure `requirements.txt` is in the root of the repo.

### GitHub Action shows red X
Click on the failed run. Check the logs. Most common issue: `DATABASE_URL` secret is not set or has a typo.

### "Connection refused" from Supabase
Check that your connection string has the correct password and the `[YOUR-PASSWORD]` placeholder is replaced.

### Proposals tab is empty
Proposals require ANTHROPIC_API_KEY. Set it in Render's environment variables. Then trigger a proposal from the dashboard.

---

## Monthly Cost Summary

| Service | Monthly cost |
|---|---|
| GitHub (code + Actions) | $0 |
| Supabase (database) | $0 (free tier) |
| Render (server) | $0 (free tier) |
| Anthropic API | $0 if no proposals; ~$5 for 10 proposals |
| **Total (scraping + dashboard only)** | **$0** |
| **Total (with AI proposals)** | **~$5/month** |
