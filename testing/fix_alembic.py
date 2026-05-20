# fix_alembic.py
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

# Try to get URL from .env first, then use the one from alembic.ini
db_url = os.getenv('DATABASE_URL', 'postgresql+asyncpg://postgres:admin@localhost:5433/medicare_db')

print(f"Connecting to: {db_url}")

try:
    # Note: create_engine needs sync URL for this operation
    # Replace asyncpg with psycopg2 for sync operations
    if 'asyncpg' in db_url:
        sync_db_url = db_url.replace('postgresql+asyncpg', 'postgresql')
    else:
        sync_db_url = db_url
    
    engine = create_engine(sync_db_url)
    
    with engine.connect() as conn:
        # Check if alembic_version table exists
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'alembic_version'
            );
        """))
        table_exists = result.scalar()
        
        if table_exists:
            print("Found alembic_version table, clearing it...")
            conn.execute(text("DELETE FROM alembic_version;"))
            conn.commit()
            print("✅ Successfully cleared alembic_version table")
        else:
            print("ℹ️ alembic_version table doesn't exist (creating it)...")
        
        # Verify
        result = conn.execute(text("SELECT * FROM alembic_version"))
        rows = result.fetchall()
        print(f"Table now has {len(rows)} rows")
        
except Exception as e:
    print(f"❌ Error: {e}")
    print("\nTrying alternative approach...")
    
    # Alternative: Direct SQL execution
    import subprocess
    try:
        # Using psql command
        cmd = f'psql -U postgres -d medicare_db -h localhost -p 5433 -c "DELETE FROM alembic_version;"'
        subprocess.run(cmd, shell=True, check=True)
        print("✅ Cleared via psql")
    except:
        print("⚠️ Please clear the table manually:")
        print("1. Open pgAdmin or any PostgreSQL client")
        print("2. Connect to your database")
        print("3. Run: DELETE FROM alembic_version;")
        print("4. Then run: SELECT * FROM alembic_version; to verify it's empty")