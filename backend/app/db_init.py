"""Create the SQLite database explicitly:  python -m app.db_init  (run inside backend/)."""
from .config import Settings
from .db import init_db

if __name__ == "__main__":
    s = Settings()
    init_db(s.database_file)
    print(f"Database ready at {s.database_file}")
