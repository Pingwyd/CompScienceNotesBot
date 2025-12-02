"""
Notification Service - Handles periodic checking and user notifications
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class NotificationService:
    """Service to manage file notifications and periodic checking"""
    
    def __init__(self, drive_service, database=None):
        """
        Initialize the notification service
        
        Args:
            drive_service: DriveService instance for fetching files
            database: Database instance for storing file states and user preferences
        """
        self.drive_service = drive_service
        self.database = database
        
        # In-memory fallback if no database
        self.last_check_time = None
        self.known_files = {}  # {file_id: file_info}
        self.subscribed_users = []  # List of user_ids (in-memory fallback)
        self.is_initialized = False  # Track if we've scanned the drive yet
    
    def initialize_file_state(self):
        """
        Initialize the known files state from Google Drive
        Should be called when bot starts or on first check
        """
        if self.is_initialized:
            logger.info("File state already initialized, skipping...")
            return True
            
        try:
            logger.info("Initializing file state from Google Drive...")
            all_files = self._get_all_files_recursive()
            
            # Store all current files as "known"
            for file in all_files:
                file_info = {
                    'name': file['name'],
                    'modified_time': file.get('modifiedTime'),
                    'size': file.get('size'),
                    'path': file.get('path', ''),
                    'is_folder': self.drive_service.is_folder(file)
                }
                self.known_files[file['id']] = file_info
                
                # Store in database if available
                if self.database:
                    self.database.add_file(
                        file_id=file['id'],
                        name=file['name'],
                        file_type=file.get('mimeType'),
                        size_bytes=int(file.get('size', 0)) if file.get('size') else None,
                        modified_time=file.get('modifiedTime'),
                        download_url=file.get('webViewLink'),
                        is_folder=file_info['is_folder'],
                        path=file_info['path']
                    )
            
            self.last_check_time = datetime.now()
            self.is_initialized = True
            logger.info(f"✓ Initialized with {len(self.known_files)} files")
            
            return True
        except Exception as e:
            logger.error(f"Failed to initialize file state: {e}")
            return False
    
    def _get_all_files_recursive(self, folder_id=None, path="", depth=0, max_depth=10):
        """
        Recursively get all files from Drive with their paths
        
        Args:
            folder_id: Folder to start from (None = root)
            path: Current path breadcrumb
            depth: Current recursion depth (for logging)
            max_depth: Maximum recursion depth to prevent infinite loops
            
        Returns:
            List of all files with path information
        """
        all_files = []
        
        if depth > max_depth:
            logger.warning(f"Max depth {max_depth} reached at path: {path}")
            return all_files
        
        try:
            if depth == 0:
                logger.info(f"Scanning root folder...")
            elif depth <= 2:  # Only log first 2 levels to reduce noise
                logger.info(f"  {'  ' * depth}Scanning: {path}")
                
            files = self.drive_service.list_files(folder_id, page_size=1000, use_cache=True)
            
            for file in files:
                # Add path to file info
                file['path'] = path
                all_files.append(file)
                
                # If it's a folder, recurse into it
                if self.drive_service.is_folder(file):
                    new_path = f"{path}/{file['name']}" if path else file['name']
                    subfolder_files = self._get_all_files_recursive(
                        file['id'], new_path, depth + 1, max_depth
                    )
                    all_files.extend(subfolder_files)
            
            if depth == 0:
                logger.info(f"✓ Scan complete! Found {len(all_files)} total items")
                
            return all_files
        except Exception as e:
            logger.error(f"Error getting files recursively at {path}: {e}")
            return all_files
    
    def check_for_new_files(self) -> List[Dict]:
        """
        Check Drive for new files since last check
        
        Returns:
            List of new files found
        """
        # Initialize on first check if needed
        if not self.is_initialized:
            logger.info("First check - initializing file state...")
            self.initialize_file_state()
            # On first initialization, no files are "new"
            return []
            
        try:
            logger.info("Checking for new files...")
            current_files = self._get_all_files_recursive()
            new_files = []
            
            # Create a set of known file IDs for quick lookup
            known_ids = set(self.known_files.keys())
            
            for file in current_files:
                file_id = file['id']
                
                # Check if this is a new file
                if file_id not in known_ids:
                    # It's new!
                    new_files.append({
                        'id': file_id,
                        'name': file['name'],
                        'path': file.get('path', ''),
                        'size': file.get('size'),
                        'modified_time': file.get('modifiedTime'),
                        'is_folder': self.drive_service.is_folder(file)
                    })
                    
                    # Add to known files
                    self.known_files[file_id] = {
                        'name': file['name'],
                        'modified_time': file.get('modifiedTime'),
                        'size': file.get('size'),
                        'path': file.get('path', ''),
                        'is_folder': self.drive_service.is_folder(file)
                    }
            
            self.last_check_time = datetime.now()
            logger.info(f"Found {len(new_files)} new files")
            
            return new_files
        except Exception as e:
            logger.error(f"Error checking for new files: {e}")
            return []
    
    def format_notification_message(self, new_files: List[Dict]) -> str:
        """
        Format new files into a notification message
        
        Args:
            new_files: List of new file dictionaries
            
        Returns:
            Formatted message string
        """
        if not new_files:
            return ""
        
        message = "📢 **New Content Added!**\n\n"
        
        # Group by folder path
        files_by_folder = {}
        for file in new_files:
            path = file.get('path', 'Root')
            if path not in files_by_folder:
                files_by_folder[path] = []
            files_by_folder[path].append(file)
        
        # Format each folder group
        for folder_path, files in sorted(files_by_folder.items()):
            if folder_path:
                message += f"📁 **{folder_path}**\n"
            else:
                message += f"📁 **Root Folder**\n"
            
            for file in files:
                if file['is_folder']:
                    message += f"   📁 {file['name']}\n"
                else:
                    # Determine icon
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
                    
                    size_str = ""
                    if file.get('size'):
                        size_str = f" ({self.drive_service.format_file_size(file['size'])})"
                    
                    message += f"   {icon} {file['name']}{size_str}\n"
            
            message += "\n"
        
        message += f"_Total: {len(new_files)} new item(s)_\n\n"
        message += "Use /browse to explore the new content!"
        
        return message
    
    def should_check_now(self, check_interval_hours: int = 48) -> bool:
        """
        Determine if it's time to check for new files
        
        Args:
            check_interval_hours: Hours between checks (default: 48 = 2 days)
            
        Returns:
            True if check is due
        """
        if self.last_check_time is None:
            return True
        
        time_since_check = datetime.now() - self.last_check_time
        return time_since_check >= timedelta(hours=check_interval_hours)
    
    def add_subscriber(self, user_id: int, user_info: dict = None):
        """Add a user to the notification subscription list
        
        Args:
            user_id: Telegram user ID
            user_info: Optional dict with user details (username, first_name, last_name, is_admin)
        """
        # Use database if available, otherwise in-memory
        if self.database:
            # If user_info provided, ensure user exists in database first
            if user_info:
                self.database.add_user(
                    user_id=user_id,
                    username=user_info.get('username'),
                    first_name=user_info.get('first_name'),
                    last_name=user_info.get('last_name'),
                    is_admin=user_info.get('is_admin', False)
                )
            success = self.database.add_subscription(user_id)
            if success:
                logger.info(f"User {user_id} subscribed to notifications (DB)")
            return success
        else:
            if user_id not in self.subscribed_users:
                self.subscribed_users.append(user_id)
                logger.info(f"User {user_id} subscribed to notifications (in-memory)")
                return True
            return False
    
    def remove_subscriber(self, user_id: int):
        """Remove a user from the notification subscription list"""
        # Use database if available, otherwise in-memory
        if self.database:
            success = self.database.remove_subscription(user_id)
            if success:
                logger.info(f"User {user_id} unsubscribed from notifications (DB)")
            return success
        else:
            if user_id in self.subscribed_users:
                self.subscribed_users.remove(user_id)
                logger.info(f"User {user_id} unsubscribed from notifications (in-memory)")
                return True
            return False
    
    def is_subscribed(self, user_id: int) -> bool:
        """Check if a user is subscribed to notifications"""
        if self.database:
            return self.database.is_subscribed(user_id)
        else:
            return user_id in self.subscribed_users
    
    def get_subscribers(self) -> List[int]:
        """Get list of all subscribed user IDs"""
        if self.database:
            return self.database.get_subscribers()
        else:
            return self.subscribed_users.copy()
    
    async def send_notifications_to_users(self, bot_application, new_files: List[Dict]):
        """
        Send notification messages to all subscribed users
        
        Args:
            bot_application: Telegram bot application instance
            new_files: List of new files to notify about
        """
        if not new_files:
            logger.info("No new files to notify about")
            return
        
        message = self.format_notification_message(new_files)
        subscribers = self.get_subscribers()
        
        if not subscribers:
            logger.info("No subscribers to notify")
            return
        
        logger.info(f"Sending notifications to {len(subscribers)} users")
        
        success_count = 0
        fail_count = 0
        
        for user_id in subscribers:
            try:
                await bot_application.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode='Markdown'
                )
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to send notification to user {user_id}: {e}")
                fail_count += 1
        
        logger.info(f"Notifications sent: {success_count} successful, {fail_count} failed")
