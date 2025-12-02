# Telegram Google Drive Notes Bot

A Telegram bot that monitors a public Google Drive containing course notes, allows users to browse/search/download files, and sends periodic notifications when new content is added.

## Features

- 📁 **Browse** - Navigate through Drive folders organized by subfolders
- 🔍 **Search** - Find files by name, type, or date
- 📥 **Download** - Get files directly or as ZIP (with user choice)
- 🔔 **Notifications** - Daily digest every 2 days about new files
- 👑 **Admin Tools** - Stats and broadcast announcements

## Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure environment variables (copy `.env.example` to `.env`):
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token
   GOOGLE_DRIVE_LINK=your_public_drive_link
   GOOGLE_API_KEY=your_api_key
   CHECK_INTERVAL_HOURS=48
   ADMIN_USER_IDS=your_telegram_user_id
   ```

3. Run the bot:
   ```bash
   python bot/main.py
   ```

## User Commands

- `/start` - Initialize bot and register user
- `/help` - Show all available commands
- `/browse` - Browse drive folders
- `/search <query>` - Search for files
- `/download` - Download files/folders
- `/notifications` - Manage notification settings
- `/stats` - View personal usage statistics

## Admin Commands

- `/admin_stats` - View bot statistics
- `/admin_broadcast <msg>` - Send announcement to all users
- `/check_now` - Manually trigger file check and send notifications

## Documentation

- [Development Checklist](TASK.md)
- [Technical Structure](BOT_STRUCTURE.md)

## Tech Stack

- **Bot Framework**: python-telegram-bot
- **Cloud Storage**: Google Drive API
- **Database**: SQLite (can be upgraded to PostgreSQL)
- **Scheduler**: APScheduler
- **Language**: Python 3.8+

## License

MIT
