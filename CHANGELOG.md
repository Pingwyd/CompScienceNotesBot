# 📋 Changelog

All notable changes to this bot will be documented here.

---

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
