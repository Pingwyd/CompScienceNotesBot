"""
Test Suite for New Bot Features
Tests: Favorites, Recent Downloads, Queue, Shortcuts

Run with: pytest tests/test_new_features.py -v
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

# Add bot directory to path
bot_dir = Path(__file__).parent.parent / 'bot'
sys.path.insert(0, str(bot_dir))

from utils.database import Database


class TestDatabase:
    """Test database operations for new features"""
    
    @pytest.fixture
    def db(self, tmp_path):
        """Create a temporary test database"""
        db_path = tmp_path / "test.db"
        database = Database(db_type='sqlite', db_path=str(db_path))
        yield database
        database.close()
    
    # ===== FAVORITES TESTS =====
    
    def test_add_favorite(self, db):
        """Test adding a file to favorites"""
        # Add a test user first
        db.add_user(12345, "Test", "User", "testuser")
        
        # Add favorite
        result = db.add_favorite(
            user_id=12345,
            file_id="file123",
            file_name="test.pdf",
            file_path="/Documents/test.pdf",
            is_folder=False
        )
        assert result is True
        
        # Verify it's in favorites
        favorites = db.get_favorites(12345)
        assert len(favorites) == 1
        assert favorites[0]['file_name'] == "test.pdf"
        assert favorites[0]['is_folder'] is False
    
    def test_add_duplicate_favorite(self, db):
        """Test adding the same favorite twice (should not duplicate)"""
        db.add_user(12345, "Test", "User", "testuser")
        
        # Add same favorite twice
        db.add_favorite(12345, "file123", "test.pdf", "/test.pdf", False)
        db.add_favorite(12345, "file123", "test.pdf", "/test.pdf", False)
        
        # Should only have one entry
        favorites = db.get_favorites(12345)
        assert len(favorites) == 1
    
    def test_remove_favorite(self, db):
        """Test removing a favorite"""
        db.add_user(12345, "Test", "User", "testuser")
        db.add_favorite(12345, "file123", "test.pdf", "/test.pdf", False)
        
        # Remove it
        result = db.remove_favorite(12345, "file123")
        assert result is True
        
        # Verify it's gone
        favorites = db.get_favorites(12345)
        assert len(favorites) == 0
    
    def test_is_favorite(self, db):
        """Test checking if file is favorited"""
        db.add_user(12345, "Test", "User", "testuser")
        
        # Not favorited yet
        assert db.is_favorite(12345, "file123") is False
        
        # Add to favorites
        db.add_favorite(12345, "file123", "test.pdf", "/test.pdf", False)
        
        # Now it should be favorited
        assert db.is_favorite(12345, "file123") is True
    
    def test_favorites_multiple_users(self, db):
        """Test that favorites are user-specific"""
        db.add_user(12345, "User", "One", "user1")
        db.add_user(67890, "User", "Two", "user2")
        
        # Each user adds their own favorite
        db.add_favorite(12345, "file1", "user1.pdf", "/user1.pdf", False)
        db.add_favorite(67890, "file2", "user2.pdf", "/user2.pdf", False)
        
        # Each user should only see their own
        user1_favs = db.get_favorites(12345)
        user2_favs = db.get_favorites(67890)
        
        assert len(user1_favs) == 1
        assert len(user2_favs) == 1
        assert user1_favs[0]['file_name'] == "user1.pdf"
        assert user2_favs[0]['file_name'] == "user2.pdf"
    
    def test_favorite_folders(self, db):
        """Test favoriting folders"""
        db.add_user(12345, "Test", "User", "testuser")
        
        # Add folder to favorites
        db.add_favorite(
            user_id=12345,
            file_id="folder123",
            file_name="Important Folder",
            file_path="/Docs/Important Folder",
            is_folder=True
        )
        
        favorites = db.get_favorites(12345)
        assert len(favorites) == 1
        assert favorites[0]['is_folder'] is True
        assert favorites[0]['file_name'] == "Important Folder"
    
    # ===== QUEUE TESTS =====
    
    def test_add_to_queue(self, db):
        """Test adding a file to download queue"""
        db.add_user(12345, "Test", "User", "testuser")
        
        result = db.add_to_queue(
            user_id=12345,
            file_id="file123",
            file_name="document.pdf",
            file_size=1024000
        )
        assert result is True
        
        # Verify it's in queue
        queue = db.get_queue(12345)
        assert len(queue) == 1
        assert queue[0]['file_name'] == "document.pdf"
        assert queue[0]['file_size'] == 1024000
        assert queue[0]['status'] == 'pending'
    
    def test_queue_order(self, db):
        """Test that queue maintains FIFO order"""
        db.add_user(12345, "Test", "User", "testuser")
        
        # Add multiple files
        db.add_to_queue(12345, "file1", "first.pdf", 1000)
        db.add_to_queue(12345, "file2", "second.pdf", 2000)
        db.add_to_queue(12345, "file3", "third.pdf", 3000)
        
        queue = db.get_queue(12345)
        assert len(queue) == 3
        assert queue[0]['file_name'] == "first.pdf"
        assert queue[1]['file_name'] == "second.pdf"
        assert queue[2]['file_name'] == "third.pdf"
    
    def test_remove_from_queue(self, db):
        """Test removing a specific item from queue"""
        db.add_user(12345, "Test", "User", "testuser")
        db.add_to_queue(12345, "file123", "test.pdf", 1000)
        
        queue = db.get_queue(12345)
        queue_id = queue[0]['id']
        
        result = db.remove_from_queue(queue_id)
        assert result is True
        
        queue = db.get_queue(12345)
        assert len(queue) == 0
    
    def test_clear_queue(self, db):
        """Test clearing entire queue for a user"""
        db.add_user(12345, "Test", "User", "testuser")
        
        # Add multiple items
        db.add_to_queue(12345, "file1", "first.pdf", 1000)
        db.add_to_queue(12345, "file2", "second.pdf", 2000)
        db.add_to_queue(12345, "file3", "third.pdf", 3000)
        
        result = db.clear_queue(12345)
        assert result is True
        
        queue = db.get_queue(12345)
        assert len(queue) == 0
    
    def test_queue_multiple_users(self, db):
        """Test that queues are user-specific"""
        db.add_user(12345, "User", "One", "user1")
        db.add_user(67890, "User", "Two", "user2")
        
        # Each user adds to their queue
        db.add_to_queue(12345, "file1", "user1.pdf", 1000)
        db.add_to_queue(67890, "file2", "user2.pdf", 2000)
        
        # Each user should only see their own queue
        user1_queue = db.get_queue(12345)
        user2_queue = db.get_queue(67890)
        
        assert len(user1_queue) == 1
        assert len(user2_queue) == 1
        assert user1_queue[0]['file_name'] == "user1.pdf"
        assert user2_queue[0]['file_name'] == "user2.pdf"
    
    # ===== SHORTCUTS TESTS =====
    
    def test_add_shortcut(self, db):
        """Test adding a folder shortcut"""
        db.add_user(12345, "Test", "User", "testuser")
        
        result = db.add_shortcut(
            user_id=12345,
            folder_id="folder123",
            folder_name="Lecture Notes",
            folder_path="/CS101/Lecture Notes",
            shortcut_name="CS Lectures"
        )
        assert result is True
        
        shortcuts = db.get_shortcuts(12345)
        assert len(shortcuts) == 1
        assert shortcuts[0]['folder_name'] == "Lecture Notes"
        assert shortcuts[0]['shortcut_name'] == "CS Lectures"
    
    def test_shortcut_default_name(self, db):
        """Test shortcut creation with default name (None)"""
        db.add_user(12345, "Test", "User", "testuser")
        
        db.add_shortcut(
            user_id=12345,
            folder_id="folder123",
            folder_name="Important Folder",
            folder_path="/Important Folder"
        )
        
        shortcuts = db.get_shortcuts(12345)
        assert len(shortcuts) == 1
        # Should use folder_name as default
        assert shortcuts[0]['folder_name'] == "Important Folder"
    
    def test_remove_shortcut(self, db):
        """Test removing a shortcut"""
        db.add_user(12345, "Test", "User", "testuser")
        db.add_shortcut(12345, "folder123", "Test", "/Test")
        
        result = db.remove_shortcut(12345, "folder123")
        assert result is True
        
        shortcuts = db.get_shortcuts(12345)
        assert len(shortcuts) == 0
    
    def test_shortcuts_multiple_users(self, db):
        """Test that shortcuts are user-specific"""
        db.add_user(12345, "User", "One", "user1")
        db.add_user(67890, "User", "Two", "user2")
        
        db.add_shortcut(12345, "folder1", "Folder A", "/A")
        db.add_shortcut(67890, "folder2", "Folder B", "/B")
        
        user1_shortcuts = db.get_shortcuts(12345)
        user2_shortcuts = db.get_shortcuts(67890)
        
        assert len(user1_shortcuts) == 1
        assert len(user2_shortcuts) == 1
        assert user1_shortcuts[0]['folder_name'] == "Folder A"
        assert user2_shortcuts[0]['folder_name'] == "Folder B"
    
    def test_duplicate_shortcut(self, db):
        """Test adding same folder shortcut twice (should update)"""
        db.add_user(12345, "Test", "User", "testuser")
        
        # Add shortcut
        db.add_shortcut(12345, "folder123", "Folder", "/Folder", "Old Name")
        
        # Add again with different name
        db.add_shortcut(12345, "folder123", "Folder", "/Folder", "New Name")
        
        shortcuts = db.get_shortcuts(12345)
        # Should only have one entry
        assert len(shortcuts) == 1
    
    # ===== INTEGRATION TESTS =====
    
    def test_user_workflow_favorites(self, db):
        """Test complete user workflow with favorites"""
        # User registers
        db.add_user(12345, "Test", "User", "testuser")
        
        # User browses and adds favorites
        db.add_favorite(12345, "file1", "Chapter1.pdf", "/Docs/Chapter1.pdf", False)
        db.add_favorite(12345, "file2", "Chapter2.pdf", "/Docs/Chapter2.pdf", False)
        db.add_favorite(12345, "folder1", "Important", "/Important", True)
        
        # User views favorites
        favorites = db.get_favorites(12345)
        assert len(favorites) == 3
        
        # User removes one
        db.remove_favorite(12345, "file1")
        favorites = db.get_favorites(12345)
        assert len(favorites) == 2
        
        # User checks if specific file is favorited
        assert db.is_favorite(12345, "file2") is True
        assert db.is_favorite(12345, "file1") is False
    
    def test_user_workflow_queue(self, db):
        """Test complete user workflow with download queue"""
        db.add_user(12345, "Test", "User", "testuser")
        
        # User adds files to queue
        db.add_to_queue(12345, "file1", "doc1.pdf", 1000)
        db.add_to_queue(12345, "file2", "doc2.pdf", 2000)
        db.add_to_queue(12345, "file3", "doc3.pdf", 3000)
        
        # User views queue
        queue = db.get_queue(12345)
        assert len(queue) == 3
        
        # Calculate total size
        total_size = sum(item['file_size'] for item in queue)
        assert total_size == 6000
        
        # User downloads one file and removes it
        db.remove_from_queue(queue[0]['id'])
        queue = db.get_queue(12345)
        assert len(queue) == 2
        
        # User clears remaining queue
        db.clear_queue(12345)
        queue = db.get_queue(12345)
        assert len(queue) == 0
    
    def test_user_workflow_shortcuts(self, db):
        """Test complete user workflow with shortcuts"""
        db.add_user(12345, "Test", "User", "testuser")
        
        # User creates shortcuts to frequently used folders
        db.add_shortcut(12345, "f1", "CS 101 Lectures", "/CS101/Lectures", "CS Lectures")
        db.add_shortcut(12345, "f2", "Assignments", "/CS101/Assignments", "Homework")
        db.add_shortcut(12345, "f3", "Resources", "/Resources")
        
        # User views shortcuts
        shortcuts = db.get_shortcuts(12345)
        assert len(shortcuts) == 3
        
        # User removes one shortcut
        db.remove_shortcut(12345, "f2")
        shortcuts = db.get_shortcuts(12345)
        assert len(shortcuts) == 2
    
    def test_combined_features(self, db):
        """Test using multiple features together"""
        db.add_user(12345, "Test", "User", "testuser")
        
        # User adds same file to favorites and queue
        db.add_favorite(12345, "file1", "important.pdf", "/Docs/important.pdf", False)
        db.add_to_queue(12345, "file1", "important.pdf", 5000)
        
        # Both should exist independently
        assert db.is_favorite(12345, "file1") is True
        queue = db.get_queue(12345)
        assert len(queue) == 1
        
        # User creates shortcut to a folder and also favorites it
        db.add_shortcut(12345, "folder1", "Important Folder", "/Important")
        db.add_favorite(12345, "folder1", "Important Folder", "/Important", True)
        
        shortcuts = db.get_shortcuts(12345)
        favorites = db.get_favorites(12345)
        
        assert len(shortcuts) == 1
        assert len([f for f in favorites if f['is_folder']]) == 1


class TestCommandHandlers:
    """Test command handlers for new features"""
    
    @pytest.fixture
    def mock_update(self):
        """Create mock Update object"""
        update = Mock()
        update.effective_user.id = 12345
        update.message = Mock()
        update.message.reply_text = Mock()
        return update
    
    @pytest.fixture
    def mock_context(self):
        """Create mock Context object"""
        context = Mock()
        context.user_data = {}
        return context
    
    @pytest.mark.asyncio
    async def test_recent_command_empty(self, mock_update, mock_context):
        """Test /recent command with no downloads"""
        with patch('bot.main.db') as mock_db:
            mock_db.get_user_downloads.return_value = []
            
            from bot.main import recent_command
            await recent_command(mock_update, mock_context)
            
            # Should show empty state message
            assert mock_update.message.reply_text.called
            args = mock_update.message.reply_text.call_args[0]
            assert "haven't downloaded" in args[0].lower()
    
    @pytest.mark.asyncio
    async def test_favorites_command_empty(self, mock_update, mock_context):
        """Test /favorites command with no favorites"""
        with patch('bot.main.db') as mock_db:
            mock_db.get_favorites.return_value = []
            
            from bot.main import favorites_command
            await favorites_command(mock_update, mock_context)
            
            args = mock_update.message.reply_text.call_args[0]
            assert "no favorites" in args[0].lower()
    
    @pytest.mark.asyncio
    async def test_queue_command_empty(self, mock_update, mock_context):
        """Test /queue command with empty queue"""
        with patch('bot.main.db') as mock_db:
            mock_db.get_queue.return_value = []
            
            from bot.main import queue_command
            await queue_command(mock_context)
            
            args = mock_update.message.reply_text.call_args[0]
            assert "queue is empty" in args[0].lower()
    
    @pytest.mark.asyncio
    async def test_shortcuts_command_empty(self, mock_update, mock_context):
        """Test /shortcuts command with no shortcuts"""
        with patch('bot.main.db') as mock_db:
            mock_db.get_shortcuts.return_value = []
            
            from bot.main import shortcuts_command
            await shortcuts_command(mock_update, mock_context)
            
            args = mock_update.message.reply_text.call_args[0]
            assert "no shortcuts" in args[0].lower()


class TestUtilityFunctions:
    """Test utility functions"""
    
    def test_format_file_size_bytes(self):
        """Test file size formatting for bytes"""
        from bot.main import format_file_size
        
        assert format_file_size(500) == "500 B"
        assert format_file_size(1023) == "1023 B"
    
    def test_format_file_size_kb(self):
        """Test file size formatting for kilobytes"""
        from bot.main import format_file_size
        
        assert format_file_size(1024) == "1.0 KB"
        assert format_file_size(1536) == "1.5 KB"
    
    def test_format_file_size_mb(self):
        """Test file size formatting for megabytes"""
        from bot.main import format_file_size
        
        assert format_file_size(1048576) == "1.0 MB"
        assert format_file_size(5242880) == "5.0 MB"
    
    def test_format_file_size_gb(self):
        """Test file size formatting for gigabytes"""
        from bot.main import format_file_size
        
        assert format_file_size(1073741824) == "1.0 GB"
        assert format_file_size(2147483648) == "2.0 GB"
    
    def test_format_file_size_tb(self):
        """Test file size formatting for terabytes"""
        from bot.main import format_file_size
        
        assert format_file_size(1099511627776) == "1.0 TB"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
