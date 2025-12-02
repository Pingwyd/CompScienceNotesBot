-- Users table
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_admin BOOLEAN DEFAULT FALSE,
    total_downloads INTEGER DEFAULT 0
);

-- Files table
CREATE TABLE IF NOT EXISTS files (
    file_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    parent_folder_id TEXT,
    file_type TEXT,
    size_bytes INTEGER,
    modified_time TIMESTAMP,
    download_url TEXT,
    is_folder BOOLEAN DEFAULT FALSE,
    path TEXT  -- Full path for easy display
);

-- Notification subscriptions
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    folder_id TEXT,  -- NULL means subscribed to entire drive
    is_active BOOLEAN DEFAULT TRUE,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Download history
CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    file_id TEXT,
    download_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    download_type TEXT,  -- 'individual', 'zip', 'link'
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (file_id) REFERENCES files(file_id)
);

-- Notification log
CREATE TABLE IF NOT EXISTS notifications_sent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT,
    sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    recipient_count INTEGER,
    FOREIGN KEY (file_id) REFERENCES files(file_id)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_files_parent ON files(parent_folder_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_downloads_user ON downloads(user_id);
CREATE INDEX IF NOT EXISTS idx_files_modified ON files(modified_time);
