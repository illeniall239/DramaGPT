import os
from sqlalchemy import create_engine, text
import pandas as pd

db_url = os.getenv('SUPABASE_DB_URL')
engine = create_engine(db_url)
table_name = "kb_data_9feeb42a_complete_bible_drama_details___2019_25_xlsx"

with engine.connect() as conn:
    print(f"--- Columns for {table_name} ---")
    res = conn.execute(text(f'SELECT * FROM "{table_name}" LIMIT 0'))
    print(res.keys())
    
    print("\n--- Sample Data ---")
    res = conn.execute(text(f'SELECT * FROM "{table_name}" WHERE "Theme" IS NOT NULL LIMIT 10'))
    for row in res:
        print(row)
    
    print("\n--- Theme Values ---")
    res = conn.execute(text(f'SELECT DISTINCT "Theme" FROM "{table_name}" WHERE "Theme" IS NOT NULL LIMIT 20'))
    for row in res:
        print(row)
