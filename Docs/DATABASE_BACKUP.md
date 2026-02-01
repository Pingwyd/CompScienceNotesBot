# Database Backup & Restore

## Overview
This bot uses SQLite for data storage. On platforms like Render (free tier), the filesystem is **ephemeral**, meaning the database is deleted on every deployment or restart.

## Solution: Manual Backup & Restore
Admin commands allow you to backup and restore the database manually before/after deployments.

---

## Admin Commands

### `/getdb` - Download Database Backup
Downloads the current SQLite database file.

**Usage:**
1. Send `/getdb` in Telegram
2. Bot sends you the database file (named `bot_backup_YYYYMMDD_HHMMSS.db`)
3. Save this file locally

**When to use:**
- Before pushing changes to Git (before deployment)
- Before making major changes
- For regular backups

---

### `/uploaddb` - Restore Database
Uploads and restores a previously backed-up database.

**Usage:**
1. Send `/uploaddb` in Telegram
2. Bot asks you to send the database file
3. Send the `.db` file as a document
4. Bot automatically:
   - Creates a backup of the current database
   - Replaces it with your uploaded file
   - Reloads the database connection

**When to use:**
- After a deployment/restart (to restore data)
- To restore from a backup
- To migrate data between environments

---

## Setup

### 1. Set Your Admin User ID
Get your Telegram user ID by messaging [@userinfobot](https://t.me/userinfobot)

Add to `.env` or Render environment variables:
```env
ADMIN_USER_ID=123456789
```

### 2. Test the Commands
```
/getdb    # Download current database
/uploaddb # Test restore process
```

---

## Deployment Workflow

### Before Deployment:
1. `/getdb` - Download database backup
2. Save the file locally
3. `git push` your changes

### After Deployment:
1. Wait for Render to finish deploying
2. `/uploaddb` - Restore the database
3. Send the backup file you saved
4. ✅ Data restored!

---

## Automatic Backups (Future Enhancement)
For fully automated backups, consider:
- **Option A:** Render Persistent Disks (~$1/month)
- **Option B:** Auto-upload to Google Drive/S3 on schedule
- **Option C:** Migrate to PostgreSQL (Render free tier available)

---

## Security Notes
- Only admins can use `/getdb` and `/uploaddb`
- Database files contain user data - keep them secure
- The bot creates automatic backups before restoring
- Backup files are named with timestamps for easy identification

---

## Troubleshooting

**"Access denied"**
- Your user ID is not in `ADMIN_USER_IDS`
- Check environment variables in Render dashboard

**"Database file not found"**
- Database hasn't been created yet
- Use the bot first to generate data

**Upload fails**
- Ensure file has `.db` extension
- File size must be under Telegram's limit (50MB)
- Check bot logs for specific errors
