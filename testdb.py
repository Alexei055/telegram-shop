from mysql.connector import (connection)

mydb = connection.MySQLConnection(
    host="localhost",
    user="root",
    passwd="admin",
    database="telegram_shop"
)

cur = mydb.cursor(buffered=True)


def print_db():
    cur.execute("SELECT table_name FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'telegram_shop'")
    tables = cur.fetchall()
    for tab in tables:
        cur.execute(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'telegram_shop' AND TABLE_NAME='{tab[0]}'")
        columns = [colm[0] for colm in cur.fetchall()]
        cur.execute(f"SELECT * FROM {tab[0]}")
        first_string = cur.fetchone()
        print(f"\n{tab[0]}: {columns}")
        print(f"{first_string}\n")

print_db()