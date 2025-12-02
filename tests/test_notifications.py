"""
Test script for notification system
Run this to verify the notification service is working correctly
"""

import sys
from pathlib import Path

# Add bot directory to path
bot_dir = Path(__file__).parent / 'bot'
sys.path.insert(0, str(bot_dir))

from dotenv import load_dotenv
load_dotenv()

from services.drive_service import DriveService
from services.notification import NotificationService


def test_notification_service():
    """Test the notification service functionality"""
    
    print("=" * 60)
    print("Testing Notification Service")
    print("=" * 60)
    
    # Initialize services
    print("\n1. Initializing DriveService...")
    try:
        drive = DriveService()
        print("   ✓ DriveService initialized")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        return
    
    print("\n2. Initializing NotificationService...")
    try:
        notif = NotificationService(drive)
        print("   ✓ NotificationService initialized")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        return
    
    print("\n3. Initializing file state from Drive...")
    try:
        success = notif.initialize_file_state()
        if success:
            print(f"   ✓ File state initialized with {len(notif.known_files)} files")
        else:
            print("   ✗ Failed to initialize file state")
            return
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        return
    
    print("\n4. Testing subscriber management...")
    try:
        # Add subscriber
        notif.add_subscriber(123456789)
        assert notif.is_subscribed(123456789), "User should be subscribed"
        print("   ✓ Add subscriber: OK")
        
        # Remove subscriber
        notif.remove_subscriber(123456789)
        assert not notif.is_subscribed(123456789), "User should not be subscribed"
        print("   ✓ Remove subscriber: OK")
        
        # Add multiple subscribers
        notif.add_subscriber(111)
        notif.add_subscriber(222)
        notif.add_subscriber(333)
        assert len(notif.get_subscribers()) == 3, "Should have 3 subscribers"
        print("   ✓ Multiple subscribers: OK")
        
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        return
    
    print("\n5. Testing file check (should find no new files on first check)...")
    try:
        new_files = notif.check_for_new_files()
        print(f"   ✓ Check completed. Found {len(new_files)} new files")
        print(f"   (Expected 0 on first check right after initialization)")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        return
    
    print("\n6. Testing notification message formatting...")
    try:
        # Create sample new files
        sample_files = [
            {
                'id': 'test1',
                'name': 'Lecture_5.pdf',
                'path': 'Physics/Semester 1',
                'size': '2457600',  # ~2.4 MB
                'is_folder': False
            },
            {
                'id': 'test2',
                'name': 'Assignment_3.docx',
                'path': 'Math/Homework',
                'size': '102400',  # 100 KB
                'is_folder': False
            },
            {
                'id': 'test3',
                'name': 'Videos',
                'path': 'Chemistry',
                'size': None,
                'is_folder': True
            }
        ]
        
        message = notif.format_notification_message(sample_files)
        print("   ✓ Formatted notification message:")
        print("-" * 60)
        print(message)
        print("-" * 60)
        
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        return
    
    print("\n7. Testing check interval logic...")
    try:
        should_check = notif.should_check_now(check_interval_hours=48)
        print(f"   ✓ Should check now: {should_check}")
        print(f"   Last check time: {notif.last_check_time}")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        return
    
    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)
    print("\nNotification system is ready to use!")
    print("\nNext steps:")
    print("1. Run the bot with: python bot/main.py")
    print("2. Use /notifications command to subscribe")
    print("3. Bot will check every 48 hours (configurable)")
    print("4. Admins can use /check_now to trigger manual check")


if __name__ == "__main__":
    test_notification_service()
