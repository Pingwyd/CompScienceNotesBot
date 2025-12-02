# Manual PostgreSQL Setup on Render

## Step 1: Create PostgreSQL Database

1. Go to https://dashboard.render.com
2. Click **"New +"** → **"PostgreSQL"**
3. Fill in details:
   - **Name**: `telegram-bot-db` (or any name you prefer)
   - **Database**: `telegram_bot`
   - **User**: (auto-generated)
   - **Region**: Oregon (or nearest to you)
   - **PostgreSQL Version**: 16 (latest)
   - **Plan**: **Free** (256 MB)
4. Click **"Create Database"**
5. Wait ~2-3 minutes for provisioning

## Step 2: Get Database Connection String

1. Go to your database in Render dashboard
2. Scroll down to **"Connections"** section
3. Copy the **"Internal Database URL"** (looks like this):
   ```
   postgresql://telegram_bot_user:AbCdEfG123...@dpg-xxxxx.oregon-postgres.render.com/telegram_bot_xxxxx
   ```
4. **Save this URL** - you'll need it in Step 4

## Step 3: Create Worker Service

1. In Render dashboard, click **"New +"** → **"Web Service"**
2. Connect your GitHub repository: **Pingwyd/CompScienceNotesBot**
3. Fill in details:
   - **Name**: `telegram-drive-bot` (or any name)
   - **Region**: Oregon (same as database)
   - **Branch**: `main`
   - **Root Directory**: (leave blank)
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot/main.py`
4. **IMPORTANT**: Change service type from "Web Service" to **"Background Worker"**
   - Scroll down and click "Advanced"
   - Change "Instance Type" to **"Background Worker"**
   - This ensures it runs as a worker, not a web server
5. Click **"Create Web Service"** (it will still say "Web" but will be a worker)

## Step 4: Set Environment Variables

In your worker service → **"Environment"** tab → Add environment variables:

### Required Variables

```bash
TELEGRAM_BOT_TOKEN
```
Value: `8345577725:AAHl0RH1iLKSJVHr-4xe4NCOqVA1uiu3JNQ`

```bash
GOOGLE_API_KEY
```
Value: `AIzaSyC02IuzNaJdnz0owO_TPDn6MJ0XQOwT8ts`

```bash
GOOGLE_DRIVE_LINK
```
Value: `https://drive.google.com/drive/u/0/folders/1N70zjiCxL_rd7SPIcam9_WDuMYwCs26P`

```bash
ADMIN_USER_IDS
```
Value: `1952434924`

```bash
DATABASE_URL
```
Value: **Paste the Internal Database URL from Step 2**
```
postgresql://telegram_bot_user:AbCdEfG123...@dpg-xxxxx.oregon-postgres.render.com/telegram_bot_xxxxx
```

### Optional Variables (already have defaults)

```bash
CHECK_INTERVAL_HOURS
```
Value: `48`

```bash
MAX_ZIP_SIZE_MB
```
Value: `50`

```bash
MAX_FILE_SIZE_MB
```
Value: `50`

## Step 5: Deploy

1. Click **"Save Changes"** (if you added env vars)
2. Click **"Manual Deploy"** → **"Deploy latest commit"**
3. Wait for build to complete (~2-5 minutes)

## Step 6: Verify Deployment

### Check Logs
1. Go to your worker service
2. Click **"Logs"** tab
3. Look for these success messages:
   ```
   Connected to PostgreSQL database
   Database schema initialized successfully
   Notification service started
   Bot started successfully!
   ```

### Test Bot
1. Open Telegram
2. Find your bot
3. Send `/start`
4. Send `/stats`
5. Send `/subscribe`

### Test Persistence
1. In Render dashboard, click **"Manual Deploy"** → **"Clear build cache & deploy"**
2. Wait for redeploy
3. Send `/stats` again - your subscription should still exist ✓

## Alternative: Using Render Blueprint (Automatic)

If you want to avoid manual setup, you can use the `render.yaml` file:

1. Delete the manually created services (if any)
2. Go to Render dashboard
3. Click **"New +"** → **"Blueprint"**
4. Connect GitHub repo
5. Render reads `render.yaml` and creates everything automatically
6. You only set environment variables (no DATABASE_URL needed, it's auto-linked)

## Troubleshooting

### Database Connection Failed
- Check `DATABASE_URL` is the **Internal Database URL** (not External)
- Ensure database is in **same region** as worker
- Verify database status is "Available"

### Bot Not Starting
- Check all required env vars are set
- Look for errors in Logs tab
- Verify `TELEGRAM_BOT_TOKEN` is correct

### Worker Keeps Stopping
- Normal on free tier (sleeps after 15 min inactivity)
- Wakes automatically when you send a message
- Upgrade to paid plan for 24/7 operation

### Database Full
- Free tier: 256 MB limit
- Check usage: Database → Metrics
- Clean old data or upgrade to paid tier

## Environment Variables Summary

| Variable | Where to Get It | Required |
|----------|----------------|----------|
| `TELEGRAM_BOT_TOKEN` | @BotFather in Telegram | ✅ Yes |
| `GOOGLE_API_KEY` | Google Cloud Console | ✅ Yes |
| `GOOGLE_DRIVE_LINK` | Google Drive folder URL | ✅ Yes |
| `ADMIN_USER_IDS` | Your Telegram user ID | ✅ Yes |
| `DATABASE_URL` | Render PostgreSQL dashboard | ✅ Yes |
| `CHECK_INTERVAL_HOURS` | Any number (default: 48) | ❌ Optional |
| `MAX_ZIP_SIZE_MB` | Any number (default: 50) | ❌ Optional |
| `MAX_FILE_SIZE_MB` | Any number (default: 50) | ❌ Optional |

## Your Current Values (from .env)

```bash
TELEGRAM_BOT_TOKEN=8345577725:AAHl0RH1iLKSJVHr-4xe4NCOqVA1uiu3JNQ
GOOGLE_API_KEY=AIzaSyC02IuzNaJdnz0owO_TPDn6MJ0XQOwT8ts
GOOGLE_DRIVE_LINK=https://drive.google.com/drive/u/0/folders/1N70zjiCxL_rd7SPIcam9_WDuMYwCs26P
ADMIN_USER_IDS=1952434924
CHECK_INTERVAL_HOURS=48
MAX_ZIP_SIZE_MB=50
MAX_FILE_SIZE_MB=50
```

**⚠️ IMPORTANT**: 
- Never commit `.env` file to GitHub (it's already in `.gitignore`)
- Copy these values manually into Render dashboard
- Replace `DATABASE_URL` with the PostgreSQL connection string from Render

---

**Estimated Setup Time**: 10-15 minutes
**Cost**: $0 (using free tier)
