from fastapi import FastAPI, Query
import sqlite3
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="Flight Booking Simulator")

# Database helper
def get_db_connection():
    conn = sqlite3.connect("db/flights.db")
    conn.row_factory = sqlite3.Row
    return conn

# Pydantic model
class Flight(BaseModel):
    id: int
    origin: str
    destination: str
    departure_time: str
    arrival_time: str
    price: float
    seats: int

# ✅ Retrieve all flights
@app.get("/flights", response_model=List[Flight])
def get_all_flights(sort_by: Optional[str] = Query(None, enum=["price", "duration"])):
    conn = get_db_connection()
    flights = conn.execute("SELECT * FROM flights").fetchall()
    conn.close()

    result = [dict(f) for f in flights]

    # Calculate duration if sorting by it
    if sort_by == "duration":
        from datetime import datetime
        for f in result:
            dep = datetime.fromisoformat(f["departure_time"])
            arr = datetime.fromisoformat(f["arrival_time"])
            f["duration"] = (arr - dep).seconds
        result.sort(key=lambda x: x["duration"])
    elif sort_by == "price":
        result.sort(key=lambda x: x["price"])

    return result

# ✅ Search by origin, destination, and date
@app.get("/flights/search", response_model=List[Flight])
def search_flights(
    origin: str,
    destination: str,
    date: str
):
    conn = get_db_connection()
    query = """
        SELECT * FROM flights
        WHERE origin = ? AND destination = ?
        AND departure_time LIKE ?
    """
    flights = conn.execute(query, (origin, destination, f"{date}%")).fetchall()
    conn.close()
    return [dict(f) for f in flights]

# ✅ Simulate external airline API
@app.get("/external/airlines")
def external_airline_api():
    return {
        "airlines": [
            {"name": "Air India", "status": "Online"},
            {"name": "IndiGo", "status": "Online"},
            {"name": "SpiceJet", "status": "Offline"},
        ]
    }
