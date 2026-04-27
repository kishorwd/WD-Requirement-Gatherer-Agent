"""
Migration script: Add 'industry' and 'pre_meeting_brief' columns to the projects table.
Safe to run multiple times — checks if columns already exist before adding.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "projects.db")

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}. Skipping migration.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get existing columns
    cursor.execute("PRAGMA table_info(projects)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    added = []

    if "industry" not in existing_columns:
        cursor.execute("ALTER TABLE projects ADD COLUMN industry TEXT")
        added.append("industry")

    if "pre_meeting_brief" not in existing_columns:
        cursor.execute("ALTER TABLE projects ADD COLUMN pre_meeting_brief TEXT")
        added.append("pre_meeting_brief")

    conn.commit()
    conn.close()

    if added:
        print(f"Migration complete. Added columns: {', '.join(added)}")
    else:
        print("All columns already exist. No changes needed.")

if __name__ == "__main__":
    migrate()
