# NETS Tender Scout: Step-by-Step Deployment Guide

This guide assumes you have never deployed a Python application before.
Every step is explained. Nothing is assumed.

---

## What You Need Before Starting

1. **A computer or server** that will run this 24/7 (a Windows PC, a Linux server, or a cloud VM)
2. **Internet access** on that machine (the scraper needs to reach sindhbank.com.pk)
3. **An Anthropic API key** (this is what gives the agents their AI intelligence)

---

## STEP 1: Get an Anthropic API Key

This is the "brain" for Agents 3, 4, and 5. Without it, they cannot write or audit proposals.

1. Go to https://console.anthropic.com/
2. Sign up or log in
3. Click "API Keys" in the left sidebar
4. Click "Create Key"
5. Give it a name like "NETS Tender Scout"
6. Copy the key (it starts with `sk-ant-...`). Save it somewhere safe. You will need it in Step 4.

Cost: approximately $0.50 to $2.00 per proposal generated (each proposal takes 3 to 5 AI calls).

---

## STEP 2: Install Docker (the easiest way to run the app)

Docker packages the entire application into a single container. You do not need to install Python, libraries, or browsers separately.

### On Windows:

1. Go to https://www.docker.com/products/docker-desktop/
2. Download "Docker Desktop for Windows"
3. Run the installer. Accept all defaults.
4. Restart your computer when asked.
5. Open Docker Desktop. Wait until the bottom-left shows "Engine running" (green).

### On Mac:

1. Go to https://www.docker.com/products/docker-desktop/
2. Download "Docker Desktop for Mac"
3. Drag it to Applications. Open it.
4. Wait until the whale icon in the menu bar stops animating.

### On Linux (Ubuntu/Debian):

Open a terminal and paste these commands one at a time:

```
sudo apt update
sudo apt install -y docker.io docker-compose
sudo systemctl start docker
sudo systemctl enable docker
```

To check Docker is working, type:

```
docker --version
```

You should see something like "Docker version 24.0.7". If you see an error, Docker did not install correctly.

---

## STEP 3: Download and Extract the Application

1. Save the file `nets-tender-scout-v3.tar.gz` to your Desktop (or any folder you will remember).

2. Extract it:

   **On Windows:**
   - Right-click the file
   - If you have 7-Zip: "7-Zip > Extract Here"
   - If you have WinRAR: "Extract Here"
   - If neither: download 7-Zip from https://7-zip.org/ and install it first

   **On Mac/Linux (terminal):**
   ```
   cd ~/Desktop
   tar -xzf nets-tender-scout-v3.tar.gz
   ```

3. You should now have a folder called `nets-tender-scout` with these files inside:

   ```
   nets-tender-scout/
     backend/          (the server code)
     frontend/         (the dashboard)
     scripts/          (helper scripts)
     Dockerfile
     docker-compose.yml
     requirements.txt
     README.md
   ```

---

## STEP 4: Set Your API Key

Open the file `docker-compose.yml` inside the `nets-tender-scout` folder with any text editor (Notepad, VS Code, TextEdit).

Find this section:

```yaml
    environment:
      - DATABASE_URL=sqlite:////app/data/tender_scout.db
      - SCAN_HOUR=5
      - SCAN_MINUTE=47
```

Add your API key as a new line right below:

```yaml
    environment:
      - DATABASE_URL=sqlite:////app/data/tender_scout.db
      - SCAN_HOUR=5
      - SCAN_MINUTE=47
      - ANTHROPIC_API_KEY=sk-ant-PASTE-YOUR-KEY-HERE
```

Replace `sk-ant-PASTE-YOUR-KEY-HERE` with the actual key you got in Step 1.

Save the file.

---

## STEP 5: Add Your NETS Logo (Optional)

If you want the NETS logo to appear in the dashboard:

1. Find your NETS logo image file (PNG format works best)
2. Create a folder: `nets-tender-scout/frontend/assets/`
3. Copy your logo into that folder and rename it to `nets-logo.png`

---

## STEP 6: Start the Application

Open a terminal/command prompt.

Navigate to the `nets-tender-scout` folder:

**Windows (Command Prompt):**
```
cd Desktop\nets-tender-scout
```

**Mac/Linux:**
```
cd ~/Desktop/nets-tender-scout
```

Now start the application:

```
docker-compose up -d
```

The first time you run this, Docker will download and build everything. This takes 5 to 10 minutes. You will see lines scrolling. This is normal.

When it finishes, you will see:

```
Creating nets-tender-scout ... done
```

---

## STEP 7: Open the Dashboard

Open your web browser (Chrome, Edge, Firefox) and go to:

```
http://localhost:8000
```

You should see the NETS Tender Scout dashboard.

If the page does not load, wait 30 seconds and try again (the server may still be starting).

---

## STEP 8: Load Your First Data

The dashboard will be empty at first. You have two options:

### Option A: Load demo data (to test immediately)

Open a terminal and run:

```
docker exec nets-tender-scout python scripts/seed_data.py --demo
```

Refresh the dashboard. You should see 10 sample tenders.

### Option B: Wait for the first real scan

The scraper runs automatically at 05:47 UK time every morning (Monday to Saturday). After the first scan, real tenders from Sindh Bank will appear.

### Option C: Trigger a scan right now

Open your browser and go to:

```
http://localhost:8000/api/scan/trigger
```

You will see `{"status": "scan_triggered"}`. Wait 30 to 60 seconds, then refresh the dashboard.

---

## STEP 9: Verify Everything Works

Go to the **Settings / Technical Health** tab in the dashboard. Check:

| What to check | What it should say |
|---|---|
| Portal Connection | sindhbank.com.pk (green tick) |
| Artifact Database | connected (green tick) |
| Last Scan | a date (not "never") |
| Tender Records | a number greater than 0 |

If all of these are green, your system is working.

---

## How to Stop the Application

```
docker-compose down
```

## How to Start It Again

```
docker-compose up -d
```

## How to See What the Application Is Doing

```
docker logs nets-tender-scout --tail 50
```

This shows the last 50 lines of activity.

## How to Update the Application

If you receive a new version:

```
docker-compose down
```

Extract the new tar.gz file over the existing folder (overwrite when asked).

```
docker-compose up -d --build
```

The `--build` flag tells Docker to rebuild with the new code.

---

## If Something Goes Wrong

### "Cannot connect to the Docker daemon"
Docker Desktop is not running. Open it and wait for the green "Engine running" indicator.

### Dashboard shows "Could not reach the server"
The backend is not running. Check: `docker ps`. If nothing is listed, run `docker-compose up -d` again.

### "No API key" warnings in the logs
You did not set ANTHROPIC_API_KEY in docker-compose.yml (Step 4). Agents 1 and 2 will still work (scraping and scoring), but Agents 3, 4, and 5 cannot generate or audit proposals.

### Scan shows 0 tenders
The Sindh Bank portal may be down or have changed its layout. Check if https://sindhbank.com.pk/tenders loads in your browser. If it loads but the scraper finds nothing, the HTML structure may have changed and the scraper needs updating.

---

## What Happens Automatically

Once running, you do not need to touch anything:

| What | When | What it does |
|---|---|---|
| Portal scan | 05:47 UK, Mon-Sat | Scrapes Sindh Bank, scores tenders, saves qualified ones |
| Dashboard refresh | Every 60 seconds | Pulls latest data from the database |
| Proposal generation | When you trigger it | Agent 3 writes, Agent 4 audits tech, Agent 5 audits compliance |

The scraper and dashboard run 24/7 as long as Docker is running on the machine.

---

## Costs

| Item | Cost |
|---|---|
| Docker | Free |
| Anthropic API | ~$0.50 to $2.00 per proposal |
| Server | Free if using an existing PC; $5 to $20/month for a cloud VM |

---

## For the IT Team: Production Deployment

If deploying on a company server behind a reverse proxy:

1. Point your domain (e.g., `tenderscout.nets-international.com`) to the server
2. Set up nginx or IIS to proxy port 8000
3. Enable HTTPS with a certificate (Let's Encrypt is free)
4. For PostgreSQL instead of SQLite, uncomment the postgres section in docker-compose.yml and change DATABASE_URL

The API documentation is at `http://localhost:8000/docs` (auto-generated Swagger UI).
