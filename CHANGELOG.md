# 📋 Changelog

All notable changes to this bot will be documented here.

---

## [2.1.0] - 2026-04-29

### 🛠️ Refactor & Fixes
- Centralized `get_drive_service()` accessor to lazily initialize the DriveService and avoid in-function `global` declarations (fixes Render deploy SyntaxError).
- Removed the ephemeral file selection system and consolidated to a persistent, DB-backed queue for multi-file downloads.
- Moved Telegram imports out of inner functions to module-level to avoid local-binding/UnboundLocalError issues.
- Queue-first UX: files show a queue `➕` button and `📋 View Queue` is visible on all browse pages.

### ✨ Improvements
- Back navigation now supports `back|browse` (browse root) and `back|home` (start), with consistent callback handling.
- `stats_command` now supports callback queries and includes a "🏠 Back to Start" button.
- Notifications view includes a "🏠 Back to Start" button and improved callback handling.

### 🐛 Bug Fixes
- Fixed "name 'drive_service_instance' is used prior to global declaration" SyntaxError in `bot/main.py`.
- Fixed inconsistent callback handling that caused some Back/Stats buttons to fail.
- Fixed UnboundLocalError caused by inner imports in callback handlers.


## [2.0.0] - 2026-02-02

### 🎉 Major Features Added
- **File Selection Mode**: Click "☑️ Select Files" to choose multiple files and download as ZIP
  - Toggle checkboxes on individual files
  - Real-time checkbox updates (no page refresh needed)
  - "📦 ZIP Selected (X)" button shows count
  
- **Queue Selection**: Added checkboxes to queue items
  - Select specific items from queue to download as ZIP
  - Toggle selection with instant visual feedback
  
- **Database Backup & Restore** (Admin Only)
  - `/getdb` - Download SQLite database backup
  - `/uploaddb` - Restore database from backup file
  - Automatic backup creation before restore
  - Timestamp-named backup files

### ✨ Improvements
- **Dynamic UI Updates**: Queue buttons (+ → ✓) update immediately when adding files
- **Queue View Everywhere**: Added "📋 View Queue (X)" button to all navigation screens
- **Back Navigation**: Added "⬅️ Back to Browse" button in queue view
- **Better Button Layout**: Optimized text truncation for cleaner display

### 🐛 Bug Fixes
- Fixed failed download count display bug
- Fixed queue button not updating without navigation
- Fixed admin authentication for database commands
- Fixed database path issues in backup/restore
- Fixed import errors in queue command

---

## [1.0.0] - Initial Release

### Features
- Browse Google Drive folders
- Search files across drive
- Download files and folders as ZIP
- Queue system for batch downloads
- Notification system for new files
- Recent downloads tracking
- User statistics
- Support ticket system
- Admin dashboard

---

### How to View Changelog
Use `/changelog` command in the bot to see this list!
