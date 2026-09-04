import sys
import os
from pathlib import Path
import mysql.connector

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

def factory_reset():
    print("WARNING: This will completely WIPE the cctv_unified database.")
    confirmation = input("Type 'RESET' to confirm: ")
    if confirmation != "RESET":
        print("Aborted.")
        return

    # Connect to MySQL server without selecting a specific database
    conn = mysql.connector.connect(
        host=config.DB_HOST,
        user=config.DB_USER,
        password=config.DB_PASS,
        port=config.DB_PORT
    )
    
    try:
        cursor = conn.cursor()
        print("Dropping database cctv_unified...")
        cursor.execute("DROP DATABASE IF EXISTS cctv_unified")
        
        print("Recreating database from schema.sql...")
        schema_path = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
        with open(schema_path, "r", encoding="utf-8") as f:
            sql_script = f.read()
            
        for stmt in sql_script.split(';'):
            if stmt.strip():
                cursor.execute(stmt)
            
        print("Creating default admin user...")
        cursor.execute("USE cctv_unified")
        
        from api.auth import hash_password
        admin_pass = hash_password("admin123")
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)", ("admin", admin_pass, "admin"))
        conn.commit()
        
    finally:
        cursor.close()
        conn.close()

    print("Database has been factory reset!")
    print("Now running seed_cameras.py to populate demo cameras...")
    os.system(f"{sys.executable} -m scripts.seed_cameras")
    print("Done! You can now log in with username 'admin' and password 'admin123'")

if __name__ == "__main__":
    factory_reset()


