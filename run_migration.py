from sqlalchemy import create_engine, MetaData, Table, inspect
import os
import sqlite3

def add_transcript_column():
    # Get the absolute path to the database file
    db_path = os.path.abspath(os.path.join('data', 'projects.db'))
    
    # Check if database exists
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at {db_path}")
        return
    
    # Connect to SQLite database directly
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if the column already exists
        cursor.execute("PRAGMA table_info(sessions)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'transcript_text' not in columns:
            # Add the new column
            cursor.execute('ALTER TABLE sessions ADD COLUMN transcript_text TEXT')
            conn.commit()
            print("[SUCCESS] Added 'transcript_text' column to 'sessions' table.")
        else:
            print("[INFO] 'transcript_text' column already exists in 'sessions' table.")
            
    except sqlite3.OperationalError as e:
        if "no such table: sessions" in str(e):
            print("[ERROR] 'sessions' table not found in the database.")
        else:
            print(f"❌ Database error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    add_transcript_column()
