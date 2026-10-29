
import sqlite3
import csv
from pathlib import Path

database = Path(__file__).resolve().parent / "medicines.db"
output = Path(__file__).resolve().parent / "medicine_training_data.csv"

conn = sqlite3.connect(database)

cursor = conn.execute(
    "SELECT name, quantity, expiry_date FROM medicines"
)

rows = cursor.fetchall()

with open(output, "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow(["name", "quantity", "expiry_date"])
    writer.writerows(rows)

conn.close()

print(f"Exported {len(rows)} medicines to {output.name}")
