# 🚀 Quick Deployment Guide

## Prerequisites
- ✅ GitHub account with repository pushed
- ✅ Render account (free tier)
- ✅ Telegram bot token from @BotFather
- ✅ Google Drive API key
- ✅ Google Drive folder ID

## 3-Step Deployment

### Step 1: Push to GitHub
```bash
git add .
git commit -m "Ready for deployment"
git push origin main
```

### Step 2: Deploy on Render
1. Go to https://dashboard.render.com
2. Click **"New"** → **"Blueprint"**
3. Connect your GitHub repository
4. Select the repository with this bot
5. Click **"Apply"** (Render auto-detects `render.yaml`)

### Step 3: Set Environment Variables
In Render dashboard, go to your worker service → Environment:

**Required:**
```
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
GOOGLE_DRIVE_API_KEY=AIzaSyA...
GOOGLE_DRIVE_FOLDER_ID=1a2B3c4D...
```

**Optional:**
```
ADMIN_USER_ID=123456789
```

**Auto-set by Render (don't touch):**
```
DATABASE_URL=postgresql://...
```

## Verify Deployment

### Check Logs
Render dashboard → Your Service → Logs

Look for:
```
✓ Connected to PostgreSQL database
✓ Database schema initialized successfully
✓ Notification service started
✓ Bot started successfully!
```

### Test Bot
Open Telegram, find your bot, send:
```
/start
/help
/subscribe
/stats
```

### Test Persistence
1. `/subscribe` in Telegram
2. Go to Render dashboard
3. Click "Manual Deploy" → "Clear build cache & deploy"
4. Wait for redeploy
5. Check `/stats` - subscription should still exist ✓

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Bot doesn't respond | Check BOT_TOKEN is correct |
| "Drive API error" | Verify GOOGLE_DRIVE_API_KEY |
| "Folder not found" | Check GOOGLE_DRIVE_FOLDER_ID |
| Database errors | Ensure DATABASE_URL is linked |
| Worker keeps stopping | Normal on free tier (restarts on message) |

## Free Tier Limits

- **Database**: 256 MB (sufficient for 50,000+ users)
- **Worker**: Sleeps after 15 min inactivity (auto-wakes on message)
- **Bandwidth**: 100 GB/month outbound
- **Build minutes**: 500 minutes/month

## Upgrade Path

Need 24/7 operation?
- Upgrade worker to Starter plan ($7/month)
- Database can stay free tier
- Bot will never sleep

## Files You Might Want to Customize

- `bot/utils/constants.py` - Bot messages and emojis
- `database/schema.sql` - Database schema (if adding features)
- `render.yaml` - Service configuration
- `bot/main.py` - Add new commands here

## Support Commands

```python
/start      - Start bot, register user
/help       - Show available commands
/browse     - Browse Google Drive folders
/search     - Search files
/subscribe  - Subscribe to notifications
/unsubscribe - Unsubscribe from notifications
/stats      - Your personal statistics
/admin_stats - Bot-wide statistics (admin only)
```

## Monitoring

- **User Count**: `/admin_stats` command
- **Database Size**: Render dashboard → Database → Metrics
- **Error Logs**: Render dashboard → Service → Logs
- **Uptime**: Render dashboard → Service → Events

## Security Checklist

- ✅ `.env` file in `.gitignore` (never commit secrets)
- ✅ Environment variables in Render (not in code)
- ✅ Google Drive folder is public/accessible
- ✅ Bot token kept secret
- ✅ Admin user ID set (optional but recommended)

---

**Deployment Time**: ~5-10 minutes  
**Status**: Ready to deploy  
**Cost**: $0 (free tier)

**Need help?** Check:
1. `DEPLOYMENT.md` - Detailed guide
2. `MIGRATION_COMPLETE.md` - Technical details
3. Render logs - Error messages
4. Render community forum - render.com/community
