import sqlite3


def init_db():
    conn = sqlite3.connect("investment.db")
    c = conn.cursor()
    #Users table
    c.execute("""
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
          
          )
          """)

#   Investments table
    c.execute("""
            CREATE TABLE IF NOT EXISTS investments(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                symbol TEXT NOT NULL,    --stock/crypto ticker(e.g., AAPL, TSLA, BTC-USD)
                category TEXT NOT NULL,
                quantity REAL,
                buy_price REAL,
                FOREIGN KEY(user_id) REFERENCES users(id)
          )
          """)
    conn.commit()
    conn.close()