from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import sqlite3
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Flight Booking Simulator with Aviationstack")

API_KEY = os.getenv("AVIATIONSTACK_API_KEY")
BASE_URL = "https://api.aviationstack.com/v1/"

def get_db_connection():
    conn = sqlite3.connect("db/flights.db")
    conn.row_factory = sqlite3.Row
    return conn

class Flight(BaseModel):
    id: int
    origin: str
    destination: str
    departure_time: str
    arrival_time: str
    price: float
    seats: int

@app.get("/flights", response_model=List[Flight])
def get_all_flights(sort_by: Optional[str] = Query(None, enum=["price", "duration"])):
    conn = get_db_connection()
    flights = conn.execute("SELECT * FROM flights").fetchall()
    conn.close()
    result = [dict(f) for f in flights]

    if sort_by == "duration":
        for f in result:
            dep = datetime.fromisoformat(f["departure_time"])
            arr = datetime.fromisoformat(f["arrival_time"])
            f["duration"] = (arr - dep).seconds
        result.sort(key=lambda x: x["duration"])
    elif sort_by == "price":
        result.sort(key=lambda x: x["price"])

    return result

# Search flights by origin, destination, and date (local)
@app.get("/flights/search", response_model=List[Flight])
def search_flights(origin: str, destination: str, date: str):
    conn = get_db_connection()
    query = """
        SELECT * FROM flights
        WHERE origin = ? AND destination = ?
        AND departure_time LIKE ?
    """
    flights = conn.execute(query, (origin, destination, f"{date}%")).fetchall()
    conn.close()
    return [dict(f) for f in flights]

# Fetch real-time flights from Aviationstack
@app.get("/external/flights")
def get_live_flights(
    dep_iata: str = Query("DEL"),
    arr_iata: str = Query("BOM")
):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key not set in environment variables.")

    url = f"{BASE_URL}flights?access_key={API_KEY}&dep_iata={dep_iata}&arr_iata={arr_iata}"
    response = requests.get(url)

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch data from Aviationstack.")

    data = response.json().get("data", [])
    flights = [
        {
            "flight_date": f.get("flight_date"),
            "airline": f.get("airline", {}).get("name"),
            "flight_number": f.get("flight", {}).get("number"),
            "departure_airport": f.get("departure", {}).get("airport"),
            "arrival_airport": f.get("arrival", {}).get("airport"),
            "status": f.get("flight_status"),
        }
        for f in data
    ]
    return {"count": len(flights), "flights": flights}

# Fetch airlines (live)
@app.get("/external/airlines")
def get_airlines():
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key not set in environment variables.")

    url = f"{BASE_URL}airlines?access_key={API_KEY}"
    response = requests.get(url)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch airlines.")

    return response.json()

# Fetch airports (live)
@app.get("/external/airports")
def get_airports():
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key not set in environment variables.")

    url = f"{BASE_URL}airports?access_key={API_KEY}"
    response = requests.get(url)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch airports.")

    return response.json()
