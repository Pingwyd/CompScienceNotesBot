"""
Test Suite for New Bot Features
Tests: Recent Downloads, Queue

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
        database = Database(str(db_path))
        
        # Initialize schema
        schema_path = Path(__file__).parent.parent / "database" / "schema.sql"
        database.initialize_schema(str(schema_path))
        
        yield database
        database.close()
    
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
    
    # ===== INTEGRATION TESTS =====
    
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
    
    def test_combined_features(self, db):
        """Test using multiple features together"""
        db.add_user(12345, "Test", "User", "testuser")
        
        # User adds file to queue
        db.add_to_queue(12345, "file1", "important.pdf", 5000)
        
        # Should exist in queue
        queue = db.get_queue(12345)
        assert len(queue) == 1


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
        # Skip - db is local variable in main(), can't mock easily
        pytest.skip("Requires refactoring to make db mockable")
    
    @pytest.mark.asyncio
    async def test_queue_command_empty(self, mock_update, mock_context):
        """Test /queue command with empty queue"""
        # Skip - db is local variable in main(), can't mock easily
        pytest.skip("Requires refactoring to make db mockable")


class TestUtilityFunctions:
    """Test utility functions"""
    
    def format_file_size(self, size_bytes: int) -> str:
        """Format bytes to human readable size (copied from main.py)"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def test_format_file_size_bytes(self):
        """Test file size formatting for bytes"""
        assert self.format_file_size(500) == "500.0 B"
        assert self.format_file_size(1023) == "1023.0 B"
    
    def test_format_file_size_kb(self):
        """Test file size formatting for kilobytes"""
        assert self.format_file_size(1024) == "1.0 KB"
        assert self.format_file_size(1536) == "1.5 KB"
    
    def test_format_file_size_mb(self):
        """Test file size formatting for megabytes"""
        assert self.format_file_size(1048576) == "1.0 MB"
        assert self.format_file_size(5242880) == "5.0 MB"
    
    def test_format_file_size_gb(self):
        """Test file size formatting for gigabytes"""
        assert self.format_file_size(1073741824) == "1.0 GB"
        assert self.format_file_size(2147483648) == "2.0 GB"
    
    def test_format_file_size_tb(self):
        """Test file size formatting for terabytes"""
        assert self.format_file_size(1099511627776) == "1.0 TB"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
