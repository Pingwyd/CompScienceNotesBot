# Bot Commands Reference

**Last Updated:** December 2, 2025

This document lists all available commands for the Telegram Google Drive Bot.

---

## 📋 User Commands

### Basic Commands

#### `/start`
- **Description:** Start the bot and register as a user
- **Usage:** `/start`
- **Response:** Welcome message with quick start guide

#### `/help`
- **Description:** Display list of available commands
- **Usage:** `/help`
- **Response:** Comprehensive help menu with all commands

#### `/browse`
- **Description:** Browse Google Drive files and folders
- **Usage:** `/browse`
- **Features:**
  - Navigate folders with breadcrumb trail
  - Download files directly
  - Download entire folders as ZIP
  - Pagination for large directories
  - File type icons (PDF, DOC, IMG, VIDEO)
  - **NEW:** ⭐ Add to favorites
  - **NEW:** ➕ Add to queue
  - **NEW:** 🔖 Create folder shortcuts

---

### 🆕 New Features (December 2025)

#### `/recent`
- **Description:** View your recent downloads
- **Usage:** `/recent`
- **Shows:** Last 10 downloaded files with timestamps
- **Actions:**
  - [Download Again] - Re-download the file
  - [⭐ Bookmark] - Add to favorites

#### `/favorites`
- **Description:** View and manage bookmarked files/folders
- **Usage:** `/favorites`
- **Shows:** All your favorited items with paths
- **Actions:**
  - [📂 Open] - Navigate to folder
  - [📥 Download] - Download file
  - [❌ Remove] - Remove from favorites

#### `/queue`
- **Description:** View and manage download queue
- **Usage:** `/queue`
- **Shows:** All queued files with total size
- **Actions:**
  - [📥 Download All] - Batch download all queued files
  - [🗑️ Clear Queue] - Remove all items from queue

#### `/shortcuts`
- **Description:** Quick access to frequently used folders
- **Usage:** `/shortcuts`
- **Shows:** All saved folder shortcuts
- **Actions:**
  - [📂 Open Folder] - Navigate directly to folder
  - [❌ Remove] - Delete shortcut

---

### Statistics & Info

#### `/stats`
- **Description:** View your personal download statistics
- **Usage:** `/stats`
- **Shows:**
  - Total downloads
  - Join date
  - Notification status
  - Recent download history (last 5)

---

## 🔔 Notification Commands

#### `/subscribe`
- **Description:** Enable notifications for new files in Google Drive
- **Usage:** `/subscribe`
- **Response:** Confirmation message, notifications activated

#### `/unsubscribe`
- **Description:** Disable file notifications
- **Usage:** `/unsubscribe`
- **Response:** Confirmation message, notifications deactivated

---

## 👑 Admin Commands

*These commands are only available to authorized administrators*

#### `/admin_stats`
- **Description:** View bot-wide statistics
- **Usage:** `/admin_stats` (admin only)
- **Shows:**
  - Total users
  - Active users (7 days)
  - Total subscribers
  - Total downloads
  - Tracked files count

#### `/dbinfo`
- **Description:** View database connection information
- **Usage:** `/dbinfo` (admin only)
- **Shows:**
  - Database type (PostgreSQL/SQLite)
  - Connection status
  - Database version
  - Total users in database
  - Connection test result

#### `/broadcast <message>`
- **Description:** Send message to all bot users
- **Usage:** `/broadcast Your message here` (admin only)
- **Example:** `/broadcast System maintenance in 1 hour`
- **Response:** Sends message to all users with delivery confirmation

---

## 🎯 Inline Button Actions

These actions are triggered by clicking buttons in the bot interface:

### Browsing Actions
- **📁 Folder Name** - Navigate into folder
- **📄 File Name** - Download file
- **⬅️ Back** - Go to parent folder
- **📦 Download as ZIP** - Download entire folder as ZIP archive
- **⬅️ Previous / Next ➡️** - Navigate through paginated lists

### NEW: Quick Actions (shown next to files/folders)
- **⭐** - Add to favorites (bookmark)
- **➕** - Add to download queue
- **🔖** - Create folder shortcut

### Notification Actions
- **🔔 Subscribe** - Enable notifications
- **🔕 Unsubscribe** - Disable notifications

---

## 📝 Command Examples

### Browsing Files
```
User: /browse
Bot: Shows root folder with files and folders
User: [Clicks "📁 Lecture Notes"]
Bot: Shows files in Lecture Notes folder
User: [Clicks "📄 Chapter1.pdf"]
Bot: Sends Chapter1.pdf file
```

### Using Favorites
```
User: /browse
Bot: Shows files with ⭐ buttons
User: [Clicks ⭐ next to "Important.pdf"]
Bot: "⭐ Added to favorites!"
User: /favorites
Bot: Shows "Important.pdf" with download button
```

### Using Queue
```
User: /browse
User: [Clicks ➕ next to "File1.pdf"]
Bot: "➕ Added to queue!"
User: [Clicks ➕ next to "File2.pdf"]
Bot: "➕ Added to queue!"
User: /queue
Bot: Shows 2 files, total size
User: [Clicks "📥 Download All"]
Bot: Downloads both files in sequence
```

### Using Shortcuts
```
User: /browse → [Opens "CS 101"] → [Clicks 🔖]
Bot: "🔖 Shortcut created!"
User: /shortcuts
Bot: Shows "CS 101" folder
User: [Clicks "📂 Open Folder"]
Bot: Navigates directly to CS 101 folder
```

---

## 🔄 Command Flow

```
/start → /browse → Download Files
         ↓
      /recent → Download Again
         ↓
    /favorites → Quick Access
         ↓
      /queue → Batch Download
         ↓
   /shortcuts → Folder Quick Access
```

---

## 🆘 Getting Help

- Use `/help` anytime to see command list
- Use `/stats` to check your account status
- Check breadcrumb navigation (📍 Home > Folder > Subfolder) to know your location
- Use ⬅️ Back button to navigate up the folder tree

---

## ⚙️ Technical Notes

### File Size Limits
- Telegram bot API limit: 50 MB per file
- ZIP archives: Limited by available memory and processing time
- Large folders may take time to compress

### Supported File Types
The bot supports all file types but displays special icons for:
- 📄 PDF files (.pdf)
- 📝 Word documents (.doc, .docx)
- 🖼️ Images (.jpg, .jpeg, .png)
- 🎥 Videos (.mp4)
- 📎 Other files

### Notifications
- Checks for new files every 30 minutes
- Only notifies subscribed users
- Shows new files added since last check
- Respects Google Drive folder structure

### Database
- User data and preferences are stored persistently
- Download history is tracked
- Favorites, queue, and shortcuts are saved per user
- Statistics are calculated in real-time

---

## 🔐 Privacy & Security

- Only stores necessary user data (user ID, name, preferences)
- Download history is private to each user
- Admin commands are restricted by user ID
- No file content is stored (direct Drive download)
- Database connection is encrypted (PostgreSQL)

---

*This document is automatically updated when new commands are added.*
