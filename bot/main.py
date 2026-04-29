"""
Telegram Google Drive Bot - Main Entry Point
"""

import os
import sys
import logging
import threading
import asyncio
from io import BytesIO
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from flask import Flask
import zipfile

# Setup sys.path once at module level to avoid repeated checks
bot_dir = Path(__file__).parent
if str(bot_dir) not in sys.path:
    sys.path.insert(0, str(bot_dir))

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# Suppress the harmless warning from googleapiclient
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
# Suppress noisy httpx logs (getUpdates)
logging.getLogger('httpx').setLevel(logging.WARNING)
# Suppress Flask logs (only show errors)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

# Import DriveService at module level
from services.drive_service import DriveService

# Admin IDs (load from env)
ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_USER_IDS', '').split(',') if id.strip()]

# Notification service (global variable to be initialized)
notification_service = None
drive_service_instance = None  # Cache DriveService globally

# File type icon mapping for performance
FILE_TYPE_ICONS = {
    '.pdf': '📄',
    '.doc': '📝',
    '.docx': '📝',
    '.jpg': '🖼️',
    '.jpeg': '🖼️',
    '.png': '🖼️',
    '.mp4': '🎥',
}

def get_file_icon(filename: str) -> str:
    """Get icon for file based on extension (optimized lookup)"""
    name_lower = filename.lower()
    for ext, icon in FILE_TYPE_ICONS.items():
        if name_lower.endswith(ext):
            return icon
    return '📎'  # Default icon


def get_drive_service():
    """Accessor for the global DriveService instance with lazy initialization."""
    global drive_service_instance
    if drive_service_instance is None:
        drive_service_instance = DriveService()
    return drive_service_instance

# Flask app for health check endpoint
flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    """Health check endpoint for Render"""
    return {'status': 'ok', 'service': 'telegram-bot'}, 200

@flask_app.route('/health')
def health():
    """Alternative health check endpoint"""
    return {'status': 'healthy'}, 200

def run_flask():
    """Run Flask server in a separate thread"""
    port = int(os.getenv('PORT', 10000))
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /search command"""
    # Check if update.message exists
    if not update.message:
        return
    
    # Get the search query from arguments
    if not context.args:
        await update.message.reply_text("🔍 Please provide a search term.\nExample: `/search math`", parse_mode='Markdown')
        return
        
    query = ' '.join(context.args)
    message = await update.message.reply_text(f"🔍 Searching for '{query}'...", parse_mode='Markdown')
    
    try:
        drive = get_drive_service()
        
        # Run search in executor to avoid blocking
        loop = asyncio.get_event_loop()
        files = await loop.run_in_executor(None, drive.search_files, query)
        
        if not files:
            await message.edit_text(f"❌ No files found matching '{query}'.")
            return
        
        # Create keyboard with buttons
        keyboard = []
        file_list_text = f"🔍 **Search Results for '{query}'**\n\n"
        
        # Limit to top 10 results to avoid hitting limits
        for file in files[:10]:
            # Build display name with path
            file_path = file.get('path', '')
            display_name = f"{file_path}/{file['name']}" if file_path else file['name']
            
            if drive.is_folder(file):
                keyboard.append([InlineKeyboardButton(f"📁 {display_name}", callback_data=f"folder|{file['id']}")])
            else:
                # Use optimized icon detection
                icon = get_file_icon(file['name'])
                size = f" ({drive.format_file_size(file.get('size'))})" if file.get('size') else ""
                
                # Add button for file download
                button_text = f"{icon} {file['name']}{size}"
                if file_path:
                    button_text = f"{icon} {file['name']} · {file_path}"
                
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"download|{file['id']}")])
        
        if len(files) > 10:
            file_list_text += f"_(Showing top 10 of {len(files)} results)_\n\n"
        
        file_list_text += f"Found **{len(files)}** file(s). Click to download or open folder."
        
        from telegram import InlineKeyboardMarkup
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.edit_text(file_list_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        error_msg = f"❌ **Search Error**\n\n"
        if "500" in str(e) or "Internal Error" in str(e):
            error_msg += "_Google Drive is experiencing issues. Please try again in a few moments._"
        elif "403" in str(e) or "permission" in str(e).lower():
            error_msg += "_Permission denied. Check your Google Drive link is public._"
        else:
            error_msg += f"{str(e)}"
        await message.edit_text(error_msg, parse_mode='Markdown')

async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restart the bot (Admin only)"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    await update.message.reply_text("🔄 Restarting bot...")
    
    # Restart the process
    os.execl(sys.executable, sys.executable, *sys.argv)


async def periodic_check_task(application):
    """
    Periodic task to check for new files and notify users
    This runs in the background on a schedule
    """
    global notification_service
    
    if notification_service is None:
        logger.warning("Notification service not initialized, skipping check")
        return
    
    try:
        logger.info("Running periodic file check...")
        
        # Run check in executor to avoid blocking
        import asyncio
        loop = asyncio.get_event_loop()
        new_files = await loop.run_in_executor(
            None, 
            notification_service.check_for_new_files
        )
        
        if new_files:
            logger.info(f"Found {len(new_files)} new files, sending notifications")
            await notification_service.send_notifications_to_users(application, new_files)
        else:
            logger.info("No new files found")
            
    except Exception as e:
        logger.error(f"Error in periodic check task: {e}")


def format_error_message(error: Exception, context: str = None, suggest_support: bool = True) -> str:
    """
    Format error messages with helpful context and suggestions
    
    Args:
        error: The exception that occurred
        context: Optional context about what was being attempted
        suggest_support: Whether to suggest using /support
    
    Returns:
        Formatted error message string
    """
    error_msg = "❌ **Error**\n\n"
    
    # Add context if provided
    if context:
        error_msg += f"**What happened:** {context}\n\n"
    
    # Parse common error types and provide helpful messages
    error_str = str(error).lower()
    
    if "403" in error_str or "forbidden" in error_str:
        error_msg += "**Problem:** Permission denied\n"
        error_msg += "**Solution:** The file or folder may be private. Check sharing settings in Google Drive."
    elif "404" in error_str or "not found" in error_str:
        error_msg += "**Problem:** File or folder not found\n"
        error_msg += "**Solution:** The item may have been moved or deleted. Try refreshing with /browse"
    elif "429" in error_str or "rate limit" in error_str or "quota" in error_str:
        error_msg += "**Problem:** Too many requests\n"
        error_msg += "**Solution:** Please wait a few minutes before trying again."
    elif "timeout" in error_str or "timed out" in error_str:
        error_msg += "**Problem:** Connection timeout\n"
        error_msg += "**Solution:** The request took too long. Try again or choose a smaller file."
    elif "connection" in error_str or "network" in error_str:
        error_msg += "**Problem:** Network connection issue\n"
        error_msg += "**Solution:** Check your internet connection and try again."
    elif "invalid" in error_str or "malformed" in error_str:
        error_msg += "**Problem:** Invalid request\n"
        error_msg += "**Solution:** Something went wrong with the request format. Try again."
    else:
        # Generic error
        error_msg += f"**Details:** {str(error)}\n"
    
    # Add support suggestion
    if suggest_support:
        error_msg += "\n\n💡 **Still having issues?**\n"
        error_msg += f"Report this with: `/support <describe what you were doing>`"
    
    return error_msg


def main():
    """Start the bot."""
    global notification_service
    
    # Get bot token from environment
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables!")
        return
    
    # Create the Application
    application = Application.builder().token(token).build()
    
    # Initialize database - PostgreSQL in production, SQLite for dev/testing
    db = None
    try:
        from pathlib import Path
        bot_dir = Path(__file__).parent
        if str(bot_dir) not in sys.path:
            sys.path.insert(0, str(bot_dir))
        
        from utils.database import Database
        
        # Check if we're in production (Render sets DATABASE_URL)
        database_url = os.getenv('DATABASE_URL')
        
        if database_url:
            # Production: PostgreSQL only
            logger.info("🚀 Production mode: Using PostgreSQL")
            db = Database()  # Will auto-detect DATABASE_URL
            if db.connect():
                schema_path = Path(__file__).parent.parent / "database" / "schema.sql"
                db.initialize_schema(str(schema_path))
                logger.info(f"✅ PostgreSQL connected: {db.db_type}")
            else:
                logger.error("❌ CRITICAL: PostgreSQL connection failed in production!")
                db = None
        else:
            # Development: SQLite
            logger.info("🔧 Development mode: Using SQLite")
            db_path = Path(__file__).parent.parent / "bot_data.db"
            db = Database(str(db_path))
            if db.connect():
                schema_path = Path(__file__).parent.parent / "database" / "schema.sql"
                db.initialize_schema(str(schema_path))
                logger.info(f"✅ SQLite connected: {db.db_path}")
            else:
                logger.error("❌ Database connection failed")
                db = None
            
    except Exception as e:
        logger.error(f"❌ Database setup failed: {e}")
        db = None
    
    # Initialize notification service
    try:
        from pathlib import Path
        bot_dir = Path(__file__).parent
        if str(bot_dir) not in sys.path:
            sys.path.insert(0, str(bot_dir))
        
        from services.drive_service import DriveService
        from services.notification import NotificationService
        
        drive_service = DriveService()
        notification_service = NotificationService(drive_service, database=db)
        
        # Don't initialize file state on startup - too slow!
        # It will initialize on first check or when user subscribes
        logger.info("Notification service created (file state will initialize on first use)")
        
    except Exception as e:
        logger.error(f"Failed to create notification service: {e}")
        notification_service = None
    
    # Add command handlers
    async def start_command(update, context):
        """Handle the /start command"""
        
        user = update.effective_user
        
        # Register user in database and track activity
        if db:
            db.add_user(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                is_admin=user.id in ADMIN_IDS
            )
            db.update_last_active(user.id)
        
        # Check if this is a new user (first time)
        is_new_user = False
        if db:
            user_data = db.get_user(user.id)
            is_new_user = user_data and user_data.get('total_downloads', 0) == 0
        
        welcome_text = f"""
👋 **Welcome {user.first_name}!**

I'm your Course Notes Bot - your gateway to course materials!

🎯 **What I Can Do:**

📁 **Browse** - Navigate through folders and files
🔍 **Search** - Find files quickly across all materials  
📥 **Download** - Get files individually or in batches
📋 **Queue** - Add multiple files for batch download
🔔 **Notifications** - Get alerts for new content
📊 **Track** - View your download history and stats

💡 **Quick Start:**
1️⃣ Use /browse to explore course materials
2️⃣ Click on files to download or ➕ to queue
3️⃣ Use /queue to download all queued files
4️⃣ Enable /notifications for updates

Need help? Use /support to report issues!
"""
        
        # Add quick action buttons
        keyboard = [
            [
                InlineKeyboardButton("📁 Browse Files", callback_data="start_browse"),
                InlineKeyboardButton("📋 My Queue", callback_data="start_queue")
            ],
            [
                InlineKeyboardButton("📚 Help", callback_data="start_help"),
                InlineKeyboardButton("🔔 Notifications", callback_data="start_notif")
            ]
        ]
        
        if is_new_user:
            welcome_text += "\n🌟 **First time here? Click 'Browse Files' to get started!**"
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def help_command(update, context):
        """Handle the /help command"""
        
        user_id = update.effective_user.id
        is_admin = user_id in ADMIN_IDS
        
        help_text = """
📚 **Bot Commands & Features**

**📂 File Browsing:**
/start - Start the bot & main menu
/browse - Browse all course materials
/search <query> - Search all files in drive
/searchhere <query> - Search in current folder

**📥 Downloads:**
/recent - View your recent downloads
/queue - View & manage download queue

**🔔 Notifications:**
/notifications - Check notification status
/notification_on - Turn notifications ON
/notification_off - Turn notifications OFF

**📊 Statistics:**
/stats - View your download stats

**🆘 Support:**
/support <message> - Report issues/get help
/mytickets - View your support tickets
/changelog - View update history & new features
/help - Show this help message
"""
        
        if is_admin:
            help_text += """
**🔑 Admin Commands:**
/admin_stats - Bot usage statistics
/check_now - Manually check for new files
/dbinfo - Database connection info
/tickets - View all open support tickets
/getdb - Download database backup
/uploaddb - Restore database from backup
"""
        
        help_text += """
**💡 Quick Tips:**
• Files show ✓ if already in queue
• Use 🏠 Home button to return to start
• Download entire folders as ZIP
• Enable notifications for new content alerts

**How Notifications Work:**
Bot checks for new files every 2 days automatically.
You'll get a message when new content is added!
        """
        
        # Add quick action keyboard
        keyboard = [
            [
                InlineKeyboardButton("📁 Browse", callback_data="start_browse"),
                InlineKeyboardButton("📋 Queue", callback_data="start_queue")
            ],
            [
                InlineKeyboardButton("📊 Stats", callback_data="start_stats"),
                InlineKeyboardButton("🔔 Notifications", callback_data="start_notif")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Handle both callback queries (button clicks) and direct commands
        if update.callback_query:
            await update.callback_query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    from telegram.ext import CallbackQueryHandler, ContextTypes

    async def browse_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /browse command"""
        # Initialize navigation context
        if 'nav_history' not in context.user_data:
            context.user_data['nav_history'] = []
        if 'current_page' not in context.user_data:
            context.user_data['current_page'] = 0
        
        # Reset to root
        context.user_data['nav_history'] = []
        context.user_data['current_page'] = 0
        
        # Check if this is a callback query (from "Back" button) or a command
        if update.callback_query:
            # It's a button click
            message = update.callback_query.message
            await message.edit_text("📁 Fetching files from Google Drive...")
        else:
            # It's a /browse command
            message = await update.message.reply_text("📁 Fetching files from Google Drive...")
        
        try:
            # Use DriveService accessor
            drive = get_drive_service()

            # Get files from the root folder (run in executor)
            loop = asyncio.get_event_loop()
            files = await loop.run_in_executor(None, drive.list_files)
            
            if not files:
                await message.edit_text("No files found in the drive.")
                return
            
            # Separate folders and files
            folders = [f for f in files if drive.is_folder(f)]
            regular_files = [f for f in files if not drive.is_folder(f)]
            
            # Cache queue items once to avoid N+1 queries
            user_id = update.effective_user.id
            queued_file_ids = set()
            if db:
                queue_items = db.get_queue(user_id)
                queued_file_ids = {item['file_id'] for item in queue_items}
            
            # Pagination settings
            ITEMS_PER_PAGE = 15
            page = context.user_data.get('current_page', 0)
            
            # Create keyboard with buttons
            keyboard = []
            
            # Breadcrumb navigation (root level)
            file_list_text = "📍 **Home** > Course Materials\n\n"
            
            # Add Home/Back button at root level
            keyboard.append([InlineKeyboardButton("🏠 Back to Start", callback_data="back|home")])
            
            # Add folders first (no pagination for folders, usually not many)
            if folders:
                file_list_text += "📁 **Folders:**\n"
                for folder in folders:
                    keyboard.append([
                        InlineKeyboardButton(f"📁 {folder['name']}", callback_data=f"folder|{folder['id']}")
                    ])
                file_list_text += "\n"
            
            # Add files with pagination
            if regular_files:
                file_list_text += "📄 **Files:**\n"
                start_idx = page * ITEMS_PER_PAGE
                end_idx = start_idx + ITEMS_PER_PAGE
                page_files = regular_files[start_idx:end_idx]
                
                for file in page_files:
                    # Use optimized icon detection
                    icon = get_file_icon(file['name'])
                    size = f" ({drive.format_file_size(file.get('size'))})" if file.get('size') else ""
                    
                    # Always show download and queue buttons (use cached set)
                    in_queue = file['id'] in queued_file_ids
                    queue_button = "✓" if in_queue else "+"
                    
                    keyboard.append([
                        InlineKeyboardButton(
                            f"{icon} {file['name'][:45]}{'...' if len(file['name']) > 45 else ''}",
                            callback_data=f"download|{file['id']}"
                        ),
                        InlineKeyboardButton(queue_button, callback_data=f"queue_add|{file['id']}")
                    ])
                
                # Add pagination buttons if needed
                if len(regular_files) > ITEMS_PER_PAGE:
                    nav_buttons = []
                    if page > 0:
                        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"page|{page-1}"))
                    total_pages = (len(regular_files) - 1) // ITEMS_PER_PAGE + 1
                    file_list_text += f"\n_Page {page + 1}/{total_pages}_"
                    if end_idx < len(regular_files):
                        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"page|{page+1}"))
                    if nav_buttons:
                        keyboard.append(nav_buttons)
            
            if not folders and not regular_files:
                file_list_text += "_(No items)_"
            else:
                file_list_text += f"\n\n📊 Total: {len(folders)} folders, {len(regular_files)} files"
            
            # Add View Queue button at the bottom
            if db:
                queue_items = db.get_queue(update.effective_user.id)
                queue_count = len(queue_items)
                queue_text = f"📋 View Queue ({queue_count})" if queue_count > 0 else "📋 View Queue"
                keyboard.append([InlineKeyboardButton(queue_text, callback_data="view_queue")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.edit_text(file_list_text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except ValueError as e:
            error_msg = f"❌ **Configuration Error**\n\n{str(e)}\n\nPlease check your .env file and /support for help."
            await message.edit_text(error_msg)
        except Exception as e:
            error_msg = format_error_message(e, "Browsing course materials", suggest_support=True)
            await message.edit_text(error_msg, parse_mode='Markdown')

    async def refresh_current_view(update: Update, context: ContextTypes.DEFAULT_TYPE, query):
        """Re-render the current view (browse or folder) with current pagination and selection state"""
        try:
            # Check if we're inside a folder
            if 'nav_history' in context.user_data and len(context.user_data['nav_history']) > 0:
                # We're in a folder - re-render it
                current_folder = context.user_data['nav_history'][-1]
                folder_id = current_folder['id']
                
                # Use DriveService accessor
                drive = get_drive_service()
                loop = asyncio.get_event_loop()
                
                # Get current page
                page = context.user_data.get('current_page', 0)
                
                # List files in the folder
                files = await loop.run_in_executor(None, drive.list_files, folder_id)
                
                # Separate folders and files
                folders = [f for f in files if drive.is_folder(f)]
                regular_files = [f for f in files if not drive.is_folder(f)]
                
                # Cache queue items once to avoid N+1 queries
                user_id = query.from_user.id
                queued_file_ids = set()
                if db:
                    queue_items = db.get_queue(user_id)
                    queued_file_ids = {item['file_id'] for item in queue_items}
                
                # Pagination settings
                ITEMS_PER_PAGE = 15
                
                # Create keyboard
                keyboard = []
                
                # Build breadcrumb path
                breadcrumb = "📍 **Home**"
                for nav in context.user_data['nav_history']:
                    breadcrumb += f" > {nav['name']}"
                
                file_list_text = f"{breadcrumb}\n\n"
                
                # Add navigation buttons
                nav_buttons = []
                if len(context.user_data['nav_history']) > 0:
                    nav_buttons.append(InlineKeyboardButton("⬅️ Back", callback_data="back|back"))
                nav_buttons.append(InlineKeyboardButton("🏠 Home", callback_data="back|home"))
                if nav_buttons:
                    keyboard.append(nav_buttons)
                
                # Always show Download as ZIP button
                keyboard.append([InlineKeyboardButton("📦 Download Folder as ZIP", callback_data=f"zipfolder|{folder_id}")])
                
                if not files:
                    file_list_text += "_(Empty folder)_"
                else:
                    # Add folders first
                    if folders:
                        file_list_text += "📁 **Folders:**\n"
                        for folder in folders:
                            keyboard.append([
                                InlineKeyboardButton(f"📁 {folder['name']}", callback_data=f"folder|{folder['id']}")
                            ])
                        file_list_text += "\n"
                    
                    # Add files with pagination
                    if regular_files:
                        file_list_text += "📄 **Files:**\n"
                        start_idx = page * ITEMS_PER_PAGE
                        end_idx = start_idx + ITEMS_PER_PAGE
                        page_files = regular_files[start_idx:end_idx]
                        
                        for file in page_files:
                            # Use optimized icon detection
                            icon = get_file_icon(file['name'])
                            size = f" ({drive.format_file_size(file.get('size'))})" if file.get('size') else ""
                            
                            # Always show download and queue buttons (use cached set)
                            in_queue = file['id'] in queued_file_ids
                            queue_button = "✓" if in_queue else "+"
                            
                            keyboard.append([
                                InlineKeyboardButton(
                                    f"{icon} {file['name'][:45]}{'...' if len(file['name']) > 45 else ''}",
                                    callback_data=f"download|{file['id']}"
                                ),
                                InlineKeyboardButton(queue_button, callback_data=f"queue_add|{file['id']}")
                            ])
                        
                        # Add pagination buttons if needed
                        if len(regular_files) > ITEMS_PER_PAGE:
                            pag_buttons = []
                            if page > 0:
                                pag_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page|{page-1}"))
                            total_pages = (len(regular_files) - 1) // ITEMS_PER_PAGE + 1
                            file_list_text += f"\n_Page {page + 1}/{total_pages}_"
                            if end_idx < len(regular_files):
                                pag_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"page|{page+1}"))
                            if pag_buttons:
                                keyboard.append(pag_buttons)
                    
                    file_list_text += f"\n\n📊 Total: {len(folders)} folders, {len(regular_files)} files"
                
                # Always show View Queue button
                if db:
                    queue_items = db.get_queue(query.from_user.id)
                    queue_count = len(queue_items)
                    queue_text = f"📋 View Queue ({queue_count})" if queue_count > 0 else "📋 View Queue"
                    keyboard.append([InlineKeyboardButton(queue_text, callback_data="view_queue")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(file_list_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                # We're at root level - re-render browse view
                await browse_command(update, context)
        except Exception as e:
            logger.error(f"Error refreshing view: {e}")
            error_msg = format_error_message(e, "Refreshing view", suggest_support=False)
            try:
                await query.edit_message_text(error_msg, parse_mode='Markdown')
            except:
                await query.message.reply_text(error_msg, parse_mode='Markdown')

    async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button clicks"""
        global notification_service, drive_service_instance
        
        query = update.callback_query
        await query.answer()  # Acknowledge the click
        
        data = query.data
        
        # Handle callbacks with and without pipe separator
        if '|' in data:
            action, value = data.split('|', 1)
        else:
            action = data
            value = None
        
        if action == "notif":
            # Notification subscription toggle
            user_id = update.effective_user.id
            
            if value == "subscribe":
                if notification_service:
                    # Ensure user exists before adding subscription
                    user = update.effective_user
                    if db:
                        db.add_user(
                            user_id=user.id,
                            username=user.username,
                            first_name=user.first_name,
                            last_name=user.last_name,
                            is_admin=user.id in ADMIN_IDS
                        )
                    notification_service.add_subscriber(user_id)
                    await query.edit_message_text(
                        "✅ **Notifications Enabled!**\n\n"
                        "You will now receive alerts when new files are added to the drive.\n\n"
                        "Use /notifications to manage your settings.",
                        parse_mode='Markdown'
                    )
                else:
                    await query.edit_message_text("❌ Notification service is not available.")
            
            elif value == "unsubscribe":
                if notification_service:
                    notification_service.remove_subscriber(user_id)
                    await query.edit_message_text(
                        "🔕 **Notifications Disabled**\n\n"
                        "You won't receive alerts about new files.\n\n"
                        "Use /notifications to turn them back on.",
                        parse_mode='Markdown'
                    )
                else:
                    await query.edit_message_text("❌ Notification service is not available.")
        
        elif action == "start_browse":
            # Quick action: Browse files
            await browse_command(update, context)
        
        elif action == "start_queue":
            # Quick action: View queue
            await queue_command(update, context)
        
        elif action == "start_help":
            # Quick action: Show help
            await help_command(update, context)
        
        elif action == "start_notif":
            # Quick action: Notifications menu
            await notifications_command(update, context)
        
        elif action == "start_stats":
            # Quick action: View stats
            await stats_command(update, context)
        
        elif action == "page":
            # Pagination handler
            page_num = int(value)
            context.user_data['current_page'] = page_num
            
            # Re-render current view
            await browse_command(update, context)
        
        elif action == "folder":
            folder_id = value
            
            # Initialize navigation if not exists
            if 'nav_history' not in context.user_data:
                context.user_data['nav_history'] = []
            if 'current_page' not in context.user_data:
                context.user_data['current_page'] = 0
            
            # Reset page when entering folder
            context.user_data['current_page'] = 0
            
            try:
                # Use DriveService accessor
                drive = get_drive_service()
                loop = asyncio.get_event_loop()
                
                # Get folder info to show name (run in executor)
                folder_info = await loop.run_in_executor(None, drive.get_file_info, folder_id)
                folder_name = folder_info['name'] if folder_info else "Folder"
                
                # Add to navigation history
                context.user_data['nav_history'].append({'id': folder_id, 'name': folder_name})
                
                # List files in the folder (run in executor - blocking I/O)
                files = await loop.run_in_executor(None, drive.list_files, folder_id)
                
                # Separate folders and files
                folders = [f for f in files if drive.is_folder(f)]
                regular_files = [f for f in files if not drive.is_folder(f)]
                
                # Cache queue items once to avoid N+1 queries
                user_id = query.from_user.id
                queued_file_ids = set()
                if db:
                    queue_items = db.get_queue(user_id)
                    queued_file_ids = {item['file_id'] for item in queue_items}
                
                # Pagination settings
                ITEMS_PER_PAGE = 15
                page = context.user_data.get('current_page', 0)
                
                # Create keyboard
                keyboard = []
                
                # Build breadcrumb path
                breadcrumb = "📍 **Home**"
                for nav in context.user_data['nav_history']:
                    breadcrumb += f" > {nav['name']}"
                
                file_list_text = f"{breadcrumb}\n\n"
                
                # Add navigation buttons
                nav_buttons = []
                if len(context.user_data['nav_history']) > 0:
                    nav_buttons.append(InlineKeyboardButton("⬅️ Back", callback_data="back|back"))
                nav_buttons.append(InlineKeyboardButton("🏠 Home", callback_data="back|home"))
                if nav_buttons:
                    keyboard.append(nav_buttons)
                
                # Always show Download as ZIP button
                keyboard.append([InlineKeyboardButton("📦 Download Folder as ZIP", callback_data=f"zipfolder|{folder_id}")])
                
                if not files:
                    file_list_text += "_(Empty folder)_"
                else:
                    # Add folders first
                    if folders:
                        file_list_text += "📁 **Folders:**\n"
                        for folder in folders:
                            keyboard.append([
                                InlineKeyboardButton(f"📁 {folder['name']}", callback_data=f"folder|{folder['id']}")
                            ])
                        file_list_text += "\n"
                    
                    # Add files with pagination
                    if regular_files:
                        file_list_text += "📄 **Files:**\n"
                        start_idx = page * ITEMS_PER_PAGE
                        end_idx = start_idx + ITEMS_PER_PAGE
                        page_files = regular_files[start_idx:end_idx]
                        
                        for file in page_files:
                            # Use optimized icon detection
                            icon = get_file_icon(file['name'])
                            size = f" ({drive.format_file_size(file.get('size'))})" if file.get('size') else ""
                            
                            # Always show download and queue buttons (use cached set)
                            in_queue = file['id'] in queued_file_ids
                            queue_button = "✓" if in_queue else "+"
                            
                            # Add button for file download with action buttons
                            keyboard.append([
                                InlineKeyboardButton(
                                    f"{icon} {file['name'][:45]}{'...' if len(file['name']) > 45 else ''}",
                                    callback_data=f"download|{file['id']}"
                                ),
                                InlineKeyboardButton(queue_button, callback_data=f"queue_add|{file['id']}")
                            ])
                        
                        # Add pagination buttons if needed
                        if len(regular_files) > ITEMS_PER_PAGE:
                            pag_buttons = []
                            if page > 0:
                                pag_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page|{page-1}"))
                            total_pages = (len(regular_files) - 1) // ITEMS_PER_PAGE + 1
                            file_list_text += f"\n_Page {page + 1}/{total_pages}_"
                            if end_idx < len(regular_files):
                                pag_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"page|{page+1}"))
                            if pag_buttons:
                                keyboard.append(pag_buttons)
                    
                    file_list_text += f"\n\n📊 Total: {len(folders)} folders, {len(regular_files)} files"
                
                # Always show View Queue button
                if db:
                    queue_items = db.get_queue(query.from_user.id)
                    queue_count = len(queue_items)
                    queue_text = f"📋 View Queue ({queue_count})" if queue_count > 0 else "📋 View Queue"
                    keyboard.append([InlineKeyboardButton(queue_text, callback_data="view_queue")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(file_list_text, reply_markup=reply_markup, parse_mode='Markdown')
                
            except Exception as e:
                error_msg = format_error_message(e, "Loading folder contents", suggest_support=True)
                await query.edit_message_text(error_msg, parse_mode='Markdown')
        
        elif action == "back":
            # Handle different back actions
            try:
                if value == "home":
                    # Go back to start command (main menu)
                    context.user_data['nav_history'] = []  # Clear navigation history
                    context.user_data['current_page'] = 0
                    await start_command(update, context)
                    return
                
                # Go back in navigation history
                if 'nav_history' in context.user_data and len(context.user_data['nav_history']) > 0:
                    context.user_data['nav_history'].pop()  # Remove current folder
                    context.user_data['current_page'] = 0  # Reset page
                    
                    if len(context.user_data['nav_history']) == 0:
                        # Back to root
                        await browse_command(update, context)
                    else:
                        # Go to parent folder - manually navigate instead of simulating click
                        parent = context.user_data['nav_history'][-1]
                        parent_id = parent['id']
                        context.user_data['nav_history'].pop()  # Will be re-added when navigating
                        
                        # Navigate to parent by calling folder logic directly
                        # Re-process as folder navigation
                        drive = get_drive_service()
                        loop = asyncio.get_event_loop()
                        context.user_data['current_page'] = 0
                        context.user_data['nav_history'].append(parent)
                        
                        # List files and render folder view (run in executor)
                        files = await loop.run_in_executor(None, drive.list_files, parent_id)
                        folders = [f for f in files if drive.is_folder(f)]
                        regular_files = [f for f in files if not drive.is_folder(f)]
                        
                        ITEMS_PER_PAGE = 15
                        page = 0
                        keyboard = []
                        breadcrumb = "📍 **Home**"
                        for nav in context.user_data['nav_history']:
                            breadcrumb += f" > {nav['name']}"
                        file_list_text = f"{breadcrumb}\n\n"
                        
                        nav_buttons = []
                        if len(context.user_data['nav_history']) > 0:
                            nav_buttons.append(InlineKeyboardButton("⬅️ Back", callback_data="back|back"))
                        nav_buttons.append(InlineKeyboardButton("📦 Download as ZIP", callback_data=f"zipfolder|{parent_id}"))
                        if nav_buttons:
                            keyboard.append(nav_buttons)
                        
                        if folders:
                            file_list_text += "📁 **Folders:**\n"
                            for folder in folders:
                                keyboard.append([InlineKeyboardButton(f"📁 {folder['name']}", callback_data=f"folder|{folder['id']}")])  
                            file_list_text += "\n"
                        
                        if regular_files:
                            file_list_text += "📄 **Files:**\n"
                            for file in regular_files[:ITEMS_PER_PAGE]:
                                icon = get_file_icon(file['name'])
                                keyboard.append([
                                    InlineKeyboardButton(f"{icon} {file['name'][:35]}{'...' if len(file['name']) > 35 else ''}", callback_data=f"download|{file['id']}"),
                                    InlineKeyboardButton("➕", callback_data=f"queue_add|{file['id']}")
                                ])
                        
                        file_list_text += f"\n\n📊 Total: {len(folders)} folders, {len(regular_files)} files"
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        await query.edit_message_text(file_list_text, reply_markup=reply_markup, parse_mode='Markdown')
                        return
                else:
                    await browse_command(update, context)
            except Exception as e:
                logger.error(f"Error in back handler: {e}")
                error_msg = format_error_message(e, "Going back to browse", suggest_support=False)
                try:
                    await query.edit_message_text(error_msg, parse_mode='Markdown')
                except:
                    # If edit fails, send a new message
                    await query.message.reply_text(error_msg, parse_mode='Markdown')
        
        elif action == "zipfolder":
            folder_id = value
            await query.message.reply_text("📦 Creating ZIP archive... This may take a while for large folders.")
            
            try:
                drive = get_drive_service()

                # Run blocking operations in executor to avoid blocking other users
                loop = asyncio.get_event_loop()
                folder_info = await loop.run_in_executor(None, drive.get_file_info, folder_id)
                folder_name = folder_info['name'] if folder_info else "Folder"
                
                # Get all files recursively (blocking operation - run in executor)
                status_msg = await query.message.reply_text(f"📁 Scanning folder '{folder_name}'...")
                all_files = await loop.run_in_executor(None, drive._get_all_files_recursive, folder_id, "", 0, 5)
                
                # Filter out folders, keep only files
                file_list = [f for f in all_files if not drive.is_folder(f)]
                
                if not file_list:
                    await status_msg.edit_text("❌ No files found in this folder.")
                    return
                
                # Check total size
                total_size = sum(int(f.get('size', 0)) for f in file_list)
                max_size = 50 * 1024 * 1024  # 50MB Telegram limit
                
                if total_size > max_size:
                    await status_msg.edit_text(
                        f"❌ Folder too large for Telegram ({drive.format_file_size(total_size)}).\n\n"
                        f"Maximum size: 50 MB\n"
                        f"Please download files individually or use smaller folders."
                    )
                    return
                
                await status_msg.edit_text(f"📦 Downloading {len(file_list)} files...")
                
                # Create ZIP in memory
                zip_buffer = BytesIO()
                successful_files = 0
                failed_files = 0
                
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for idx, file in enumerate(file_list, 1):
                        try:
                            await status_msg.edit_text(f"📥 {idx}/{len(file_list)}: {file['name'][:30]}...")
                            
                            # Download file in executor (blocking I/O)
                            file_content = await loop.run_in_executor(None, drive.download_file, file['id'])
                            if file_content:
                                # Use file path if available, otherwise just name
                                # Handle cases where path might be None or empty
                                file_path = file.get('path', '')
                                file_name = file['name']
                                
                                # Construct the full archive path with the file name
                                if file_path and isinstance(file_path, str) and file_path.strip():
                                    # Combine path and filename to preserve folder structure
                                    arc_name = f"{file_path}/{file_name}"
                                else:
                                    # No path info, just use filename at root level
                                    arc_name = file_name
                                
                                # Read the content as bytes from BytesIO
                                file_bytes = file_content.read()
                                
                                if file_bytes:  # Only add if we have content
                                    zip_file.writestr(arc_name, file_bytes)
                                    successful_files += 1
                                    logger.info(f"Added to ZIP: {arc_name} ({len(file_bytes)} bytes)")
                                else:
                                    failed_files += 1
                                    logger.warning(f"File {file['name']} has no content")
                            else:
                                failed_files += 1
                                logger.warning(f"Failed to download {file['name']}")
                        except Exception as e:
                            failed_files += 1
                            logger.error(f"Failed to add {file['name']} to ZIP: {e}")
                
                logger.info(f"ZIP creation complete: {successful_files} succeeded, {failed_files} failed")
                
                # Important: Seek to beginning after ZIP is finalized
                zip_buffer.seek(0)
                zip_size = len(zip_buffer.getvalue())
                
                # Verify ZIP has content
                if zip_size < 100:  # Empty or corrupted ZIP
                    await status_msg.edit_text(f"❌ Error: ZIP file is empty or corrupted (size: {zip_size} bytes)")
                    logger.error(f"ZIP creation failed - size only {zip_size} bytes for {len(file_list)} files")
                    return
                
                logger.info(f"Created ZIP: {zip_size} bytes for {successful_files}/{len(file_list)} files")
                await status_msg.edit_text("📤 Uploading ZIP to Telegram...")
                
                # Build caption with success/failure info
                caption = f"📦 {folder_name}.zip\n📊 {successful_files} files ({drive.format_file_size(zip_size)})"
                if failed_files > 0:
                    caption += f"\n⚠️ {failed_files} files failed to download"
                
                # Send ZIP file
                await context.bot.send_document(
                    chat_id=query.message.chat_id,
                    document=zip_buffer,
                    filename=f"{folder_name}.zip",
                    caption=caption
                )
                
                # Log download in database
                if db:
                    # Ensure user exists before logging download
                    user = query.from_user
                    db.add_user(
                        user_id=user.id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        is_admin=user.id in ADMIN_IDS
                    )
                    db.log_download(query.from_user.id, folder_id, 'folder_zip')
                
                await status_msg.delete()
                
            except Exception as e:
                logger.error(f"ZIP creation error: {e}")
                await query.message.reply_text(f"❌ Error creating ZIP: {str(e)}")
        
        elif action == "fav_add":
            # Add to favorites
            file_id = value
            user_id = query.from_user.id
            
            try:
                drive = get_drive_service()
                loop = asyncio.get_event_loop()
                file_info = await loop.run_in_executor(None, drive.get_file_info, file_id)
                
                if file_info and db:
                    is_folder = drive.is_folder(file_info)
                    
                    # Don't allow favoriting folders
                    if is_folder:
                        await query.answer("❌ Cannot favorite folders, only files can be favorited!")
                        return
                    
                    file_path = file_info.get('path', '')
                    
                    success = db.add_favorite(
                        user_id=user_id,
                        file_id=file_id,
                        file_name=file_info['name'],
                        file_path=file_path,
                        is_folder=False
                    )
                    
                    if success:
                        await query.answer("⭐ Added to favorites!")
                    else:
                        await query.answer("⚠️ Already in favorites!")
                else:
                    await query.answer("❌ Failed to add to favorites")
                    
            except Exception as e:
                logger.error(f"Error adding favorite: {e}")
                await query.answer("❌ Error adding to favorites")
        
        elif action == "queue_add":
            # Add to download queue
            file_id = value
            user_id = query.from_user.id
            
            try:
                drive = get_drive_service()
                loop = asyncio.get_event_loop()
                file_info = await loop.run_in_executor(None, drive.get_file_info, file_id)
                
                if file_info and db:
                    file_size = int(file_info.get('size', 0))
                    success = db.add_to_queue(user_id, file_id, file_info['name'], file_size)
                    
                    if success:
                        await query.answer("➕ Added to download queue!")
                        
                        # Update the keyboard to show the checkmark immediately
                        if query.message.reply_markup:
                            new_keyboard = []
                            for row in query.message.reply_markup.inline_keyboard:
                                new_row = []
                                for button in row:
                                    # Find the queue button for this file and update it
                                    if button.callback_data == f"queue_add|{file_id}":
                                        new_row.append(InlineKeyboardButton("✓", callback_data=button.callback_data))
                                    else:
                                        new_row.append(button)
                                new_keyboard.append(new_row)
                            
                            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard))
                    else:
                        await query.answer("⚠️ Already in queue")
                else:
                    await query.answer("❌ File not found")
                    
            except Exception as e:
                logger.error(f"Error adding to queue: {e}")
                await query.answer("❌ Error adding to queue")
        
        elif action == "queue_download_all":
            # Download all items in queue
            user_id = query.from_user.id
            
            if not db:
                await query.answer("❌ Database not available")
                return
            
            queue_items = db.get_queue(user_id)
            if not queue_items:
                await query.answer("📋 Queue is empty")
                return
            
            await query.answer("📥 Starting batch download...")
            await query.message.reply_text(f"📥 Downloading {len(queue_items)} files from queue...")
            
            try:
                # Use global DriveService instance
                drive = get_drive_service()
                successful = 0
                failed = 0
                
                for item in queue_items:
                    try:
                        file_id = item['file_id']
                        file_name = item['file_name']
                        
                        # Download file from Drive
                        file_content = drive.download_file(file_id)
                        
                        if file_content:
                            # Send file to user
                            file_content.seek(0)
                            await query.message.reply_document(
                                document=file_content,
                                filename=file_name,
                                caption=f"✅ {file_name}"
                            )
                            successful += 1
                            
                            # Record download in database
                            if db:
                                db.record_download(user_id, file_id, file_name)
                            
                            # Remove from queue after successful download
                            if 'id' in item:
                                db.remove_from_queue(item['id'])
                        else:
                            failed += 1
                            logger.error(f"Failed to download {file_name}")
                    
                    except Exception as e:
                        failed += 1
                        logger.error(f"Error downloading {item.get('file_name', 'unknown')}: {e}")
                
                # Send completion message
                result_msg = f"📝 ✅ Downloaded {successful}/{len(queue_items)} files"
                if failed > 0:
                    result_msg += f"\n❌ Failed: {failed}"
                await query.message.reply_text(result_msg)
                
            except Exception as e:
                logger.error(f"Error in batch download: {e}")
                await query.message.reply_text("❌ Error during batch download")
        
        elif action == "view_queue":
            # View download queue
            await queue_command(update, context)
        
        elif action == "queue_toggle":
            # Toggle selection of a queue item
            file_id = value
            
            if 'queue_selected' not in context.user_data:
                context.user_data['queue_selected'] = set()
            
            if file_id in context.user_data['queue_selected']:
                context.user_data['queue_selected'].remove(file_id)
            else:
                context.user_data['queue_selected'].add(file_id)
            
            # Refresh the queue view
            await queue_command(update, context)
        
        elif action == "queue_zip_selected":
            # Download selected queue items as ZIP
            user_id = query.from_user.id
            
            if 'queue_selected' not in context.user_data or not context.user_data['queue_selected']:
                await query.answer("⚠️ No items selected")
                return
            
            selected_ids = context.user_data['queue_selected']
            queue_items = db.get_queue(user_id) if db else []
            selected_items = [item for item in queue_items if item['file_id'] in selected_ids]
            
            if not selected_items:
                await query.answer("⚠️ Selected items not found")
                return
            
            await query.answer(f"📦 Creating ZIP with {len(selected_items)} files...")
            await query.message.reply_text(f"📦 Preparing ZIP file with {len(selected_items)} selected files...")
            
            try:
                drive = get_drive_service()
                loop = asyncio.get_event_loop()
                
                # Create ZIP in memory
                zip_buffer = BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for item in selected_items:
                        file_id = item['file_id']
                        file_name = item['file_name']
                        
                        try:
                            file_content = await loop.run_in_executor(None, drive.download_file, file_id)
                            if file_content:
                                zip_file.writestr(file_name, file_content.read())
                                logger.info(f"Added {file_name} to ZIP")
                            else:
                                logger.error(f"Failed to download {file_name}")
                        except Exception as e:
                            logger.error(f"Error adding {file_name} to ZIP: {e}")
                
                zip_buffer.seek(0)
                
                # Send ZIP file
                await query.message.reply_document(
                    document=zip_buffer,
                    filename=f"selected_files_{len(selected_items)}.zip",
                    caption=f"📦 {len(selected_items)} files zipped"
                )
                
                # Clear selection
                context.user_data['queue_selected'] = set()
                
                await query.message.reply_text("✅ Selected files sent!")
                
            except Exception as e:
                logger.error(f"Error creating ZIP: {e}")
                await query.message.reply_text(f"❌ Error creating ZIP: {str(e)}")
        
        elif action == "queue_clear":
            # Clear download queue
            user_id = query.from_user.id
            
            if db and db.clear_queue(user_id):
                await query.answer("🗑️ Queue cleared")
                # Clear selection too
                context.user_data['queue_selected'] = set()
                await queue_command(update, context)
            else:
                await query.answer("❌ Failed to clear queue")
        
        elif action == "shortcut_add":
            # Add folder shortcut
            folder_id = value
            user_id = query.from_user.id
            
            try:
                drive = get_drive_service()
                loop = asyncio.get_event_loop()
                folder_info = await loop.run_in_executor(None, drive.get_file_info, folder_id)
                
                if folder_info and db:
                    folder_path = folder_info.get('path', '')
                    success = db.add_shortcut(
                        user_id=user_id,
                        folder_id=folder_id,
                        folder_name=folder_info['name'],
                        folder_path=folder_path
                    )
                    
                    if success:
                        await query.answer("🔖 Shortcut created!")
                    else:
                        await query.answer("⚠️ Shortcut already exists!")
                else:
                    await query.answer("❌ Failed to create shortcut")
                    
            except Exception as e:
                logger.error(f"Error creating shortcut: {e}")
                await query.answer("❌ Error creating shortcut")
        
        elif action == "search":
            # Initiate search in current folder
            await query.answer("💬 Use /searchhere command")
            await query.message.reply_text(
                "🔍 **Search in Current Folder**\n\n"
                "Use the `/searchhere <query>` command to search for files.\n\n"
                "Example: `/searchhere chapter 5`",
                parse_mode='Markdown'
            )
        
        elif action == "download":
            file_id = value
            await query.message.reply_text("⬇️ Starting download...")
            
            try:
                # Use global DriveService instance
                drive = get_drive_service()
                loop = asyncio.get_event_loop()
                file_info = await loop.run_in_executor(None, drive.get_file_info, file_id)
                
                if not file_info:
                    await query.message.reply_text("❌ File not found!")
                    return

                # Check file size (Telegram limit is 50MB for bots)
                size_bytes = int(file_info.get('size', 0))
                if size_bytes > 50 * 1024 * 1024:
                    # Too big, send link instead
                    link = file_info.get('webViewLink', '')
                    await query.message.reply_text(
                        f"⚠️ File is too large for Telegram (>50MB).\n\n"
                        f"🔗 [Download from Google Drive]({link})",
                        parse_mode='Markdown'
                    )
                else:
                    # Download and send file
                    status_msg = await query.message.reply_text("⬇️ Downloading file from Drive...")
                    
                    # Run download in executor (blocking I/O)
                    file_content = await loop.run_in_executor(None, drive.download_file, file_id)
                    
                    if file_content:
                        await status_msg.edit_text("📤 Uploading to Telegram...")
                        
                        # Send the document
                        await context.bot.send_document(
                            chat_id=query.message.chat_id,
                            document=file_content,
                            filename=file_info['name'],
                            caption=f"📄 {file_info['name']}"
                        )
                        
                        # Log download in database
                        if db:
                            # Ensure user exists before logging download
                            user = query.from_user
                            db.add_user(
                                user_id=user.id,
                                username=user.username,
                                first_name=user.first_name,
                                last_name=user.last_name,
                                is_admin=user.id in ADMIN_IDS
                            )
                            db.log_download(query.from_user.id, file_id, 'individual')
                        
                        await status_msg.delete()
                    else:
                        await status_msg.edit_text("❌ Failed to download file from Drive.")
            except Exception as e:
                await query.message.reply_text(f"❌ Download error: {str(e)}")
        
        elif action == "root":
            # Go back to main menu (re-use browse logic essentially)
            await browse_command(update, context)

    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("h", help_command))
    application.add_handler(CommandHandler("browse", browse_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("restart", restart_command))
    application.add_handler(CallbackQueryHandler(button_click))
    
    # Add notification commands
    async def notifications_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /notifications command - show notification settings with manual toggle buttons"""
        global notification_service
        
        if notification_service is None:
            if update.callback_query:
                await update.callback_query.edit_message_text("❌ Notification service is not available.")
            else:
                await update.message.reply_text("❌ Notification service is not available.")
            return
        
        user_id = update.effective_user.id
        is_subscribed = notification_service.is_subscribed(user_id)
        
        if is_subscribed:
            status_text = "🔔 **Notification Status: ON**\n\nYou will receive notifications when new files are added to the drive (checked every 2 days)."
            button = InlineKeyboardButton("🔕 Turn OFF Notifications", callback_data="notif|unsubscribe")
        else:
            status_text = "🔕 **Notification Status: OFF**\n\nYou won't receive notifications about new files."
            button = InlineKeyboardButton("🔔 Turn ON Notifications", callback_data="notif|subscribe")
        
        keyboard = [[button], [InlineKeyboardButton("🏠 Back to Start", callback_data="back|home")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Handle both callback queries (button clicks) and direct commands
        if update.callback_query:
            await update.callback_query.edit_message_text(status_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(status_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def notification_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /notification_on command - enable notifications"""
        global notification_service
        
        if notification_service is None:
            await update.message.reply_text("❌ Notification service is not available.")
            return
        
        user_id = update.effective_user.id
        user = update.effective_user
        
        # Ensure user exists in database
        if db:
            db.add_user(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                is_admin=user.id in ADMIN_IDS
            )
        
        # Add subscriber
        notification_service.add_subscriber(user_id)
        
        await update.message.reply_text(
            "✅ **Notifications Turned ON**\n\n"
            "🔔 You will now receive alerts when new files are added to the drive.\n"
            "🕒 The bot checks every 2 days automatically.\n\n"
            "Use /notification_off to disable\n"
            "Use /notifications to check status",
            parse_mode='Markdown'
        )
    
    async def notification_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /notification_off command - disable notifications"""
        global notification_service
        
        if notification_service is None:
            await update.message.reply_text("❌ Notification service is not available.")
            return
        
        user_id = update.effective_user.id
        
        # Remove subscriber
        notification_service.remove_subscriber(user_id)
        
        await update.message.reply_text(
            "🔕 **Notifications Turned OFF**\n\n"
            "❌ You won't receive alerts about new files anymore.\n\n"
            "Use /notification_on to re-enable\n"
            "Use /notifications to check status",
            parse_mode='Markdown'
        )
    
    async def check_now_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /check_now command - manually trigger a check (Admin only)"""
        global notification_service
        
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("⛔ You are not authorized to use this command.")
            return
        
        if notification_service is None:
            await update.message.reply_text("❌ Notification service is not available.")
            return
        
        message = await update.message.reply_text("🔍 Checking for new files...")
        
        try:
            # Run check in executor to avoid blocking
            import asyncio
            loop = asyncio.get_event_loop()
            new_files = await loop.run_in_executor(
                None,
                notification_service.check_for_new_files
            )
            
            if new_files:
                await message.edit_text(f"✅ Found {len(new_files)} new files! Sending notifications...")
                await notification_service.send_notifications_to_users(application, new_files)
                await update.message.reply_text(f"📤 Notifications sent to {len(notification_service.get_subscribers())} users.")
            else:
                await message.edit_text("✅ Check complete. No new files found.")
        except Exception as e:
            await message.edit_text(f"❌ Error during check: {str(e)}")
    
    async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /stats command - show user statistics"""
        user_id = update.effective_user.id
        
        # Track activity
        if db:
            db.update_last_active(user_id)
        
        if not db:
            await update.message.reply_text("❌ Database not available.")
            return
        
        try:
            user_data = db.get_user(user_id)
            downloads = db.get_user_downloads(user_id)
            is_subscribed = notification_service.is_subscribed(user_id) if notification_service else False
            
            # Use HTML to avoid Markdown parsing issues
            stats_text = "📊 <b>Your Statistics</b>\n\n"
            stats_text += f"👤 User: {user_data.get('first_name', 'Unknown')}\n"
            stats_text += f"📥 Total Downloads: {user_data.get('total_downloads', 0)}\n"
            
            # Format joined_date properly
            joined_date = user_data.get('joined_date', 'Unknown')
            if joined_date != 'Unknown':
                joined_date = str(joined_date)[:10] if joined_date else 'Unknown'
            stats_text += f"📅 Joined: {joined_date}\n"
            stats_text += f"🔔 Notifications: {'ON' if is_subscribed else 'OFF'}\n"
            
            if downloads:
                stats_text += f"\n<b>Recent Downloads:</b>\n"
                for dl in downloads[:5]:
                    file_name = dl.get('file_name', 'Unknown')
                    # Escape HTML special characters
                    file_name = file_name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    stats_text += f"  • {file_name}\n"
            
            await update.message.reply_text(stats_text, parse_mode='HTML')
        except Exception as e:
            await update.message.reply_text(f"❌ Error fetching stats: {str(e)}")
    
    async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /admin_stats command - show bot statistics (Admin only)"""
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("⛔ You are not authorized to use this command.")
            return
        
        if not db:
            await update.message.reply_text("❌ Database not available.")
            return
        
        try:
            stats = db.get_stats()
            active_7d = db.get_active_users_count(7)
            
            stats_text = f"📊 **Bot Statistics**\n\n"
            stats_text += f"👥 Total Users: {stats.get('total_users', 0)}\n"
            stats_text += f"✅ Active (7 days): {active_7d}\n"
            stats_text += f"🔔 Subscribed: {stats.get('active_subscribers', 0)}\n"
            stats_text += f"📥 Total Downloads: {stats.get('total_downloads', 0)}\n"
            stats_text += f"📁 Tracked Files: {stats.get('total_files', 0)}\n"
            
            await update.message.reply_text(stats_text, parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"❌ Error fetching stats: {str(e)}")
    
    async def dbinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /dbinfo command - show database connection info (Admin only)"""
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("⛔ You are not authorized to use this command.")
            return
        
        if not db:
            await update.message.reply_text("❌ Database not available.")
            return
        
        try:
            info_text = "🗄️ <b>Database Information</b>\n\n"
            info_text += f"<b>Type:</b> {db.db_type.upper()}\n"
            info_text += f"<b>Connected:</b> {'✅ Yes' if db.connection else '❌ No'}\n"
            
            if db.db_type == 'postgresql':
                # Get PostgreSQL version
                cursor = db.connection.cursor()
                cursor.execute("SELECT version();")
                version = cursor.fetchone()
                pg_version = version['version'].split(',')[0] if version else 'Unknown'
                info_text += f"<b>Version:</b> {pg_version}\n"
                
                # Get database name
                cursor.execute("SELECT current_database();")
                dbname = cursor.fetchone()
                info_text += f"<b>Database:</b> {dbname['current_database'] if dbname else 'Unknown'}\n"
                
                # Test a simple query
                cursor.execute("SELECT COUNT(*) as count FROM users")
                user_count = cursor.fetchone()['count']
                info_text += f"\n<b>Connection Test:</b> ✅ Success\n"
                info_text += f"<b>Users in DB:</b> {user_count}\n"
            else:
                info_text += f"<b>Path:</b> {db.db_path}\n"
            
            await update.message.reply_text(info_text, parse_mode='HTML')
        except Exception as e:
            await update.message.reply_text(f"❌ Database Error:\n{str(e)}")
    
    async def recent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /recent command - show recent downloads"""
        user_id = update.effective_user.id
        
        if not db:
            await update.message.reply_text("❌ Database not available.")
            return
        
        try:
            downloads = db.get_user_downloads(user_id)
            
            if not downloads:
                await update.message.reply_text("📥 You haven't downloaded any files yet.\n\nUse /browse to explore files!")
                return
            
            # Show last 10 downloads - use HTML to avoid parsing issues
            text = "📥 <b>Recent Downloads</b>\n\n"
            keyboard = []
            
            for idx, dl in enumerate(downloads[:10], 1):
                file_name = dl.get('file_name', 'Unknown')
                file_id = dl.get('file_id')
                download_date = dl.get('download_date', '')
                
                # Escape HTML special characters in filename - ensure string type
                file_name_escaped = str(file_name).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                
                # Format date
                if download_date:
                    from datetime import datetime
                    try:
                        if isinstance(download_date, str):
                            dt = datetime.fromisoformat(download_date.replace('Z', '+00:00'))
                        else:
                            dt = download_date
                        
                        # Relative time
                        diff = datetime.now() - dt.replace(tzinfo=None)
                        if diff.days == 0:
                            time_str = "Today"
                        elif diff.days == 1:
                            time_str = "Yesterday"
                        else:
                            time_str = dt.strftime("%b %d")
                    except:
                        time_str = str(download_date)[:10]
                else:
                    time_str = "Unknown"
                
                text += f"{idx}. <b>{file_name_escaped}</b>\n   Downloaded: {time_str}\n\n"
                
                # Add button
                if file_id:
                    keyboard.append([
                        InlineKeyboardButton(f"📥 {idx}. {file_name[:25]}...", callback_data=f"download|{file_id}")
                    ])
            
            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Error in recent_command: {e}")
            await update.message.reply_text(f"❌ Error fetching recent downloads: {str(e)}")
    
    async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /queue command - show download queue"""
        
        user_id = update.effective_user.id
        
        if not db:
            message_text = "❌ Database not available."
            if update.callback_query:
                await update.callback_query.edit_message_text(message_text)
            else:
                await update.message.reply_text(message_text)
            return
        
        try:
            queue_items = db.get_queue(user_id)
            
            if not queue_items:
                message_text = "📋 Your download queue is empty.\n\nAdd files with the ➕ button while browsing!"
                keyboard = [[InlineKeyboardButton("⬅️ Back to Browse", callback_data="back|home")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                if update.callback_query:
                    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
                else:
                    await update.message.reply_text(message_text, reply_markup=reply_markup)
                return
            
            # Calculate total size
            total_size = sum(item.get('file_size', 0) for item in queue_items)
            
            # Get selected items from user data
            if 'queue_selected' not in context.user_data:
                context.user_data['queue_selected'] = set()
            selected = context.user_data['queue_selected']
            
            # Use HTML instead of Markdown to avoid parsing issues
            text = f"📋 <b>Download Queue</b> ({len(queue_items)} files)\n"
            text += f"📊 Total Size: {format_file_size(total_size)}\n\n"
            
            keyboard = []
            for idx, item in enumerate(queue_items, 1):
                file_name = item.get('file_name', 'Unknown')
                file_size = item.get('file_size', 0)
                file_id = item.get('file_id', '')
                
                # Check if this item is selected
                is_selected = file_id in selected
                checkbox = "☑️" if is_selected else "☐"
                
                # Add text
                text += f"{idx}. {file_name} ({format_file_size(file_size)})\n"
                
                # Add button with checkbox
                keyboard.append([
                    InlineKeyboardButton(
                        f"{checkbox} {file_name[:45]}{'...' if len(file_name) > 45 else ''}",
                        callback_data=f"queue_toggle|{file_id}"
                    )
                ])
            
            # Add action buttons
            action_row = [
                InlineKeyboardButton("📥 Download All", callback_data="queue_download_all"),
            ]
            if len(selected) > 0:
                action_row.append(InlineKeyboardButton(f"📦 ZIP Selected ({len(selected)})", callback_data="queue_zip_selected"))
            
            keyboard.append(action_row)
            keyboard.append([InlineKeyboardButton("🗑️ Clear Queue", callback_data="queue_clear")])
            
            # Add back button
            keyboard.append([InlineKeyboardButton("⬅️ Back to Browse", callback_data="back|home")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
            else:
                await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Error in queue_command: {e}")
            error_text = f"❌ Error fetching queue: {str(e)}"
            if update.callback_query:
                await update.callback_query.edit_message_text(error_text)
            else:
                await update.message.reply_text(error_text)
    
    def format_file_size(size_bytes: int) -> str:
        """Format bytes to human readable size"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    async def getdb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin command to download the SQLite database"""
        user_id = update.effective_user.id
        
        # Check if user is admin
        from utils.constants import ADMIN_USER_IDS
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text("❌ Access denied. This command is only for admins.")
            return
        
        try:
            # Get database path (same as in setup_database)
            from pathlib import Path
            db_path = Path(__file__).parent.parent / 'bot_data.db'
            
            if not db_path.exists():
                await update.message.reply_text("❌ Database file not found.")
                return
            
            # Send database file
            await update.message.reply_text("📦 Preparing database backup...")
            
            with open(db_path, 'rb') as db_file:
                await update.message.reply_document(
                    document=db_file,
                    filename=f"bot_backup_{update.message.date.strftime('%Y%m%d_%H%M%S')}.db",
                    caption="📊 SQLite Database Backup\n\nUse /uploaddb to restore this backup."
                )
            
            await update.message.reply_text("✅ Database backup sent successfully!")
            logger.info(f"Database downloaded by admin user {user_id}")
            
        except Exception as e:
            logger.error(f"Error in getdb_command: {e}")
            await update.message.reply_text(f"❌ Error creating backup: {str(e)}")
    
    async def uploaddb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin command to upload and restore the SQLite database"""
        user_id = update.effective_user.id
        
        # Check if user is admin
        from utils.constants import ADMIN_USER_IDS
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text("❌ Access denied. This command is only for admins.")
            return
        
        await update.message.reply_text(
            "📤 **Database Restore**\n\n"
            "Please send me the database file (.db) as a document.\n\n"
            "⚠️ Warning: This will replace the current database!",
            parse_mode='Markdown'
        )
    
    async def handle_database_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle database file upload from admin"""
        global db  # Declare global at the start
        user_id = update.effective_user.id
        
        # Check if user is admin
        from utils.constants import ADMIN_USER_IDS
        if user_id not in ADMIN_USER_IDS:
            return
        
        # Check if message has a document
        if not update.message.document:
            return
        
        document = update.message.document
        
        # Check if it's a .db file
        if not document.file_name.endswith('.db'):
            return
        
        try:
            await update.message.reply_text("📥 Downloading database file...")
            
            # Download the file
            file = await context.bot.get_file(document.file_id)
            
            from pathlib import Path
            import shutil
            
            # Create backup of current database (same as in setup_database)
            db_path = Path(__file__).parent.parent / 'bot_data.db'
            backup_path = db_path.parent / f'bot_data_backup_{update.message.date.strftime("%Y%m%d_%H%M%S")}.db'
            
            if db_path.exists():
                shutil.copy2(db_path, backup_path)
                await update.message.reply_text(f"💾 Current database backed up to: {backup_path.name}")
            
            # Download new database
            temp_path = db_path.parent / 'temp_upload.db'
            await file.download_to_drive(temp_path)
            
            # Close existing database connections
            global db
            if db:
                try:
                    db.close()
                except:
                    pass
            
            # Replace the database
            shutil.move(temp_path, db_path)
            
            # Reinitialize database
            from utils.database import Database
            db = Database(str(db_path))
            if db.connect():
                schema_path = Path(__file__).parent.parent / "database" / "schema.sql"
                db.initialize_schema(str(schema_path))
            
            await update.message.reply_text(
                "✅ Database restored successfully!\n\n"
                f"📊 Backup saved as: {backup_path.name}\n"
                "🔄 Database reloaded and ready to use.",
                parse_mode='Markdown'
            )
            
            logger.info(f"Database restored by admin user {user_id}")
            
        except Exception as e:
            logger.error(f"Error restoring database: {e}")
            await update.message.reply_text(f"❌ Error restoring database: {str(e)}")
    
    async def changelog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /changelog command - show bot update history"""
        try:
            from pathlib import Path
            changelog_path = Path(__file__).parent.parent / "CHANGELOG.md"
            
            if not changelog_path.exists():
                await update.message.reply_text("📋 No changelog available.")
                return
            
            with open(changelog_path, 'r', encoding='utf-8') as f:
                changelog_text = f.read()
            
            # Split into chunks if too long (Telegram has 4096 char limit)
            max_length = 4000
            if len(changelog_text) > max_length:
                # Send in chunks
                chunks = []
                current_chunk = ""
                for line in changelog_text.split('\n'):
                    if len(current_chunk) + len(line) + 1 > max_length:
                        chunks.append(current_chunk)
                        current_chunk = line + '\n'
                    else:
                        current_chunk += line + '\n'
                if current_chunk:
                    chunks.append(current_chunk)
                
                for i, chunk in enumerate(chunks):
                    await update.message.reply_text(chunk, parse_mode='Markdown')
            else:
                await update.message.reply_text(changelog_text, parse_mode='Markdown')
        
        except Exception as e:
            logger.error(f"Error in changelog_command: {e}")
            await update.message.reply_text(f"❌ Error loading changelog: {str(e)}")
    
    async def searchhere_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /searchhere command - search files in current folder"""
        user_id = update.effective_user.id
        
        # Check if there's a search query
        if not context.args:
            await update.message.reply_text(
                "🔍 **Search in Current Folder**\n\n"
                "Usage: `/searchhere <query>`\n\n"
                "Example: `/searchhere chapter 5`\n\n"
                "This will search for files matching 'chapter 5' in your current location.",
                parse_mode='Markdown'
            )
            return
        
        search_query = ' '.join(context.args).lower()
        
        try:
            drive = get_drive_service()
            loop = asyncio.get_event_loop()
            
            # Get current folder ID from navigation history
            current_folder_id = None
            if 'nav_history' in context.user_data and context.user_data['nav_history']:
                current_folder_id = context.user_data['nav_history'][-1]['id']
            
            # List files in current folder (or root if not in a folder) - run in executor
            files = await loop.run_in_executor(None, drive.list_files, current_folder_id)
            
            # Search for matching files (case-insensitive)
            matching_files = [
                f for f in files 
                if search_query in f['name'].lower() and not drive.is_folder(f)
            ]
            
            if not matching_files:
                location = context.user_data['nav_history'][-1]['name'] if 'nav_history' in context.user_data and context.user_data['nav_history'] else "Home"
                await update.message.reply_text(
                    f"🔍 No files found matching **'{search_query}'** in {location}",
                    parse_mode='Markdown'
                )
                return
            
            # Build results message
            location = context.user_data['nav_history'][-1]['name'] if 'nav_history' in context.user_data and context.user_data['nav_history'] else "Home"
            text = f"🔍 **Search Results** ({len(matching_files)})\n\n"
            text += f"Query: **{search_query}**\n"
            text += f"Location: {location}\n\n"
            
            keyboard = []
            for file in matching_files[:15]:  # Limit to 15 results
                # File icon using helper function
                icon = get_file_icon(file['name'])
                size = f" ({format_file_size(int(file['size']))})" if file.get('size') else ""
                
                keyboard.append([
                    InlineKeyboardButton(
                        f"{icon} {file['name'][:35]}{'...' if len(file['name']) > 35 else ''}",
                        callback_data=f"download|{file['id']}"
                    ),
                    InlineKeyboardButton("➕", callback_data=f"queue_add|{file['id']}")
                ])
            
            if len(matching_files) > 15:
                text += f"\n_Showing first 15 of {len(matching_files)} results_"
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in searchhere_command: {e}")
            await update.message.reply_text(f"❌ Error searching files: {str(e)}")
    
    async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /support command - report issues or get help"""
        user_id = update.effective_user.id
        
        # Track activity
        if db:
            db.update_last_active(user_id)
        
        # Check if user is providing a message or just asking for info
        if not context.args:
            help_text = """
🆘 **Support & Error Reporting**

To report an issue or error, use:
`/support <your message>`

**Example:**
`/support The download button isn't working for PDF files`

**What to include:**
• What you were trying to do
• What error message you saw (if any)
• Which file/folder you were accessing

Your message will be sent to the admin for review.

You can also check your previous support tickets with:
`/mytickets`
"""
            await update.message.reply_text(help_text, parse_mode='Markdown')
            return
        
        # User is submitting a support ticket
        message = ' '.join(context.args)
        username = update.effective_user.username or f"{update.effective_user.first_name}"
        
        if not db:
            await update.message.reply_text("❌ Support system is currently unavailable. Please try again later.")
            return
        
        try:
            success = db.create_support_ticket(user_id, username, message)
            
            if success:
                # Notify admins
                admin_notification = f"""
🆘 **New Support Ticket**

👤 User: @{username} (ID: {user_id})
📝 Message: {message}

Use /tickets to view all open tickets.
"""
                for admin_id in ADMIN_IDS:
                    try:
                        await application.bot.send_message(chat_id=admin_id, text=admin_notification, parse_mode='Markdown')
                    except Exception:
                        pass  # Admin might have blocked the bot
                
                await update.message.reply_text(
                    "✅ **Support ticket created!**\n\n"
                    "Your message has been sent to the admin team. "
                    "We'll review it and get back to you as soon as possible.\n\n"
                    "Use `/mytickets` to view your submitted tickets.",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("❌ Failed to create support ticket. Please try again.")
        except Exception as e:
            logger.error(f"Error creating support ticket: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def mytickets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /mytickets command - view user's support tickets"""
        user_id = update.effective_user.id
        
        if not db:
            await update.message.reply_text("❌ Database not available.")
            return
        
        try:
            tickets = db.get_user_tickets(user_id)
            
            if not tickets:
                await update.message.reply_text("📭 You haven't submitted any support tickets yet.")
                return
            
            # Build ticket list
            text = "🎫 **Your Support Tickets**\n\n"
            
            for ticket in tickets:
                status_emoji = {
                    'open': '🟢',
                    'in_progress': '🟡',
                    'resolved': '✅',
                    'closed': '⚫'
                }.get(ticket['status'], '❓')
                
                text += f"{status_emoji} **Ticket #{ticket['id']}** - {ticket['status'].title()}\n"
                text += f"📅 Created: {ticket['created_date'][:16]}\n"
                text += f"📝 Message: {ticket['message'][:100]}{'...' if len(ticket['message']) > 100 else ''}\n"
                
                if ticket.get('admin_notes'):
                    text += f"💬 Admin: {ticket['admin_notes']}\n"
                
                text += "\n"
            
            await update.message.reply_text(text, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error retrieving tickets: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def tickets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /tickets command - view all open tickets (Admin only)"""
        user_id = update.effective_user.id
        
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("⛔ You are not authorized to use this command.")
            return
        
        if not db:
            await update.message.reply_text("❌ Database not available.")
            return
        
        try:
            tickets = db.get_all_open_tickets()
            
            if not tickets:
                await update.message.reply_text("✅ No open support tickets!")
                return
            
            text = f"🎫 **Open Support Tickets** ({len(tickets)})\n\n"
            
            for ticket in tickets[:20]:  # Limit to 20 most recent
                status_emoji = {'open': '🟢', 'in_progress': '🟡'}.get(ticket['status'], '❓')
                
                text += f"{status_emoji} **Ticket #{ticket['id']}**\n"
                text += f"👤 User: @{ticket['username']} (ID: {ticket['user_id']})\n"
                text += f"📅 {ticket['created_date'][:16]}\n"
                text += f"📝 {ticket['message']}\n"
                
                if ticket.get('error_context'):
                    text += f"⚠️ Context: {ticket['error_context'][:100]}\n"
                
                text += "\n"
            
            if len(tickets) > 20:
                text += f"\n_Showing 20 of {len(tickets)} tickets_"
            
            await update.message.reply_text(text, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error retrieving all tickets: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("admin_stats", admin_stats_command))
    application.add_handler(CommandHandler("dbinfo", dbinfo_command))
    application.add_handler(CommandHandler("recent", recent_command))
    application.add_handler(CommandHandler("queue", queue_command))
    application.add_handler(CommandHandler("searchhere", searchhere_command))
    application.add_handler(CommandHandler("changelog", changelog_command))
    application.add_handler(CommandHandler("notifications", notifications_command))
    application.add_handler(CommandHandler("notification_on", notification_on_command))
    application.add_handler(CommandHandler("notification_off", notification_off_command))
    application.add_handler(CommandHandler("check_now", check_now_command))
    application.add_handler(CommandHandler("support", support_command))
    application.add_handler(CommandHandler("mytickets", mytickets_command))
    application.add_handler(CommandHandler("tickets", tickets_command))
    
    # Admin commands for database backup/restore
    application.add_handler(CommandHandler("getdb", getdb_command))
    application.add_handler(CommandHandler("uploaddb", uploaddb_command))
    
    # Add handler for document uploads (for database restore)
    from telegram.ext import MessageHandler, filters
    application.add_handler(MessageHandler(filters.Document.ALL, handle_database_upload))
    
    # Set up scheduler for periodic checks
    check_interval_hours = int(os.getenv('CHECK_INTERVAL_HOURS', '48'))  # Default: 2 days
    
    scheduler = AsyncIOScheduler()
    
    # Add periodic file check
    scheduler.add_job(
        periodic_check_task,
        trigger=IntervalTrigger(hours=check_interval_hours),
        args=[application],
        id='periodic_file_check',
        name='Check for new files periodically',
        replace_existing=True
    )
    
    # Add keep-alive ping for Render (prevent service from sleeping)
    async def keep_alive_ping():
        """Ping own health endpoint to prevent Render from sleeping"""
        try:
            import aiohttp
            port = os.getenv('PORT', '10000')
            url = f"http://localhost:{port}/health"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        logger.debug("Keep-alive ping successful")
        except Exception as e:
            logger.debug(f"Keep-alive ping failed: {e}")
    
    # Ping every 14 minutes to stay active on Render free tier
    scheduler.add_job(
        keep_alive_ping,
        trigger=IntervalTrigger(minutes=5),
        id='keep_alive',
        name='Keep service active on Render',
        replace_existing=True
    )
    
    scheduler.start()
    
    logger.info(f"Scheduler started! Will check for new files every {check_interval_hours} hours.")
    logger.info("Bot started successfully!")
    
    # Start Flask server in a separate thread for Render health checks
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info(f"Health check server started on port {os.getenv('PORT', 10000)}")
    
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=True)


if __name__ == '__main__':
    main()
