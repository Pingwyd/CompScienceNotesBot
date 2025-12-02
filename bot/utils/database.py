"""
Database utility module for managing SQLite database operations
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class Database:
    """Database manager for the bot"""
    
    def __init__(self, db_path: str = "bot_data.db"):
        """
        Initialize database connection
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.connection = None
        
    def connect(self):
        """Establish database connection"""
        try:
            self.connection = sqlite3.connect(self.db_path)
            self.connection.row_factory = sqlite3.Row  # Access columns by name
            logger.info(f"Connected to database: {self.db_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            return False
    
    def initialize_schema(self, schema_file: str = "database/schema.sql"):
        """
        Create database tables from schema file
        
        Args:
            schema_file: Path to SQL schema file
        """
        if not self.connection:
            logger.error("No database connection")
            return False
            
        try:
            # Read schema file
            schema_path = Path(schema_file)
            if not schema_path.exists():
                logger.error(f"Schema file not found: {schema_file}")
                return False
            
            with open(schema_path, 'r') as f:
                schema_sql = f.read()
            
            # Execute schema
            cursor = self.connection.cursor()
            cursor.executescript(schema_sql)
            self.connection.commit()
            
            logger.info("Database schema initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize schema: {e}")
            return False
    
    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")
    
    # User operations
    def add_user(self, user_id: int, username: str = None, 
                 first_name: str = None, last_name: str = None,
                 is_admin: bool = False) -> bool:
        """Add or update a user"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO users 
                (user_id, username, first_name, last_name, is_admin)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, username, first_name, last_name, is_admin))
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add user: {e}")
            return False
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user by ID"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get user: {e}")
            return None
    
    def get_all_users(self) -> List[Dict]:
        """Get all users"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT * FROM users")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get users: {e}")
            return []
    
    # Subscription operations
    def add_subscription(self, user_id: int, folder_id: str = None) -> bool:
        """Subscribe user to notifications"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO subscriptions (user_id, folder_id, is_active)
                VALUES (?, ?, TRUE)
            """, (user_id, folder_id))
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add subscription: {e}")
            return False
    
    def remove_subscription(self, user_id: int, folder_id: str = None) -> bool:
        """Unsubscribe user from notifications"""
        try:
            cursor = self.connection.cursor()
            if folder_id is None:
                # Remove all subscriptions for user
                cursor.execute("""
                    UPDATE subscriptions 
                    SET is_active = FALSE 
                    WHERE user_id = ? AND folder_id IS NULL
                """, (user_id,))
            else:
                cursor.execute("""
                    UPDATE subscriptions 
                    SET is_active = FALSE 
                    WHERE user_id = ? AND folder_id = ?
                """, (user_id, folder_id))
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to remove subscription: {e}")
            return False
    
    def is_subscribed(self, user_id: int, folder_id: str = None) -> bool:
        """Check if user is subscribed"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT COUNT(*) as count FROM subscriptions 
                WHERE user_id = ? AND folder_id IS ? AND is_active = TRUE
            """, (user_id, folder_id))
            row = cursor.fetchone()
            return row['count'] > 0 if row else False
        except Exception as e:
            logger.error(f"Failed to check subscription: {e}")
            return False
    
    def get_subscribers(self, folder_id: str = None) -> List[int]:
        """Get all subscribed user IDs"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT DISTINCT user_id FROM subscriptions 
                WHERE is_active = TRUE AND folder_id IS ?
            """, (folder_id,))
            rows = cursor.fetchall()
            return [row['user_id'] for row in rows]
        except Exception as e:
            logger.error(f"Failed to get subscribers: {e}")
            return []
    
    # File operations
    def add_file(self, file_id: str, name: str, parent_folder_id: str = None,
                 file_type: str = None, size_bytes: int = None,
                 modified_time: str = None, download_url: str = None,
                 is_folder: bool = False, path: str = None) -> bool:
        """Add or update a file record"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO files 
                (file_id, name, parent_folder_id, file_type, size_bytes, 
                 modified_time, download_url, is_folder, path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (file_id, name, parent_folder_id, file_type, size_bytes,
                  modified_time, download_url, is_folder, path))
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add file: {e}")
            return False
    
    def get_file(self, file_id: str) -> Optional[Dict]:
        """Get file by ID"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT * FROM files WHERE file_id = ?", (file_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get file: {e}")
            return None
    
    def get_all_file_ids(self) -> List[str]:
        """Get all known file IDs"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT file_id FROM files")
            rows = cursor.fetchall()
            return [row['file_id'] for row in rows]
        except Exception as e:
            logger.error(f"Failed to get file IDs: {e}")
            return []
    
    # Download history
    def log_download(self, user_id: int, file_id: str, download_type: str = 'individual') -> bool:
        """Log a file download"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO downloads (user_id, file_id, download_type)
                VALUES (?, ?, ?)
            """, (user_id, file_id, download_type))
            
            # Update user's total downloads
            cursor.execute("""
                UPDATE users 
                SET total_downloads = total_downloads + 1 
                WHERE user_id = ?
            """, (user_id,))
            
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to log download: {e}")
            return False
    
    def get_user_downloads(self, user_id: int) -> List[Dict]:
        """Get download history for a user"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT d.*, f.name as file_name 
                FROM downloads d
                LEFT JOIN files f ON d.file_id = f.file_id
                WHERE d.user_id = ?
                ORDER BY d.download_date DESC
            """, (user_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get downloads: {e}")
            return []
    
    # Notification log
    def log_notification(self, file_id: str, recipient_count: int) -> bool:
        """Log a notification sent"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO notifications_sent (file_id, recipient_count)
                VALUES (?, ?)
            """, (file_id, recipient_count))
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to log notification: {e}")
            return False
    
    # Statistics
    def get_stats(self) -> Dict[str, Any]:
        """Get bot statistics"""
        try:
            cursor = self.connection.cursor()
            
            # Total users
            cursor.execute("SELECT COUNT(*) as count FROM users")
            total_users = cursor.fetchone()['count']
            
            # Total downloads
            cursor.execute("SELECT COUNT(*) as count FROM downloads")
            total_downloads = cursor.fetchone()['count']
            
            # Total files
            cursor.execute("SELECT COUNT(*) as count FROM files")
            total_files = cursor.fetchone()['count']
            
            # Active subscribers
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id) as count 
                FROM subscriptions WHERE is_active = TRUE
            """)
            active_subscribers = cursor.fetchone()['count']
            
            return {
                'total_users': total_users,
                'total_downloads': total_downloads,
                'total_files': total_files,
                'active_subscribers': active_subscribers
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}
