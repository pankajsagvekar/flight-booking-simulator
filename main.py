import os
import time
import math
import random
import asyncio
import requests
from datetime import datetime, timedelta
from typing import List

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from database import SessionLocal, engine, Base
from models import Booking, FlightCache, FareHistory
from schemas import FlightOut, BookingCreate, BookingOut, FareHistoryOut, FarePoint

load_dotenv()
API_KEY = os.getenv("API_MARKET_KEY") or os.getenv("AERODATABOX_API_KEY")
BASE_URL = os.getenv("AERODATABOX_BASE", os.getenv("AERODATABOX_BASE", "https://prod.api.market/api/v1/aedbx/aerodatabox"))
SIM_LOOP = int(os.getenv("SIMULATOR_LOOP_SECONDS", "30"))

if not API_KEY:
    raise RuntimeError("API_MARKET_KEY must be set in .env")

HEADERS = {"accept": "application/json", "x-api-market-key": API_KEY}

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Flight Booking Simulator — Dynamic Pricing")

# CORS for react dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pricing engine
def compute_price(base_fare: float, seats_left: int, seats_total: int, demand_score: float, flight_date_str: str) -> float:
    """
    Pricing factors:
      - remaining seat percentage (seat_factor)
      - time until departure (time_factor)
      - demand_score (demand_factor)
      - base_fare and tiers
    Returns a rounded price.
    """
    # clamp inputs
    seats_total = max(1, seats_total)
    seats_left = max(0, min(seats_left, seats_total))
    demand_score = max(0.0, min(1.0, demand_score))

    # seat factor: when seats are low, price increases
    remaining_pct = seats_left / seats_total  # 0..1
    seat_factor = 1.0 + (1.0 - remaining_pct) * 0.8  # up to +80%

    # time factor: closer to departure => price increases
    try:
        flight_dt = datetime.fromisoformat(flight_date_str + "T00:00")
    except Exception:
        flight_dt = datetime.utcnow()
    days_to_dep = max(0.0, (flight_dt - datetime.utcnow()).days)
    # if within 30 days, increase up to 60%
    time_factor = 1.0 + max(0.0, (30.0 - days_to_dep) / 30.0) * 0.6

    # demand factor: proportional
    demand_factor = 1.0 + demand_score * 0.7  # up to +70%

    # raw price
    raw = base_fare * seat_factor * time_factor * demand_factor

    # pricing tiers — simple: round to nearest 50/100 depending on value
    if raw < 3000:
        price = round(raw / 50) * 50
    elif raw < 10000:
        price = round(raw / 100) * 100
    else:
        price = round(raw / 200) * 200

    # ensure price at least base_fare
    price = max(price, int(base_fare * 0.5))
    return float(price)

# -------------------------
# Flight cache helpers
# -------------------------
def get_cache_key(flight_number: str, date: str, origin: str, destination: str) -> dict:
    return {"flight_number": flight_number, "date": date, "origin": origin, "destination": destination}

def ensure_flight_cache(db: Session, flight_number: str, date: str, origin: str, destination: str, airline_name: str = None) -> FlightCache:
    """
    Ensure a FlightCache row exists. If not create with simulated base_fare and seats.
    """
    fc = db.query(FlightCache).filter_by(flight_number=flight_number, date=date, origin=origin, destination=destination).first()
    if fc:
        return fc
    # create
    base = 3000.0 + (abs(hash(flight_number)) % 4000)
    seats = random.randint(80, 220)
    demand = random.uniform(0.05, 0.35)
    fc = FlightCache(
        flight_number=flight_number,
        origin=origin,
        destination=destination,
        date=date,
        base_fare=round(base,2),
        seats_total=seats,
        seats_left=seats - random.randint(0, int(seats*0.2)),
        demand_score=round(demand, 3),
        last_updated=datetime.utcnow()
    )
    db.add(fc)
    db.commit()
    db.refresh(fc)
    # record initial fare
    price = compute_price(fc.base_fare, fc.seats_left, fc.seats_total, fc.demand_score, date)
    fh = FareHistory(flight_id=fc.id, price=price)
    db.add(fh)
    db.commit()
    return fc

# -------------------------
# Background simulator
# -------------------------
async def simulator_loop():
    """
    Background loop that randomly adjusts demand and seats_left for cached flights,
    and appends fare history points.
    """
    while True:
        try:
            db = SessionLocal()
            all_flights = db.query(FlightCache).all()
            for fc in all_flights:
                # random small fluctuation in demand
                delta = random.uniform(-0.05, 0.07)
                fc.demand_score = max(0.0, min(1.0, fc.demand_score + delta))

                # occasionally simulate bookings reducing seats_left
                if random.random() < 0.3:  # 30% chance per cycle per flight
                    book_amt = random.randint(0, max(1, int(fc.seats_total * 0.03)))  # small bookings
                    fc.seats_left = max(0, fc.seats_left - book_amt)

                fc.last_updated = datetime.utcnow()

                # compute price and store history point
                price = compute_price(fc.base_fare, fc.seats_left, fc.seats_total, fc.demand_score, fc.date)
                fh = FareHistory(flight_id=fc.id, price=price)
                db.add(fh)

            db.commit()
            db.close()
        except Exception as e:
            # do not crash loop
            print("Simulator error:", e)
        await asyncio.sleep(SIM_LOOP)

@app.on_event("startup")
async def start_background_tasks():
    # start background loop
    loop = asyncio.get_event_loop()
    loop.create_task(simulator_loop())

# -------------------------
# API Endpoints
# -------------------------
def aero_flights_by_airport(origin: str, date: str):
    """Call AeroDataBox API Market endpoint for departures of origin on date"""
    from_time = f"{date}T00:00"
    to_time = f"{date}T23:59"
    url = f"{BASE_URL}/flights/airports/icao/{origin}/{from_time}/{to_time}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"AeroDataBox error {resp.status_code}")
    return resp.json()

@app.get("/api/flights/all", response_model=dict)
def get_all_flights(origin: str = Query(...), date: str = Query(...), db: Session = Depends(get_db)):
    """Return all departures from origin on the date with dynamic price and availability"""
    aero = aero_flights_by_airport(origin, date)
    departures = aero.get("departures", [])
    out = []
    for d in departures:
        flight_num = d.get("number") or d.get("callsign") or "N/A"
        dest = d.get("arrival", {}).get("airport", {}).get("icao", "")
        dep_time = d.get("departure", {}).get("scheduledTimeLocal")
        arr_time = d.get("arrival", {}).get("scheduledTimeLocal")
        fc = ensure_flight_cache(db, flight_num, date, origin, dest, d.get("airline", {}).get("name"))
        price = compute_price(fc.base_fare, fc.seats_left, fc.seats_total, fc.demand_score, date)
        out.append({
            "flight_number": flight_num,
            "airline": d.get("airline", {}).get("name"),
            "origin": origin,
            "destination": dest,
            "departure_time": dep_time,
            "arrival_time": arr_time,
            "price": price,
            "seats_left": fc.seats_left,
            "seats_total": fc.seats_total,
            "demand_score": round(fc.demand_score,3)
        })
    return {"total": len(out), "flights": out}

@app.get("/api/flights/search", response_model=dict)
def search_flights(origin: str = Query(...), destination: str = Query(...), date: str = Query(...), db: Session = Depends(get_db)):
    api = aero_flights_by_airport(origin, date)
    departures = api.get("departures", [])
    results = []
    for d in departures:
        dest = d.get("arrival", {}).get("airport", {}).get("icao", "")
        if dest and dest.upper() == destination.upper():
            flight_num = d.get("number") or d.get("callsign") or "N/A"
            dep_time = d.get("departure", {}).get("scheduledTimeLocal")
            arr_time = d.get("arrival", {}).get("scheduledTimeLocal")
            fc = ensure_flight_cache(db, flight_num, date, origin, dest, d.get("airline", {}).get("name"))
            price = compute_price(fc.base_fare, fc.seats_left, fc.seats_total, fc.demand_score, date)
            results.append({
                "flight_number": flight_num,
                "airline": d.get("airline", {}).get("name"),
                "origin": origin,
                "destination": destination,
                "departure_time": dep_time,
                "arrival_time": arr_time,
                "price": price,
                "seats_left": fc.seats_left,
                "seats_total": fc.seats_total,
                "demand_score": round(fc.demand_score,3)
            })
    return {"total": len(results), "flights": results}

@app.post("/api/bookings", response_model=BookingOut)
def create_booking(bk: BookingCreate, db: Session = Depends(get_db)):
    # reduce seats in cache
    fc = db.query(FlightCache).filter_by(flight_number=bk.flight_number, date=bk.date, origin=bk.origin, destination=bk.destination).first()
    if not fc:
        # create cache entry if missing
        fc = ensure_flight_cache(db, bk.flight_number, bk.date, bk.origin, bk.destination, bk.airline)
    if fc.seats_left < bk.passengers:
        raise HTTPException(status_code=400, detail="Not enough seats available")
    fc.seats_left -= bk.passengers
    db_booking = Booking(
        user_name=bk.user_name,
        email=bk.email,
        flight_number=bk.flight_number,
        origin=bk.origin,
        destination=bk.destination,
        date=bk.date,
        price=bk.price,
        passengers=bk.passengers
    )
    db.add(db_booking)
    # add fare history point after booking
    price_point = compute_price(fc.base_fare, fc.seats_left, fc.seats_total, fc.demand_score, fc.date)
    fh = FareHistory(flight_id=fc.id, price=price_point)
    db.add(fh)
    fc.last_updated = datetime.utcnow()
    db.commit()
    db.refresh(db_booking)
    return db_booking

@app.get("/api/bookings", response_model=List[BookingOut])
def list_bookings(email: str = Query(None), db: Session = Depends(get_db)):
    if email:
        return db.query(Booking).filter(Booking.email == email).all()
    return db.query(Booking).all()

@app.get("/api/fare-history/{flight_number}/{date}", response_model=FareHistoryOut)
def fare_history(flight_number: str, date: str, db: Session = Depends(get_db)):
    fc = db.query(FlightCache).filter_by(flight_number=flight_number, date=date).first()
    if not fc:
        raise HTTPException(status_code=404, detail="Flight not tracked")
    points = []
    for fh in fc.fares:
        points.append({"timestamp": fh.timestamp, "price": fh.price})
    return {"flight_number": flight_number, "date": date, "history": points}
