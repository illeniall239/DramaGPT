"""
Run database migration to add metadata column to kb_documents.

Usage:
    python run_migration.py
"""

import os
from supabase import create_client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def run_migration():
    """Apply the migration to add metadata column."""

    # Get Supabase client
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

    if not url or not key:
        print("❌ Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required in .env")
        return False

    supabase = create_client(url, key)

    # Read migration SQL
    migration_file = 'migrations/001_add_metadata_to_kb_documents.sql'

    if not os.path.exists(migration_file):
        print(f"❌ Migration file not found: {migration_file}")
        return False

    with open(migration_file, 'r') as f:
        sql = f.read()

    print("🔄 Running migration: Add metadata column to kb_documents...")
    print(f"📝 SQL:\n{sql}\n")

    try:
        # Execute the migration
        # Note: Supabase Python client doesn't support raw SQL execution directly
        # You need to run this via the Supabase SQL Editor or psql
        print("⚠️  MANUAL STEP REQUIRED:")
        print("1. Go to your Supabase Dashboard → SQL Editor")
        print("2. Copy and paste the SQL from migrations/001_add_metadata_to_kb_documents.sql")
        print("3. Click 'Run' to execute the migration")
        print("\nOr use psql:")
        print(f"psql <your-connection-string> -f {migration_file}")

        return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("KB Standalone - Database Migration")
    print("=" * 60)
    run_migration()
