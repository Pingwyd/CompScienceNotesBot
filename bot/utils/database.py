"""
Database utility module for managing database operations
Supports both SQLite (local) and PostgreSQL (production)
"""

import sqlite3
import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class Database:
    """Database manager for the bot - supports SQLite and PostgreSQL"""
    
    def __init__(self, db_path: str = "bot_data.db"):
        """
        Initialize database connection
        
        Args:
            db_path: Path to SQLite database file (ignored if using PostgreSQL)
        """
        self.db_path = db_path
        self.connection = None
        self.db_type = None  # 'sqlite' or 'postgresql'
        
        # Check if PostgreSQL URL is provided
        self.database_url = os.getenv('DATABASE_URL')
        
        # Auto-connect on initialization
        self.connect()
    
    def connect(self):
        """Establish database connection (SQLite or PostgreSQL)"""
        try:
            if self.database_url:
                # Use PostgreSQL
                import psycopg2
                from psycopg2.extras import RealDictCursor
                
                # Fix for Render PostgreSQL URLs (postgres:// -> postgresql://)
                db_url = self.database_url
                if db_url.startswith('postgres://'):
                    db_url = db_url.replace('postgres://', 'postgresql://', 1)
                
                self.connection = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
                self.connection.autocommit = True  # Enable autocommit to avoid transaction errors
                self.db_type = 'postgresql'
                logger.info(f"Connected to PostgreSQL database")
            else:
                # Use SQLite
                self.connection = sqlite3.connect(self.db_path)
                self.connection.row_factory = sqlite3.Row
                self.db_type = 'sqlite'
                logger.info(f"Connected to SQLite database: {self.db_path}")
            
            # Ensure migrations
            try:
                self._ensure_last_active_column()
            except Exception as e:
                logger.warning(f"Migration warning: {e}")
                
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
            
            # Adjust schema for PostgreSQL if needed
            if self.db_type == 'postgresql':
                schema_sql = self._convert_schema_to_postgresql(schema_sql)
            
            # Execute schema
            # Temporarily disable autocommit for PostgreSQL to execute multiple statements
            original_autocommit = None
            if self.db_type == 'postgresql':
                original_autocommit = self.connection.autocommit
                self.connection.autocommit = False
            
            cursor = self.connection.cursor()
            
            if self.db_type == 'postgresql':
                # PostgreSQL doesn't support executescript
                statements = [s.strip() for s in schema_sql.split(';') if s.strip()]
                for statement in statements:
                    if statement:  # Skip empty statements
                        cursor.execute(statement)
                self.connection.commit()
                # Restore autocommit
                self.connection.autocommit = original_autocommit
            else:
                cursor.executescript(schema_sql)
                self.connection.commit()
                
            logger.info("Database schema initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize schema: {e}")
            if self.db_type == 'postgresql' and original_autocommit is not None:
                self.connection.rollback()
                self.connection.autocommit = original_autocommit
            return False
    
    def _convert_schema_to_postgresql(self, schema_sql: str) -> str:
        """Convert SQLite schema to PostgreSQL compatible schema"""
        # Replace SQLite specific syntax
        schema_sql = schema_sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
        schema_sql = schema_sql.replace('AUTOINCREMENT', '')
        # Keep IF NOT EXISTS for idempotent schema creation
        
        # PostgreSQL uses BOOLEAN instead of INTEGER for booleans (already compatible)
        
        return schema_sql
    
    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")
    
    def _placeholder(self) -> str:
        """Get SQL placeholder for current database type"""
        return '%s' if self.db_type == 'postgresql' else '?'
    
    # User operations
    def add_user(self, user_id: int, username: str = None, 
                 first_name: str = None, last_name: str = None,
                 is_admin: bool = False) -> bool:
        """Add or update a user"""
        try:
            cursor = self.connection.cursor()
            p = self._placeholder()
            
            if self.db_type == 'postgresql':
                cursor.execute("""
                    INSERT INTO users (user_id, username, first_name, last_name, is_admin)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        is_admin = EXCLUDED.is_admin
                """, (user_id, username, first_name, last_name, is_admin))
            else:
                cursor.execute(f"""
                    INSERT OR REPLACE INTO users 
                    (user_id, username, first_name, last_name, is_admin)
                    VALUES ({p}, {p}, {p}, {p}, {p})
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
            placeholder = '%s' if self.db_type == 'postgresql' else '?'
            cursor.execute(f"SELECT * FROM users WHERE user_id = {placeholder}", (user_id,))
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

    def _ensure_last_active_column(self):
        """Ensure `last_active` column exists in users table (migration)"""
        try:
            cursor = self.connection.cursor()
            
            if self.db_type == 'postgresql':
                # PostgreSQL way to check column exists
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name='users' AND column_name='last_active'
                """)
                if not cursor.fetchone():
                    logger.info("Adding 'last_active' column to users table (PostgreSQL)")
                    cursor.execute("ALTER TABLE users ADD COLUMN last_active TIMESTAMP")
                    if not self.connection.autocommit:
                        self.connection.commit()
                    logger.info("✓ Successfully added last_active column")
            else:
                # SQLite way
                cursor.execute("PRAGMA table_info(users)")
                cols = [row[1] if isinstance(row, tuple) else row['name'] for row in cursor.fetchall()]
                if 'last_active' not in cols:
                    logger.info("Adding 'last_active' column to users table (SQLite)")
                    cursor.execute("ALTER TABLE users ADD COLUMN last_active TIMESTAMP")
                    self.connection.commit()
                    logger.info("✓ Successfully added last_active column")
        except Exception as e:
            logger.error(f"Failed to add last_active column: {e}")
            # Don't raise - allow bot to continue even if migration fails

    def update_last_active(self, user_id: int) -> bool:
        """Update the last_active timestamp for a user"""
        try:
            cursor = self.connection.cursor()
            placeholder = '%s' if self.db_type == 'postgresql' else '?'
            
            cursor.execute(f"""
                UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = {placeholder}
            """, (user_id,))
            
            # If user not present, insert a minimal record
            if cursor.rowcount == 0:
                if self.db_type == 'postgresql':
                    cursor.execute("""
                        INSERT INTO users (user_id, last_active) 
                        VALUES (%s, CURRENT_TIMESTAMP)
                        ON CONFLICT (user_id) DO NOTHING
                    """, (user_id,))
                else:
                    cursor.execute("""
                        INSERT OR IGNORE INTO users (user_id, last_active) 
                        VALUES (?, CURRENT_TIMESTAMP)
                    """, (user_id,))
                    
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update last_active: {e}")
            return False

    def get_active_users_count(self, days: int = 7) -> int:
        """Get count of users active within the last `days` days"""
        try:
            cursor = self.connection.cursor()
            
            if self.db_type == 'postgresql':
                cursor.execute("""
                    SELECT COUNT(*) as count FROM users 
                    WHERE last_active >= NOW() - INTERVAL '%s days'
                """, (days,))
            else:
                cursor.execute("""
                    SELECT COUNT(*) as count FROM users 
                    WHERE last_active >= datetime('now', '-' || ? || ' days')
                """, (days,))
            
            row = cursor.fetchone()
            return row['count'] if row else 0
        except Exception as e:
            logger.error(f"Failed to get active users count: {e}")
            # Fallback: return total user count if last_active column doesn't exist
            try:
                cursor = self.connection.cursor()
                cursor.execute("SELECT COUNT(*) as count FROM users")
                row = cursor.fetchone()
                return row['count'] if row else 0
            except:
                return 0
            return row['count'] if row else 0
        except Exception as e:
            logger.error(f"Failed to get active users count: {e}")
            return 0
    
    # Subscription operations
    def add_subscription(self, user_id: int, folder_id: str = None) -> bool:
        """Subscribe user to notifications"""
        try:
            cursor = self.connection.cursor()
            p = self._placeholder()
            cursor.execute(f"""
                INSERT INTO subscriptions (user_id, folder_id, is_active)
                VALUES ({p}, {p}, TRUE)
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
            p = self._placeholder()
            if folder_id is None:
                # Remove all subscriptions for user
                cursor.execute(f"""
                    UPDATE subscriptions 
                    SET is_active = FALSE 
                    WHERE user_id = {p} AND folder_id IS NULL
                """, (user_id,))
            else:
                cursor.execute(f"""
                    UPDATE subscriptions 
                    SET is_active = FALSE 
                    WHERE user_id = {p} AND folder_id = {p}
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
            p = self._placeholder()
            cursor.execute(f"""
                SELECT COUNT(*) as count FROM subscriptions 
                WHERE user_id = {p} AND folder_id IS {p} AND is_active = TRUE
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
            p = self._placeholder()
            cursor.execute(f"""
                SELECT DISTINCT user_id FROM subscriptions 
                WHERE is_active = TRUE AND folder_id IS {p}
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
            p = self._placeholder()
            
            if self.db_type == 'postgresql':
                cursor.execute(f"""
                    INSERT INTO files 
                    (file_id, name, parent_folder_id, file_type, size_bytes, 
                     modified_time, download_url, is_folder, path)
                    VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
                    ON CONFLICT (file_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        parent_folder_id = EXCLUDED.parent_folder_id,
                        file_type = EXCLUDED.file_type,
                        size_bytes = EXCLUDED.size_bytes,
                        modified_time = EXCLUDED.modified_time,
                        download_url = EXCLUDED.download_url,
                        is_folder = EXCLUDED.is_folder,
                        path = EXCLUDED.path
                """, (file_id, name, parent_folder_id, file_type, size_bytes,
                      modified_time, download_url, is_folder, path))
            else:
                cursor.execute(f"""
                    INSERT OR REPLACE INTO files 
                    (file_id, name, parent_folder_id, file_type, size_bytes, 
                     modified_time, download_url, is_folder, path)
                    VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
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
            p = self._placeholder()
            cursor.execute(f"SELECT * FROM files WHERE file_id = {p}", (file_id,))
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
            p = self._placeholder()
            cursor.execute(f"""
                INSERT INTO downloads (user_id, file_id, download_type)
                VALUES ({p}, {p}, {p})
            """, (user_id, file_id, download_type))
            
            # Update user's total downloads
            cursor.execute(f"""
                UPDATE users 
                SET total_downloads = total_downloads + 1 
                WHERE user_id = {p}
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
            p = self._placeholder()
            cursor.execute(f"""
                SELECT d.*, f.name as file_name 
                FROM downloads d
                LEFT JOIN files f ON d.file_id = f.file_id
                WHERE d.user_id = {p}
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
            p = self._placeholder()
            cursor.execute(f"""
                INSERT INTO notifications_sent (file_id, recipient_count)
                VALUES ({p}, {p})
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

    # Favorites operations
    def add_favorite(self, user_id: int, file_id: str, file_name: str, 
                     file_path: str = None, is_folder: bool = False) -> bool:
        """Add a file/folder to user's favorites"""
        try:
            cursor = self.connection.cursor()
            p = self._placeholder()
            
            if self.db_type == 'postgresql':
                cursor.execute(f"""
                    INSERT INTO favorites (user_id, file_id, file_name, file_path, is_folder)
                    VALUES ({p}, {p}, {p}, {p}, {p})
                    ON CONFLICT (user_id, file_id) DO NOTHING
                """, (user_id, file_id, file_name, file_path, is_folder))
            else:
                cursor.execute(f"""
                    INSERT OR IGNORE INTO favorites 
                    (user_id, file_id, file_name, file_path, is_folder)
                    VALUES ({p}, {p}, {p}, {p}, {p})
                """, (user_id, file_id, file_name, file_path, is_folder))
            
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add favorite: {e}")
            return False
    
    def remove_favorite(self, user_id: int, file_id: str) -> bool:
        """Remove a file/folder from user's favorites"""
        try:
            cursor = self.connection.cursor()
            p = self._placeholder()
            cursor.execute(f"""
                DELETE FROM favorites WHERE user_id = {p} AND file_id = {p}
            """, (user_id, file_id))
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to remove favorite: {e}")
            return False
    
    def get_favorites(self, user_id: int) -> List[Dict]:
        """Get user's favorite files/folders"""
        try:
            cursor = self.connection.cursor()
            p = self._placeholder()
            cursor.execute(f"""
                SELECT * FROM favorites WHERE user_id = {p} ORDER BY added_date DESC
            """, (user_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get favorites: {e}")
            return []
    
    def is_favorite(self, user_id: int, file_id: str) -> bool:
        """Check if file/folder is in favorites"""
        try:
            cursor = self.connection.cursor()
            p = self._placeholder()
            cursor.execute(f"""
                SELECT COUNT(*) as count FROM favorites 
                WHERE user_id = {p} AND file_id = {p}
            """, (user_id, file_id))
            row = cursor.fetchone()
            return row['count'] > 0 if row else False
        except Exception as e:
            logger.error(f"Failed to check favorite: {e}")
            return False
    
    # Download Queue operations
    def add_to_queue(self, user_id: int, file_id: str, file_name: str, file_size: int = 0) -> bool:
        """Add file to download queue. Returns False if already in queue."""
        try:
            # First check if file is already in queue
            if self.is_in_queue(user_id, file_id):
                return False
            
            cursor = self.connection.cursor()
            p = self._placeholder()
            cursor.execute(f"""
                INSERT INTO download_queue (user_id, file_id, file_name, file_size)
                VALUES ({p}, {p}, {p}, {p})
            """, (user_id, file_id, file_name, file_size))
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add to queue: {e}")
            return False
    
    def is_in_queue(self, user_id: int, file_id: str) -> bool:
        """Check if file is already in user's queue"""
        try:
            cursor = self.connection.cursor()
            p = self._placeholder()
            cursor.execute(f"""
                SELECT COUNT(*) as count FROM download_queue 
                WHERE user_id = {p} AND file_id = {p} AND status = 'pending'
            """, (user_id, file_id))
            row = cursor.fetchone()
            return row['count'] > 0 if row else False
        except Exception as e:
            logger.error(f"Failed to check queue: {e}")
            return False
    
    def get_queue(self, user_id: int) -> List[Dict]:
        """Get user's download queue"""
        try:
            cursor = self.connection.cursor()
            p = self._placeholder()
            cursor.execute(f"""
                SELECT * FROM download_queue 
                WHERE user_id = {p} AND status = 'pending'
                ORDER BY added_date ASC
            """, (user_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get queue: {e}")
            return []
    
    def remove_from_queue(self, queue_id: int) -> bool:
        """Remove item from download queue"""
        try:
            cursor = self.connection.cursor()
            p = self._placeholder()
            cursor.execute(f"DELETE FROM download_queue WHERE id = {p}", (queue_id,))
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to remove from queue: {e}")
            return False
    
    def clear_queue(self, user_id: int) -> bool:
        """Clear user's download queue"""
        try:
            cursor = self.connection.cursor()
            p = self._placeholder()
            cursor.execute(f"DELETE FROM download_queue WHERE user_id = {p}", (user_id,))
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to clear queue: {e}")
            return False
    
    # Shortcuts operations
    def add_shortcut(self, user_id: int, folder_id: str, folder_name: str,
                     folder_path: str = None, shortcut_name: str = None) -> bool:
        """Add folder shortcut"""
        try:
            cursor = self.connection.cursor()
            p = self._placeholder()
            name = shortcut_name or folder_name
            
            if self.db_type == 'postgresql':
                cursor.execute(f"""
                    INSERT INTO shortcuts (user_id, folder_id, folder_name, folder_path, shortcut_name)
                    VALUES ({p}, {p}, {p}, {p}, {p})
                    ON CONFLICT (user_id, folder_id) DO UPDATE SET shortcut_name = EXCLUDED.shortcut_name
                """, (user_id, folder_id, folder_name, folder_path, name))
            else:
                cursor.execute(f"""
                    INSERT OR REPLACE INTO shortcuts 
                    (user_id, folder_id, folder_name, folder_path, shortcut_name)
                    VALUES ({p}, {p}, {p}, {p}, {p})
                """, (user_id, folder_id, folder_name, folder_path, name))
            
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add shortcut: {e}")
            return False
    
    def remove_shortcut(self, user_id: int, folder_id: str) -> bool:
        """Remove folder shortcut"""
        try:
            cursor = self.connection.cursor()
            p = self._placeholder()
            cursor.execute(f"""
                DELETE FROM shortcuts WHERE user_id = {p} AND folder_id = {p}
            """, (user_id, folder_id))
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to remove shortcut: {e}")
            return False
    
    def get_shortcuts(self, user_id: int) -> List[Dict]:
        """Get user's folder shortcuts"""
        try:
            cursor = self.connection.cursor()
            p = self._placeholder()
            cursor.execute(f"""
                SELECT * FROM shortcuts WHERE user_id = {p} ORDER BY created_date DESC
            """, (user_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get shortcuts: {e}")
            return []
    
    # Support Ticket Functions
    def create_support_ticket(self, user_id: int, username: str, message: str, error_context: str = None) -> bool:
        """Create a new support ticket"""
        try:
            cursor = self.connection.cursor()
            p = self._placeholder()
            cursor.execute(f"""
                INSERT INTO support_tickets (user_id, username, message, error_context, status)
                VALUES ({p}, {p}, {p}, {p}, 'open')
            """, (user_id, username, message, error_context))
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to create support ticket: {e}")
            return False
    
    def get_user_tickets(self, user_id: int) -> List[Dict]:
        """Get all support tickets for a user"""
        try:
            cursor = self.connection.cursor()
            p = self._placeholder()
            cursor.execute(f"""
                SELECT * FROM support_tickets 
                WHERE user_id = {p} 
                ORDER BY created_date DESC
            """, (user_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get user tickets: {e}")
            return []
    
    def get_all_open_tickets(self) -> List[Dict]:
        """Get all open support tickets (admin function)"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT * FROM support_tickets 
                WHERE status IN ('open', 'in_progress')
                ORDER BY created_date DESC
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get open tickets: {e}")
            return []
    
    def update_ticket_status(self, ticket_id: int, status: str, admin_notes: str = None) -> bool:
        """Update support ticket status (admin function)"""
        try:
            cursor = self.connection.cursor()
            p = self._placeholder()
            
            if status in ('resolved', 'closed'):
                cursor.execute(f"""
                    UPDATE support_tickets 
                    SET status = {p}, admin_notes = {p}, resolved_date = CURRENT_TIMESTAMP
                    WHERE id = {p}
                """, (status, admin_notes, ticket_id))
            else:
                cursor.execute(f"""
                    UPDATE support_tickets 
                    SET status = {p}, admin_notes = {p}
                    WHERE id = {p}
                """, (status, admin_notes, ticket_id))
            
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update ticket status: {e}")
            return False


