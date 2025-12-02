# Test Suite

This directory contains automated tests for the Telegram Google Drive Bot.

## Running Tests

### Install Test Dependencies
```bash
pip install -r requirements.txt
```

This installs:
- `pytest` - Testing framework
- `pytest-asyncio` - For testing async functions

### Run All Tests
```bash
# From project root
pytest tests/ -v
```

### Run Specific Test File
```bash
pytest tests/test_new_features.py -v
```

### Run Specific Test Class
```bash
pytest tests/test_new_features.py::TestDatabase -v
```

### Run Specific Test
```bash
pytest tests/test_new_features.py::TestDatabase::test_add_favorite -v
```

### Run with Coverage
```bash
pytest tests/ --cov=bot --cov-report=html
```

## Test Structure

### `test_new_features.py`
Tests for recently added features (Dec 2025):
- **Favorites System**: Add, remove, list, check favorites
- **Download Queue**: Add, remove, clear queue items
- **Folder Shortcuts**: Create, remove shortcuts
- **Command Handlers**: /recent, /favorites, /queue, /shortcuts
- **Utility Functions**: File size formatting

#### Test Classes:

**TestDatabase**
- Tests all database operations for new features
- Uses temporary SQLite database (no external dependencies)
- Tests user isolation (favorites/queue/shortcuts are per-user)
- Tests edge cases (duplicates, empty states, etc.)

**TestCommandHandlers**
- Tests command handler functions
- Uses mocked Update and Context objects
- Tests empty states and error handling

**TestUtilityFunctions**
- Tests helper functions (format_file_size, etc.)
- Simple input/output validation

## Test Coverage

Current features tested:
- ✅ Favorites (add, remove, list, check, folders, multi-user)
- ✅ Download Queue (add, remove, clear, order, multi-user)
- ✅ Folder Shortcuts (add, remove, list, multi-user)
- ✅ File size formatting (B, KB, MB, GB, TB)
- ✅ Command empty states

## Writing New Tests

When adding a new feature, create tests following this pattern:

```python
def test_feature_name(self, db):
    """Test description"""
    # Setup
    db.add_user(12345, "Test", "User", "testuser")
    
    # Action
    result = db.your_method(...)
    
    # Assert
    assert result is True
    assert expected_value == actual_value
```

### Best Practices:
1. Use descriptive test names (test_what_is_being_tested)
2. Follow Arrange-Act-Assert pattern
3. Test edge cases (empty, duplicates, invalid input)
4. Test multi-user scenarios
5. Use fixtures for common setup (db, mock objects)
6. Add docstrings explaining what each test validates

## Continuous Integration

Tests should be run:
- Before committing changes
- Before deploying to Render
- After adding new features
- When fixing bugs

## Troubleshooting

### Import Errors
If you see import errors, ensure you're running from the project root:
```bash
cd "c:\Users\Prosperr\Documents\Coding\Schl Py\Notes"
pytest tests/
```

### Database Errors
Tests use temporary SQLite databases that are automatically cleaned up.
If you see database locked errors, ensure no other process is using the test DB.

### Async Test Failures
Make sure `pytest-asyncio` is installed:
```bash
pip install pytest-asyncio
```

## Test Results

Example output:
```
tests/test_new_features.py::TestDatabase::test_add_favorite PASSED        [ 10%]
tests/test_new_features.py::TestDatabase::test_remove_favorite PASSED     [ 20%]
tests/test_new_features.py::TestDatabase::test_add_to_queue PASSED        [ 30%]
...
===================== 25 passed in 0.45s =====================
```

## Future Tests to Add

- [ ] File Preview feature tests
- [ ] Inline Search tests
- [ ] Filter by Type tests
- [ ] Analytics Dashboard tests
- [ ] Batch operations tests
- [ ] Cache system tests
- [ ] Integration tests with real Google Drive API (mocked)
- [ ] End-to-end user workflow tests
- [ ] Performance tests (large queues, many favorites)
- [ ] Error handling tests (network failures, API limits)

---

**Last Updated:** December 2, 2025
