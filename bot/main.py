"""
Telegram Google Drive Bot - Main Entry Point
"""

import os
import sys
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

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

logger = logging.getLogger(__name__)

# Admin IDs (load from env)
ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_USER_IDS', '').split(',') if id.strip()]

# Notification service (global variable to be initialized)
notification_service = None
drive_service_instance = None  # Cache DriveService globally

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
    
    # Initialize database
    db = None
    try:
        from pathlib import Path
        bot_dir = Path(__file__).parent
        if str(bot_dir) not in sys.path:
            sys.path.insert(0, str(bot_dir))
        
        from utils.database import Database
        
        # Create database in the project root
        db_path = Path(__file__).parent.parent / "bot_data.db"
        db = Database(str(db_path))
        
        if db.connect():
            # Initialize schema
            schema_path = Path(__file__).parent.parent / "database" / "schema.sql"
            db.initialize_schema(str(schema_path))
            logger.info("Database initialized successfully")
        else:
            logger.warning("Database connection failed, using in-memory storage")
            db = None
            
    except Exception as e:
        logger.warning(f"Database setup failed: {e}. Using in-memory storage")
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
        help_text = """
📚 **Available Commands:**

/start - Start the bot
/help - Show this help message
/browse - Browse course materials
/search <query> - Search for files
/notifications - Manage notification settings

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
            
            # Create keyboard with buttons
            keyboard = []
            file_list_text = "📁 **Course Materials**\n\n"
            
            for file in files:
                # Check if it's a folder or file
                if drive.is_folder(file):
                    # Add a button for the folder
                    keyboard.append([InlineKeyboardButton(f"📁 {file['name']}", callback_data=f"folder|{file['id']}")])
                else:
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
                    
                    # Add file to text list (we'll add download buttons later)
                    size = f" ({drive.format_file_size(file.get('size'))})"
                    file_list_text += f"{icon} {file['name']}{size}\n"
            
            file_list_text += "\n👇 Click a folder to open it:"
            
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
        
        elif action == "folder":
            folder_id = value
            
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
                
                # List files in the folder
                files = drive.list_files(folder_id)
                
                # Create keyboard
                keyboard = []
                
                # Add "Back" button (we need to know parent ID, but for now let's just go to root if we can't find it)
                # Ideally we should track navigation history, but for simplicity:
                # We'll add a "Back to Root" button for now
                keyboard.append([InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="root|root")])
                
                file_list_text = f"📁 **{folder_name}**\n\n"
                
                if not files:
                    file_list_text += "_(Empty folder)_"
                
                for file in files:
                    if drive.is_folder(file):
                        keyboard.append([InlineKeyboardButton(f"📁 {file['name']}", callback_data=f"folder|{file['id']}")])
                    else:
                        # File icons
                        name = file['name'].lower()
                        if name.endswith('.pdf'): icon = "📄"
                        elif name.endswith(('.doc', '.docx')): icon = "📝"
                        elif name.endswith(('.jpg', '.jpeg', '.png')): icon = "🖼️"
                        elif name.endswith('.mp4'): icon = "🎥"
                        else: icon = "📎"
                        
                        size = f" ({drive.format_file_size(file.get('size'))})"
                        
                        # Add button for file download
                        keyboard.append([InlineKeyboardButton(f"{icon} {file['name']}{size}", callback_data=f"download|{file['id']}")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(file_list_text, reply_markup=reply_markup)
                
            except Exception as e:
                await query.edit_message_text(f"❌ Error loading folder: {str(e)}")
        
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
            
            stats_text = f"📊 **Your Statistics**\n\n"
            stats_text += f"👤 User: {user_data.get('first_name', 'Unknown')}\n"
            stats_text += f"📥 Total Downloads: {user_data.get('total_downloads', 0)}\n"
            stats_text += f"📅 Joined: {user_data.get('joined_date', 'Unknown')[:10]}\n"
            stats_text += f"🔔 Notifications: {'ON' if is_subscribed else 'OFF'}\n"
            
            if downloads:
                stats_text += f"\n**Recent Downloads:**\n"
                for dl in downloads[:5]:
                    file_name = dl.get('file_name', 'Unknown')
                    stats_text += f"  • {file_name}\n"
            
            await update.message.reply_text(stats_text, parse_mode='Markdown')
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
    
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("admin_stats", admin_stats_command))
    application.add_handler(CommandHandler("notifications", notifications_command))
    application.add_handler(CommandHandler("check_now", check_now_command))
    
    # Set up scheduler for periodic checks
    check_interval_hours = int(os.getenv('CHECK_INTERVAL_HOURS', '48'))  # Default: 2 days
    
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        periodic_check_task,
        trigger=IntervalTrigger(hours=check_interval_hours),
        args=[application],
        id='periodic_file_check',
        name='Check for new files periodically',
        replace_existing=True
    )
    scheduler.start()
    
    logger.info(f"Scheduler started! Will check for new files every {check_interval_hours} hours.")
    logger.info("Bot started successfully!")
    
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=True)


if __name__ == '__main__':
    main()
