-- Users table
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP,
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

-- Favorites/Bookmarks table
CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    file_id TEXT,
    file_name TEXT,
    file_path TEXT,
    is_folder BOOLEAN DEFAULT FALSE,
    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    UNIQUE(user_id, file_id)
);

-- Download Queue table
CREATE TABLE IF NOT EXISTS download_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    file_id TEXT,
    file_name TEXT,
    file_size INTEGER,
    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'pending',  -- 'pending', 'processing', 'completed', 'failed'
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Folder Shortcuts table
CREATE TABLE IF NOT EXISTS shortcuts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    folder_id TEXT,
    folder_name TEXT,
    folder_path TEXT,
    shortcut_name TEXT,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    UNIQUE(user_id, folder_id)
);

-- Support Tickets table
CREATE TABLE IF NOT EXISTS support_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    message TEXT NOT NULL,
    error_context TEXT,  -- Optional: stack trace, command used, etc.
    status TEXT DEFAULT 'open',  -- 'open', 'in_progress', 'resolved', 'closed'
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_date TIMESTAMP,
    admin_notes TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_files_parent ON files(parent_folder_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_downloads_user ON downloads(user_id);
CREATE INDEX IF NOT EXISTS idx_files_modified ON files(modified_time);
CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id);
CREATE INDEX IF NOT EXISTS idx_queue_user ON download_queue(user_id);
CREATE INDEX IF NOT EXISTS idx_shortcuts_user ON shortcuts(user_id);
CREATE INDEX IF NOT EXISTS idx_support_tickets_user ON support_tickets(user_id);
CREATE INDEX IF NOT EXISTS idx_support_tickets_status ON support_tickets(status);
