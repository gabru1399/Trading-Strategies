import sqlite3, os

db_path = r'C:\Users\SIGMA\.gemini\config\plugins\persistent-memory\memory.db'
if os.path.exists(db_path):
    print(f'Size: {os.path.getsize(db_path)/(1024*1024):.2f} MB')
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cur.fetchall()
        print('Tables:', tables)
        for t in tables:
            cur.execute(f"SELECT count(*) FROM {t[0]};")
            print(f"  Table {t[0]}: {cur.fetchone()[0]} rows")
        conn.close()
    except Exception as e:
        print('Error reading db:', e)
