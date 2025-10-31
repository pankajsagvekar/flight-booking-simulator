import sqlite3

conn = sqlite3.connect("flights.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS flights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origin TEXT,
    destination TEXT,
    departure_time TEXT,
    arrival_time TEXT,
    price REAL,
    seats INTEGER
)
""")

# Sample data
flights_data = [
    ("Pune", "Delhi", "2025-11-01 06:00", "2025-11-01 08:00", 4000, 20),
    ("Delhi", "Mumbai", "2025-11-01 09:00", "2025-11-01 11:00", 3500, 15),
    ("Pune", "Bangalore", "2025-11-01 07:30", "2025-11-01 09:00", 2800, 10),
    ("Mumbai", "Chennai", "2025-11-02 10:00", "2025-11-02 12:30", 4500, 25),
]

cur.executemany("INSERT INTO flights (origin, destination, departure_time, arrival_time, price, seats) VALUES (?, ?, ?, ?, ?, ?)", flights_data)

conn.commit()
conn.close()

print("Database created and populated!")
