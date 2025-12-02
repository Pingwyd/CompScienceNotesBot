"""
Pre-Deployment Verification Script
Tests database compatibility with both SQLite and PostgreSQL
"""

import os
import sys
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.utils.database import Database


def test_database_operations():
    """Test all database operations"""
    print("=" * 60)
    print("DATABASE COMPATIBILITY TEST")
    print("=" * 60)
    
    # Initialize database
    db = Database()
    print(f"\n✓ Database initialized")
    print(f"  Type: {db.db_type}")
    print(f"  Database: {db.database_url if db.db_type == 'postgresql' else 'telegram_bot.db'}")
    
    # Test schema creation
    db.initialize_schema()
    print(f"\n✓ Schema initialized")
    
    # Test user operations
    print(f"\n{'User Operations':-^60}")
    test_user_id = 999999999
    
    db.add_user(test_user_id, "testuser", "Test", "User", is_admin=True)
    print("✓ User added")
    
    user = db.get_user(test_user_id)
    assert user is not None, "Failed to retrieve user"
    assert user['username'] == 'testuser'
    print(f"✓ User retrieved: {user['first_name']} {user['last_name']}")
    
    db.update_last_active(test_user_id)
    print("✓ Last active updated")
    
    active_count = db.get_active_users_count()
    print(f"✓ Active users count: {active_count}")
    
    # Test subscription operations
    print(f"\n{'Subscription Operations':-^60}")
    
    db.add_subscription(test_user_id)
    print("✓ Subscription added")
    
    is_sub = db.is_subscribed(test_user_id)
    assert is_sub, "User should be subscribed"
    print("✓ Subscription verified")
    
    subscribers = db.get_subscribers()
    assert test_user_id in subscribers
    print(f"✓ Subscriber list retrieved: {len(subscribers)} subscribers")
    
    db.remove_subscription(test_user_id)
    print("✓ Subscription removed")
    
    is_sub = db.is_subscribed(test_user_id)
    assert not is_sub, "User should not be subscribed"
    print("✓ Unsubscribe verified")
    
    # Test file operations
    print(f"\n{'File Operations':-^60}")
    
    test_file_id = "test_file_123"
    db.add_file(
        file_id=test_file_id,
        name="Test Document.pdf",
        parent_folder_id=None,
        file_type="application/pdf",
        size_bytes=1024000,
        modified_time=datetime.now().isoformat(),
        download_url="https://example.com/download",
        is_folder=False,
        path="/Test Folder/Test Document.pdf"
    )
    print("✓ File added")
    
    file = db.get_file(test_file_id)
    assert file is not None
    assert file['name'] == "Test Document.pdf"
    print(f"✓ File retrieved: {file['name']}")
    
    all_files = db.get_all_file_ids()
    assert test_file_id in all_files
    print(f"✓ All file IDs retrieved: {len(all_files)} files")
    
    # Test download logging
    print(f"\n{'Download Operations':-^60}")
    
    db.log_download(test_user_id, test_file_id, 'individual')
    print("✓ Download logged")
    
    downloads = db.get_user_downloads(test_user_id)
    assert len(downloads) > 0
    print(f"✓ Download history retrieved: {len(downloads)} downloads")
    
    # Test notification logging
    print(f"\n{'Notification Operations':-^60}")
    
    db.log_notification(test_file_id, recipient_count=5)
    print("✓ Notification logged")
    
    # Test stats
    print(f"\n{'Statistics':-^60}")
    
    stats = db.get_stats()
    assert 'total_users' in stats
    assert 'total_downloads' in stats
    print(f"✓ Total users: {stats['total_users']}")
    print(f"✓ Total downloads: {stats['total_downloads']}")
    print(f"✓ Total files: {stats['total_files']}")
    print(f"✓ Active subscribers: {stats['active_subscribers']}")
    
    # Cleanup
    print(f"\n{'Cleanup':-^60}")
    db.close()
    print("✓ Database connection closed")
    
    print(f"\n{'='*60}")
    print("ALL TESTS PASSED ✓")
    print(f"{'='*60}")
    print(f"\nDatabase type: {db.db_type.upper()}")
    print(f"Status: READY FOR DEPLOYMENT")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    try:
        test_database_operations()
        sys.exit(0)
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"TEST FAILED ✗")
        print(f"{'='*60}")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
