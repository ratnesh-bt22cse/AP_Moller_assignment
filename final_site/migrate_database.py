"""
Database migration script to add session_name column to existing chat_history.db

WHAT THIS DOES:
- Adds session_name column to chat_sessions table for ChatGPT-style naming
- Updates existing sessions with default names
- Safe to run multiple times (idempotent)

WHEN TO RUN:
- First time setup
- After pulling code updates
- If you see "no such column: session_name" error

HOW TO RUN:
    cd final_site
    python migrate_database.py

TECHNICAL DETAILS:
- Checks if column exists before adding (prevents errors)
- Uses ALTER TABLE (standard SQL DDL)
- Auto-generates names from session_id for existing records
- Commits transaction only on success
"""
import sqlite3
import os

def migrate_database():
    db_path = "chat_history.db"
    
    if not os.path.exists(db_path):
        print(f"Database {db_path} doesn't exist. No migration needed.")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if session_name column already exists
        cursor.execute("PRAGMA table_info(chat_sessions)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'session_name' in columns:
            print("✓ Column 'session_name' already exists. No migration needed.")
        else:
            print("Adding 'session_name' column to chat_sessions table...")
            cursor.execute("""
                ALTER TABLE chat_sessions 
                ADD COLUMN session_name TEXT
            """)
            
            # Update existing sessions with default names
            cursor.execute("""
                UPDATE chat_sessions 
                SET session_name = 'Conversation ' || substr(session_id, 1, 8)
                WHERE session_name IS NULL
            """)
            
            conn.commit()
            print("✓ Migration completed successfully!")
            print("✓ Updated existing sessions with default names.")
            
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    print("=" * 50)
    print("Database Migration Script")
    print("=" * 50)
    migrate_database()
    print("=" * 50)
