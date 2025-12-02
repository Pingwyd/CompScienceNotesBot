"""
Telegram Google Drive Bot - Main Entry Point
"""

import os
import sys
import logging
import threading
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from flask import Flask

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

# Admin IDs (load from env)
ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_USER_IDS', '').split(',') if id.strip()]

# Notification service (global variable to be initialized)
notification_service = None
drive_service_instance = None  # Cache DriveService globally

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
        global drive_service_instance
        
        # Use cached DriveService or create new one
        if drive_service_instance is None:
            import sys
            from pathlib import Path
            bot_dir = Path(__file__).parent
            if str(bot_dir) not in sys.path:
                sys.path.insert(0, str(bot_dir))
            from services.drive_service import DriveService
            drive_service_instance = DriveService()
        
        # Run search in executor to avoid blocking
        import asyncio
        loop = asyncio.get_event_loop()
        files = await loop.run_in_executor(None, drive_service_instance.search_files, query)
        
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
            
            if drive_service_instance.is_folder(file):
                # Import InlineKeyboardButton here to avoid circular imports or scope issues if not global
                from telegram import InlineKeyboardButton
                keyboard.append([InlineKeyboardButton(f"📁 {display_name}", callback_data=f"folder|{file['id']}")])
            else:
                from telegram import InlineKeyboardButton
                # File icons
                name = file['name'].lower()
                if name.endswith('.pdf'): icon = "📄"
                elif name.endswith(('.doc', '.docx')): icon = "📝"
                elif name.endswith(('.jpg', '.jpeg', '.png')): icon = "🖼️"
                elif name.endswith('.mp4'): icon = "🎥"
                else: icon = "📎"
                
                size = f" ({drive_service_instance.format_file_size(file.get('size'))})" if file.get('size') else ""
                
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
        
        welcome_text = f"""
👋 Hello {user.first_name}!

Welcome to the Course Notes Bot!

I can help you:
📁 Browse course materials
🔍 Search for files
📥 Download files and folders
🔔 Get notified about new content

Use /help to see all available commands.
        """
        await update.message.reply_text(welcome_text)
    
    async def help_command(update, context):
        """Handle the /help command"""
        user_id = update.effective_user.id
        is_admin = user_id in ADMIN_IDS
        
        help_text = """
📚 **Available Commands:**

/start - Start the bot
/help - Show this help message
/browse - Browse course materials
/search <query> - Search for files
/searchhere <query> - Search in current folder
/recent - View recent downloads
/favorites - Manage your bookmarks
/queue - Manage download queue
/notifications - Manage notification settings
/stats - View your download statistics
"""
        
        if is_admin:
            help_text += """
**Admin Commands:**
/admin_stats - View bot statistics
/check_now - Manually check for new files
/dbinfo - View database connection info
/analytics - Detailed usage analytics
"""
        
        help_text += """
**Notifications:**
Get alerts when new files are added to the drive!
The bot checks every 2 days automatically.

**How to use:**
1. Use /browse to explore folders
2. Click on folders to navigate
3. Click on files to download them
4. Use /notifications to get updates about new content
        """
        await update.message.reply_text(help_text)
    
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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
            # Import the DriveService - using direct import from services folder
            import sys
            from pathlib import Path
            
            # Add bot directory to path
            bot_dir = Path(__file__).parent
            if str(bot_dir) not in sys.path:
                sys.path.insert(0, str(bot_dir))
            
            from services.drive_service import DriveService
            
            # Create drive service
            drive = DriveService()
            
            # Get files from the root folder
            files = drive.list_files()
            
            if not files:
                await message.edit_text("No files found in the drive.")
                return
            
            # Separate folders and files
            folders = [f for f in files if drive.is_folder(f)]
            regular_files = [f for f in files if not drive.is_folder(f)]
            
            # Apply filter if set
            file_filter = context.user_data.get('file_filter', 'all')
            if file_filter != 'all' and regular_files:
                if file_filter == 'pdf':
                    regular_files = [f for f in regular_files if f['name'].lower().endswith('.pdf')]
                elif file_filter == 'doc':
                    regular_files = [f for f in regular_files if f['name'].lower().endswith(('.doc', '.docx'))]
                elif file_filter == 'img':
                    regular_files = [f for f in regular_files if f['name'].lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp'))]
                elif file_filter == 'video':
                    regular_files = [f for f in regular_files if f['name'].lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))]
            
            # Pagination settings
            ITEMS_PER_PAGE = 15
            page = context.user_data.get('current_page', 0)
            
            # Create keyboard with buttons
            keyboard = []
            
            # Breadcrumb navigation (root level)
            file_list_text = "📍 **Home** > Course Materials\n\n"
            
            # Add filter buttons for file types
            if regular_files:
                filter_buttons = [
                    InlineKeyboardButton("📄 PDFs", callback_data="filter|pdf"),
                    InlineKeyboardButton("📝 Docs", callback_data="filter|doc"),
                    InlineKeyboardButton("🖼️ Images", callback_data="filter|img"),
                    InlineKeyboardButton("🎥 Videos", callback_data="filter|video")
                ]
                keyboard.append(filter_buttons)
                filter_buttons2 = [
                    InlineKeyboardButton("📎 All Files", callback_data="filter|all"),
                    InlineKeyboardButton("🔍 Search", callback_data="search|prompt")
                ]
                keyboard.append(filter_buttons2)
                file_list_text += "_Use filters above to narrow results_\n\n"
            
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
                    # Determine icon based on file type
                    name = file['name'].lower()
                    if name.endswith('.pdf'):
                        icon = "📄"
                    elif name.endswith(('.doc', '.docx')):
                        icon = "📝"
                    elif name.endswith(('.jpg', '.jpeg', '.png')):
                        icon = "🖼️"
                    elif name.endswith('.mp4'):
                        icon = "🎥"
                    else:
                        icon = "📎"
                    
                    size = f" ({drive.format_file_size(file.get('size'))})" if file.get('size') else ""
                    keyboard.append([
                        InlineKeyboardButton(
                            f"{icon} {file['name'][:35]}{'...' if len(file['name']) > 35 else ''}",
                            callback_data=f"download|{file['id']}"
                        ),
                        InlineKeyboardButton("ℹ️", callback_data=f"info|{file['id']}"),
                        InlineKeyboardButton("⭐", callback_data=f"fav_add|{file['id']}"),
                        InlineKeyboardButton("➕", callback_data=f"queue_add|{file['id']}")
                    ])
                
                # Add pagination buttons if needed
                if len(regular_files) > ITEMS_PER_PAGE:
                    nav_buttons = []
                    if page > 0:
                        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"page|{page-1}"))
                    file_list_text += f"\n_Page {page + 1}/{(len(regular_files) - 1) // ITEMS_PER_PAGE + 1}_"
                    if end_idx < len(regular_files):
                        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"page|{page+1}"))
                    if nav_buttons:
                        keyboard.append(nav_buttons)
            
            if not folders and not regular_files:
                file_list_text += "_(No items)_"
            else:
                file_list_text += f"\n\n📊 Total: {len(folders)} folders, {len(regular_files)} files"
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.edit_text(file_list_text, reply_markup=reply_markup)
            
        except ValueError as e:
            error_msg = f"❌ **Configuration Error**\n\n{str(e)}\n\nPlease check your .env file."
            await message.edit_text(error_msg)
        except Exception as e:
            error_msg = f"❌ **Error**\n\n{str(e)}\n\n"
            if "500" in str(e) or "Internal Error" in str(e):
                error_msg += "_Google Drive is experiencing issues. Please try again in a few moments._"
            elif "403" in str(e) or "permission" in str(e).lower():
                error_msg += "_Permission denied. Check your Google Drive link is public._"
            await message.edit_text(error_msg)

    async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button clicks"""
        global notification_service
        
        query = update.callback_query
        await query.answer()  # Acknowledge the click
        
        data = query.data
        action, value = data.split('|', 1)
        
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
                # Import DriveService (same as above)
                import sys
                from pathlib import Path
                bot_dir = Path(__file__).parent
                if str(bot_dir) not in sys.path:
                    sys.path.insert(0, str(bot_dir))
                from services.drive_service import DriveService
                
                drive = DriveService()
                
                # Get folder info to show name
                folder_info = drive.get_file_info(folder_id)
                folder_name = folder_info['name'] if folder_info else "Folder"
                
                # Add to navigation history
                context.user_data['nav_history'].append({'id': folder_id, 'name': folder_name})
                
                # List files in the folder
                files = drive.list_files(folder_id)
                
                # Separate folders and files
                folders = [f for f in files if drive.is_folder(f)]
                regular_files = [f for f in files if not drive.is_folder(f)]
                
                # Apply filter if set
                file_filter = context.user_data.get('file_filter', 'all')
                if file_filter != 'all' and regular_files:
                    if file_filter == 'pdf':
                        regular_files = [f for f in regular_files if f['name'].lower().endswith('.pdf')]
                    elif file_filter == 'doc':
                        regular_files = [f for f in regular_files if f['name'].lower().endswith(('.doc', '.docx'))]
                    elif file_filter == 'img':
                        regular_files = [f for f in regular_files if f['name'].lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp'))]
                    elif file_filter == 'video':
                        regular_files = [f for f in regular_files if f['name'].lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))]
                
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
                
                # Add "Back" and "Download Folder as ZIP" buttons
                nav_buttons = []
                if len(context.user_data['nav_history']) > 0:
                    nav_buttons.append(InlineKeyboardButton("⬅️ Back", callback_data="back|back"))
                nav_buttons.append(InlineKeyboardButton("📦 Download as ZIP", callback_data=f"zipfolder|{folder_id}"))
                if nav_buttons:
                    keyboard.append(nav_buttons)
                
                # Add filter buttons if there are files
                if regular_files:
                    filter_buttons = [
                        InlineKeyboardButton("📄 PDFs", callback_data="filter|pdf"),
                        InlineKeyboardButton("📝 Docs", callback_data="filter|doc"),
                        InlineKeyboardButton("🖼️ Images", callback_data="filter|img"),
                        InlineKeyboardButton("🎥 Videos", callback_data="filter|video")
                    ]
                    keyboard.append(filter_buttons)
                    filter_buttons2 = [
                        InlineKeyboardButton("📎 All Files", callback_data="filter|all"),
                        InlineKeyboardButton("🔍 Search", callback_data="search|prompt")
                    ]
                    keyboard.append(filter_buttons2)
                
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
                            # File icons
                            name = file['name'].lower()
                            if name.endswith('.pdf'): icon = "📄"
                            elif name.endswith(('.doc', '.docx')): icon = "📝"
                            elif name.endswith(('.jpg', '.jpeg', '.png')): icon = "🖼️"
                            elif name.endswith('.mp4'): icon = "🎥"
                            else: icon = "📎"
                            
                            size = f" ({drive.format_file_size(file.get('size'))})" if file.get('size') else ""
                            
                            # Add button for file download with action buttons
                            keyboard.append([
                                InlineKeyboardButton(
                                    f"{icon} {file['name'][:35]}{'...' if len(file['name']) > 35 else ''}",
                                    callback_data=f"download|{file['id']}"
                                ),
                                InlineKeyboardButton("ℹ️", callback_data=f"info|{file['id']}"),
                                InlineKeyboardButton("⭐", callback_data=f"fav_add|{file['id']}"),
                                InlineKeyboardButton("➕", callback_data=f"queue_add|{file['id']}")
                            ])
                        
                        # Add pagination buttons if needed
                        if len(regular_files) > ITEMS_PER_PAGE:
                            pag_buttons = []
                            if page > 0:
                                pag_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page|{page-1}"))
                            file_list_text += f"\n_Page {page + 1}/{(len(regular_files) - 1) // ITEMS_PER_PAGE + 1}_"
                            if end_idx < len(regular_files):
                                pag_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"page|{page+1}"))
                            if pag_buttons:
                                keyboard.append(pag_buttons)
                    
                    file_list_text += f"\n\n📊 Total: {len(folders)} folders, {len(regular_files)} files"
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(file_list_text, reply_markup=reply_markup, parse_mode='Markdown')
                
            except Exception as e:
                await query.edit_message_text(f"❌ Error loading folder: {str(e)}")
        
        elif action == "back":
            # Go back in navigation history
            if 'nav_history' in context.user_data and len(context.user_data['nav_history']) > 0:
                context.user_data['nav_history'].pop()  # Remove current folder
                context.user_data['current_page'] = 0  # Reset page
                
                if len(context.user_data['nav_history']) == 0:
                    # Back to root
                    await browse_command(update, context)
                else:
                    # Go to parent folder
                    parent = context.user_data['nav_history'][-1]
                    context.user_data['nav_history'].pop()  # Will be re-added by folder handler
                    
                    # Simulate clicking on parent folder
                    query.data = f"folder|{parent['id']}"
                    await button_click(update, context)
            else:
                await browse_command(update, context)
        
        elif action == "zipfolder":
            folder_id = value
            await query.message.reply_text("📦 Creating ZIP archive... This may take a while for large folders.")
            
            try:
                import sys
                from pathlib import Path
                bot_dir = Path(__file__).parent
                if str(bot_dir) not in sys.path:
                    sys.path.insert(0, str(bot_dir))
                from services.drive_service import DriveService
                import zipfile
                from io import BytesIO
                import os
                
                drive = DriveService()
                folder_info = drive.get_file_info(folder_id)
                folder_name = folder_info['name'] if folder_info else "Folder"
                
                # Get all files recursively
                status_msg = await query.message.reply_text(f"📁 Scanning folder '{folder_name}'...")
                all_files = drive._get_all_files_recursive(folder_id, max_depth=5)
                
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
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for idx, file in enumerate(file_list, 1):
                        try:
                            await status_msg.edit_text(f"📥 {idx}/{len(file_list)}: {file['name'][:30]}...")
                            
                            file_content = drive.download_file(file['id'])
                            if file_content:
                                # Use file path if available, otherwise just name
                                arc_name = file.get('path', file['name'])
                                # Read the content as bytes from BytesIO
                                file_bytes = file_content.getvalue()
                                zip_file.writestr(arc_name, file_bytes)
                        except Exception as e:
                            logger.warning(f"Failed to add {file['name']} to ZIP: {e}")
                
                zip_buffer.seek(0)
                
                await status_msg.edit_text("📤 Uploading ZIP to Telegram...")
                
                # Send ZIP file
                await context.bot.send_document(
                    chat_id=query.message.chat_id,
                    document=zip_buffer,
                    filename=f"{folder_name}.zip",
                    caption=f"📦 {folder_name}.zip\n📊 {len(file_list)} files ({drive.format_file_size(total_size)})"
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
                import sys
                from pathlib import Path
                bot_dir = Path(__file__).parent
                if str(bot_dir) not in sys.path:
                    sys.path.insert(0, str(bot_dir))
                from services.drive_service import DriveService
                
                drive = DriveService()
                file_info = drive.get_file_info(file_id)
                
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
        
        elif action == "fav_remove":
            # Remove from favorites
            file_id = value
            user_id = query.from_user.id
            
            if db and db.remove_favorite(user_id, file_id):
                await query.answer("✅ Removed from favorites")
                # Refresh favorites list
                await favorites_command(update, context)
            else:
                await query.answer("❌ Failed to remove from favorites")
        
        elif action == "queue_add":
            # Add to download queue
            file_id = value
            user_id = query.from_user.id
            
            try:
                import sys
                from pathlib import Path
                bot_dir = Path(__file__).parent
                if str(bot_dir) not in sys.path:
                    sys.path.insert(0, str(bot_dir))
                from services.drive_service import DriveService
                
                drive = DriveService()
                file_info = drive.get_file_info(file_id)
                
                if file_info and db:
                    file_size = int(file_info.get('size', 0))
                    success = db.add_to_queue(user_id, file_id, file_info['name'], file_size)
                    
                    if success:
                        await query.answer("➕ Added to download queue!")
                    else:
                        await query.answer("❌ Failed to add to queue")
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
                # Import DriveService
                import sys
                from pathlib import Path
                bot_dir = Path(__file__).parent
                if str(bot_dir) not in sys.path:
                    sys.path.insert(0, str(bot_dir))
                from services.drive_service import DriveService
                
                drive = DriveService()
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
                result_msg = f"✅ Downloaded {successful}/{len(queue_items)} files"
                if failed > 0:
                    result_msg += f"\n❌ Failed: {failed}"
                await query.message.reply_text(result_msg)
                
            except Exception as e:
                logger.error(f"Error in batch download: {e}")
                await query.message.reply_text("❌ Error during batch download")
        
        elif action == "queue_clear":
            # Clear download queue
            user_id = query.from_user.id
            
            if db and db.clear_queue(user_id):
                await query.answer("🗑️ Queue cleared")
                await queue_command(update, context)
            else:
                await query.answer("❌ Failed to clear queue")
        
        elif action == "shortcut_add":
            # Add folder shortcut
            folder_id = value
            user_id = query.from_user.id
            
            try:
                import sys
                from pathlib import Path
                bot_dir = Path(__file__).parent
                if str(bot_dir) not in sys.path:
                    sys.path.insert(0, str(bot_dir))
                from services.drive_service import DriveService
                
                drive = DriveService()
                folder_info = drive.get_file_info(folder_id)
                
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
        
        elif action == "info":
            # Show file preview/info
            file_id = value
            
            try:
                import sys
                from pathlib import Path
                from datetime import datetime
                bot_dir = Path(__file__).parent
                if str(bot_dir) not in sys.path:
                    sys.path.insert(0, str(bot_dir))
                from services.drive_service import DriveService
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                
                drive = DriveService()
                file_info = drive.get_file_info(file_id)
                
                if not file_info:
                    await query.answer("❌ File not found")
                    return
                
                # Build info message
                info_text = f"ℹ️ **File Information**\n\n"
                info_text += f"**Name:** {file_info['name']}\n"
                
                if file_info.get('size'):
                    size_str = format_file_size(int(file_info['size']))
                    info_text += f"**Size:** {size_str}\n"
                
                if file_info.get('mimeType'):
                    mime = file_info['mimeType']
                    # Simplify mime type
                    if 'pdf' in mime:
                        file_type = "PDF Document"
                    elif 'word' in mime or 'document' in mime:
                        file_type = "Word Document"
                    elif 'image' in mime:
                        file_type = "Image"
                    elif 'video' in mime:
                        file_type = "Video"
                    elif 'text' in mime:
                        file_type = "Text File"
                    else:
                        file_type = mime.split('/')[-1].upper()
                    info_text += f"**Type:** {file_type}\n"
                
                if file_info.get('modifiedTime'):
                    # Parse and format date
                    modified = file_info['modifiedTime']
                    try:
                        dt = datetime.fromisoformat(modified.replace('Z', '+00:00'))
                        date_str = dt.strftime("%B %d, %Y at %I:%M %p")
                        info_text += f"**Modified:** {date_str}\n"
                    except:
                        info_text += f"**Modified:** {modified[:10]}\n"
                
                # Add download button
                keyboard = [
                    [InlineKeyboardButton("📥 Download", callback_data=f"download|{file_id}")],
                    [
                        InlineKeyboardButton("⭐ Favorite", callback_data=f"fav_add|{file_id}"),
                        InlineKeyboardButton("➕ Queue", callback_data=f"queue_add|{file_id}")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.message.reply_text(info_text, reply_markup=reply_markup, parse_mode='Markdown')
                await query.answer()
                
            except Exception as e:
                logger.error(f"Error fetching file info: {e}")
                await query.answer("❌ Error fetching file info")
        
        elif action == "filter":
            # Filter files by type
            filter_type = value
            
            # Store filter in context
            context.user_data['file_filter'] = filter_type
            
            # Re-render current view
            await query.answer(f"🔍 Filtering: {filter_type.upper()}")
            await browse_command(update, context)
        
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
                # Import DriveService
                import sys
                from pathlib import Path
                bot_dir = Path(__file__).parent
                if str(bot_dir) not in sys.path:
                    sys.path.insert(0, str(bot_dir))
                from services.drive_service import DriveService
                
                drive = DriveService()
                file_info = drive.get_file_info(file_id)
                
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
                    
                    file_content = drive.download_file(file_id)
                    
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
    application.add_handler(CommandHandler("browse", browse_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("restart", restart_command))
    application.add_handler(CallbackQueryHandler(button_click))
    
    # Add notification commands
    async def notifications_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /notifications command - manage notification settings"""
        global notification_service
        
        if notification_service is None:
            await update.message.reply_text("❌ Notification service is not available.")
            return
        
        user_id = update.effective_user.id
        is_subscribed = notification_service.is_subscribed(user_id)
        
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        if is_subscribed:
            status_text = "🔔 **Notification Status: ON**\n\nYou will receive notifications when new files are added to the drive (checked every 2 days)."
            button = InlineKeyboardButton("🔕 Turn OFF Notifications", callback_data="notif|unsubscribe")
        else:
            status_text = "🔕 **Notification Status: OFF**\n\nYou won't receive notifications about new files."
            button = InlineKeyboardButton("🔔 Turn ON Notifications", callback_data="notif|subscribe")
        
        keyboard = [[button]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(status_text, reply_markup=reply_markup, parse_mode='Markdown')
    
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
            
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            
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
                        InlineKeyboardButton(f"📥 {idx}. {file_name[:25]}...", callback_data=f"download|{file_id}"),
                        InlineKeyboardButton("⭐", callback_data=f"fav_add|{file_id}")
                    ])
            
            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Error in recent_command: {e}")
            await update.message.reply_text(f"❌ Error fetching recent downloads: {str(e)}")
    
    async def favorites_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /favorites command - show user's bookmarks"""
        user_id = update.effective_user.id
        
        if not db:
            await update.message.reply_text("❌ Database not available.")
            return
        
        try:
            favorites = db.get_favorites(user_id)
            
            # Filter out folders - only show files
            favorites = [f for f in favorites if not f.get('is_folder', False)]
            
            if not favorites:
                await update.message.reply_text("⭐ You haven't bookmarked any files yet.\n\nClick the ⭐ button on any file to bookmark it!")
                return
            
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            
            text = f"⭐ **Your Favorites** ({len(favorites)} files)\n\n"
            keyboard = []
            
            for fav in favorites:
                file_name = fav.get('file_name', 'Unknown')
                file_id = fav.get('file_id')
                file_path = fav.get('file_path', '')
                
                text += f"📄 **{file_name}**\n"
                if file_path:
                    text += f"   {file_path}\n"
                text += "\n"
                
                # Add buttons (files only)
                keyboard.append([
                    InlineKeyboardButton(f"📥 {file_name[:30]}", callback_data=f"download|{file_id}"),
                    InlineKeyboardButton("❌", callback_data=f"fav_remove|{file_id}")
                ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in favorites_command: {e}")
            await update.message.reply_text(f"❌ Error fetching favorites: {str(e)}")
    
    async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /queue command - show download queue"""
        user_id = update.effective_user.id
        
        if not db:
            await update.message.reply_text("❌ Database not available.")
            return
        
        try:
            queue_items = db.get_queue(user_id)
            
            if not queue_items:
                await update.message.reply_text("📋 Your download queue is empty.\n\nAdd files with the ➕ button while browsing!")
                return
            
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            
            # Calculate total size
            total_size = sum(item.get('file_size', 0) for item in queue_items)
            
            text = f"📋 **Download Queue** ({len(queue_items)} files)\n"
            text += f"📊 Total Size: {format_file_size(total_size)}\n\n"
            
            keyboard = []
            for idx, item in enumerate(queue_items, 1):
                file_name = item.get('file_name', 'Unknown')
                file_size = item.get('file_size', 0)
                text += f"{idx}. {file_name} ({format_file_size(file_size)})\n"
            
            # Add action buttons
            keyboard.append([
                InlineKeyboardButton("📥 Download All", callback_data="queue_download_all"),
                InlineKeyboardButton("🗑️ Clear Queue", callback_data="queue_clear")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in queue_command: {e}")
            await update.message.reply_text(f"❌ Error fetching queue: {str(e)}")
    
    def format_file_size(size_bytes: int) -> str:
        """Format bytes to human readable size"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
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
            import sys
            from pathlib import Path
            bot_dir = Path(__file__).parent
            if str(bot_dir) not in sys.path:
                sys.path.insert(0, str(bot_dir))
            from services.drive_service import DriveService
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            
            drive = DriveService()
            
            # Get current folder ID from navigation history
            current_folder_id = None
            if 'nav_history' in context.user_data and context.user_data['nav_history']:
                current_folder_id = context.user_data['nav_history'][-1]['id']
            
            # List files in current folder (or root if not in a folder)
            files = drive.list_files(current_folder_id)
            
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
                # File icon
                name = file['name'].lower()
                if name.endswith('.pdf'): icon = "📄"
                elif name.endswith(('.doc', '.docx')): icon = "📝"
                elif name.endswith(('.jpg', '.jpeg', '.png')): icon = "🖼️"
                elif name.endswith('.mp4'): icon = "🎥"
                else: icon = "📎"
                
                size = f" ({format_file_size(int(file['size']))})" if file.get('size') else ""
                
                keyboard.append([
                    InlineKeyboardButton(
                        f"{icon} {file['name'][:35]}{'...' if len(file['name']) > 35 else ''}",
                        callback_data=f"download|{file['id']}"
                    ),
                    InlineKeyboardButton("ℹ️", callback_data=f"info|{file['id']}"),
                    InlineKeyboardButton("⭐", callback_data=f"fav_add|{file['id']}"),
                    InlineKeyboardButton("➕", callback_data=f"queue_add|{file['id']}")
                ])
            
            if len(matching_files) > 15:
                text += f"\n_Showing first 15 of {len(matching_files)} results_"
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in searchhere_command: {e}")
            await update.message.reply_text(f"❌ Error searching files: {str(e)}")
    
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("admin_stats", admin_stats_command))
    application.add_handler(CommandHandler("dbinfo", dbinfo_command))
    application.add_handler(CommandHandler("recent", recent_command))
    application.add_handler(CommandHandler("favorites", favorites_command))
    application.add_handler(CommandHandler("queue", queue_command))
    application.add_handler(CommandHandler("searchhere", searchhere_command))
    application.add_handler(CommandHandler("notifications", notifications_command))
    application.add_handler(CommandHandler("check_now", check_now_command))
    
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
