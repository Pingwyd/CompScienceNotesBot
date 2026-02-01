"""
Constants and configuration values
"""

import os

# Admin user IDs (add your Telegram user ID here)
ADMIN_USER_IDS = [
    int(os.getenv('ADMIN_USER_ID', '0'))  # Set ADMIN_USER_ID in environment variables
]

# File size limits (in bytes)
MAX_TELEGRAM_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_ZIP_SIZE = 50 * 1024 * 1024  # 50 MB

# File type mappings
FILE_TYPE_ICONS = {
    'pdf': '📄',
    'doc': '📝',
    'docx': '📝',
    'xls': '📊',
    'xlsx': '📊',
    'ppt': '📊',
    'pptx': '📊',
    'txt': '📃',
    'jpg': '🖼️',
    'jpeg': '🖼️',
    'png': '🖼️',
    'gif': '🖼️',
    'mp4': '🎥',
    'mp3': '🎵',
    'zip': '📦',
    'rar': '📦',
    'folder': '📁',
}

# Bot messages
WELCOME_MESSAGE = """
👋 Welcome to the Course Notes Bot!

I can help you:
📁 Browse course materials
🔍 Search for specific files
📥 Download files and folders
🔔 Get notified about new content

Use /help to see all available commands.
"""

HELP_MESSAGE = """
📚 **Available Commands:**

/start - Start the bot
/help - Show this help message
/browse - Browse drive folders
/search <query> - Search for files
/download - Download files/folders
/notifications - Manage notifications
/stats - View your statistics

Need help? Just ask!
"""
