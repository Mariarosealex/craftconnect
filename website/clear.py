import sqlite3

def clear_database():
    conn = sqlite3.connect("craftconnect.db")
    cursor = conn.cursor()

    # List of tables to clear
    tables = ["users", "products", "cart", "orders"]

    for table in tables:
        cursor.execute(f"DELETE FROM {table}")
        cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table}'")  # Reset auto-increment counter
        print(f"Cleared table: {table}")

    conn.commit()
    conn.close()
    print("Database cleared")

clear_database()