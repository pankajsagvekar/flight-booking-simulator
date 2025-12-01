import asyncio
import json
import os
import random
import string
from datetime import datetime, timedelta
from typing import List

import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine, ensure_schema_migrations
from models import Booking, FareHistory, FlightCache, SeatAssignment, SeatInventory
from schemas import (
    BookingDetail,
    BookingHoldRequest,
    BookingHoldResponse,
    BookingHistoryResponse,
    CancellationResponse,
    FareHistoryOut,
    FarePoint,
    FlightOut,
    FlightSearchResponse,
    PassengerInfo,
    PaymentRequest,
    PaymentResponse,
    PricingTier,
    SeatInfo,
)

load_dotenv()
API_KEY = os.getenv("API_MARKET_KEY") or os.getenv("AERODATABOX_API_KEY")
BASE_URL = os.getenv(
    "AERODATABOX_BASE",
    os.getenv("AERODATABOX_BASE", "https://prod.api.market/api/v1/aedbx/aerodatabox"),
)
SIM_LOOP = int(os.getenv("SIMULATOR_LOOP_SECONDS", "30"))
DEFAULT_HOLD_MINUTES = int(os.getenv("BOOKING_HOLD_MINUTES", "15"))

if not API_KEY:
    raise RuntimeError("API_MARKET_KEY or AERODATABOX_API_KEY must be set in .env")

HEADERS = {"accept": "application/json", "x-api-market-key": API_KEY}

PRICING_MULTIPLIERS = {
    "ECONOMY": {"multiplier": 1.0},
    "PREMIUM": {"multiplier": 1.25},
    "BUSINESS": {"multiplier": 1.6},
}
CABIN_LAYOUT = {
    "BUSINESS": {"rows": range(1, 5), "labels": ["A", "C", "D", "F"]},
    "PREMIUM": {"rows": range(5, 9), "labels": list("ABCDEF")},
    "ECONOMY": {"rows": range(9, 31), "labels": list("ABCDEF")},
}

Base.metadata.create_all(bind=engine)
ensure_schema_migrations()

app = FastAPI(title="Flight Booking Simulator � Dynamic Pricing")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def clamp(value: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(value, max_val))


def compute_price(
    base_fare: float,
    seats_left: int,
    seats_total: int,
    demand_score: float,
    flight_date_str: str,
    tier_multiplier: float = 1.0,
) -> float:
    seats_total = max(1, seats_total)
    seats_left = max(0, min(seats_left, seats_total))
    demand_score = clamp(demand_score, 0.0, 1.0)

    remaining_pct = seats_left / seats_total
    seat_factor = 1.0 + (1.0 - remaining_pct) * 0.8

    try:
        flight_dt = datetime.fromisoformat(f"{flight_date_str}T00:00")
    except ValueError:
        flight_dt = datetime.utcnow()
    days_to_dep = max(0.0, (flight_dt - datetime.utcnow()).days)
    time_factor = 1.0 + max(0.0, (30.0 - days_to_dep) / 30.0) * 0.6

    demand_factor = 1.0 + demand_score * 0.7

    raw = base_fare * seat_factor * time_factor * demand_factor * tier_multiplier

    if raw < 3000:
        price = round(raw / 50) * 50
    elif raw < 10000:
        price = round(raw / 100) * 100
    else:
        price = round(raw / 200) * 200

    return float(max(price, int(base_fare * 0.5)))


def generate_seat_layout():
    layout = []
    for cabin, cfg in CABIN_LAYOUT.items():
        for row in cfg["rows"]:
            for label in cfg["labels"]:
                layout.append({"seat_number": f"{row}{label}", "cabin_class": cabin})
    return layout


def ensure_seat_inventory(db: Session, flight: FlightCache):
    existing = db.query(SeatInventory).filter(SeatInventory.flight_id == flight.id).first()
    if existing:
        return

    layout = generate_seat_layout()
    random.seed(hash(flight.flight_number))
    simulated_blocks = set(random.sample(range(len(layout)), k=int(len(layout) * 0.08)))

    for idx, seat in enumerate(layout):
        db.add(
            SeatInventory(
                flight_id=flight.id,
                seat_number=seat["seat_number"],
                cabin_class=seat["cabin_class"],
                is_reserved=idx in simulated_blocks,
                reservation_source="SIMULATOR" if idx in simulated_blocks else "AVAILABLE",
            )
        )

    flight.seats_total = len(layout)
    flight.seats_left = len(layout) - len(simulated_blocks)
    db.commit()


def sync_seat_counters(db: Session, flight: FlightCache):
    available = (
        db.query(func.count(SeatInventory.id))
        .filter(SeatInventory.flight_id == flight.id, SeatInventory.is_reserved.is_(False))
        .scalar()
    )
    total = (
        db.query(func.count(SeatInventory.id))
        .filter(SeatInventory.flight_id == flight.id)
        .scalar()
    )
    flight.seats_left = available or 0
    flight.seats_total = total or flight.seats_total
    flight.last_updated = datetime.utcnow()


def build_price_buckets(db: Session, flight: FlightCache) -> List[PricingTier]:
    buckets: List[PricingTier] = []
    for cabin, meta in PRICING_MULTIPLIERS.items():
        seats_left = (
            db.query(func.count(SeatInventory.id))
            .filter(
                SeatInventory.flight_id == flight.id,
                SeatInventory.cabin_class == cabin,
                SeatInventory.is_reserved.is_(False),
            )
            .scalar()
        )
        if not seats_left:
            continue
        seat_price = compute_price(
            flight.base_fare,
            flight.seats_left,
            flight.seats_total,
            flight.demand_score,
            flight.date,
            tier_multiplier=meta["multiplier"],
        )
        buckets.append(
            PricingTier(cabin_class=cabin, seats_left=seats_left, seat_price=seat_price)
        )
    return buckets


def ensure_flight_cache(
    db: Session,
    flight_number: str,
    date: str,
    origin: str,
    destination: str,
    airline_name: str | None = None,
) -> FlightCache:
    flight = (
        db.query(FlightCache)
        .filter_by(flight_number=flight_number, date=date, origin=origin, destination=destination)
        .first()
    )
    if flight:
        if airline_name and flight.airline != airline_name:
            flight.airline = airline_name
            db.commit()
        ensure_seat_inventory(db, flight)
        return flight

    base = 3000.0 + (abs(hash(flight_number)) % 4000)
    flight = FlightCache(
        flight_number=flight_number,
        origin=origin,
        destination=destination,
        date=date,
        base_fare=round(base, 2),
        seats_total=180,
        seats_left=180,
        demand_score=round(random.uniform(0.1, 0.45), 3),
        airline=airline_name,
    )
    db.add(flight)
    db.commit()
    ensure_seat_inventory(db, flight)

    price = compute_price(
        flight.base_fare, flight.seats_left, flight.seats_total, flight.demand_score, flight.date
    )
    db.add(FareHistory(flight_id=flight.id, price=price))
    db.commit()
    return flight


def aero_flights_by_airport(origin: str, date: str):
    from_time = f"{date}T00:00"
    to_time = f"{date}T23:59"
    url = f"{BASE_URL}/flights/airports/icao/{origin}/{from_time}/{to_time}"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"AeroDataBox error {resp.status_code}")
    return resp.json()


def serialize_booking(booking: Booking) -> BookingDetail:
    try:
        passengers = [PassengerInfo(**p) for p in json.loads(booking.passenger_manifest or "[]")]
    except json.JSONDecodeError:
        passengers = []

    seats = [
        {"seat_number": seat.seat_number, "cabin_class": seat.cabin_class}
        for seat in booking.seats
    ]

    return BookingDetail(
        id=booking.id,
        pnr=booking.pnr,
        status=booking.status,
        payment_status=booking.payment_status,
        total_amount=booking.total_amount or booking.price,
        currency=booking.currency or "INR",
        passengers=passengers,
        seats=seats,
        flight_number=booking.flight_number,
        origin=booking.origin,
        destination=booking.destination,
        date=booking.date,
        hold_expires_at=booking.hold_expires_at,
        created_at=booking.created_at,
        updated_at=booking.updated_at,
        payment_reference=booking.payment_reference,
    )


def acquire_sqlite_lock(session: Session):
    session.execute(text("BEGIN IMMEDIATE"))


def generate_pnr(session: Session) -> str:
    alphabet = string.ascii_uppercase
    digits = string.digits
    for _ in range(5):
        candidate = "".join(random.choices(alphabet, k=3)) + "".join(random.choices(digits, k=3))
        exists = session.query(Booking).filter(Booking.pnr == candidate).first()
        if not exists:
            return candidate
    return f"PNR{int(datetime.utcnow().timestamp())}"


def release_booking_seats(session: Session, booking: Booking):
    if not booking.flight_cache_id:
        return 0
    released = 0
    seat_rows = (
        session.query(SeatInventory)
        .filter(
            SeatInventory.flight_id == booking.flight_cache_id,
            SeatInventory.reserved_by_booking_id == booking.id,
        )
        .all()
    )
    for seat in seat_rows:
        seat.is_reserved = False
        seat.reserved_by_booking_id = None
        seat.reservation_source = "AVAILABLE"
        released += 1
    if booking.flight:
        booking.flight.seats_left = max(0, (booking.flight.seats_left or 0) + released)
    return released


def simulator_random_shift(val: float) -> float:
    return clamp(val + random.uniform(-0.04, 0.08), 0.0, 1.0)


async def simulator_loop():
    while True:
        try:
            db = SessionLocal()
            flights = db.query(FlightCache).all()
            for flight in flights:
                ensure_seat_inventory(db, flight)
                flight.demand_score = simulator_random_shift(flight.demand_score)

                available_seats = (
                    db.query(SeatInventory)
                    .filter(SeatInventory.flight_id == flight.id, SeatInventory.is_reserved.is_(False))
                    .all()
                )
                if available_seats and random.random() < 0.25:
                    seat = random.choice(available_seats)
                    seat.is_reserved = True
                    seat.reservation_source = "SIMULATOR"

                simulator_held = (
                    db.query(SeatInventory)
                    .filter(
                        SeatInventory.flight_id == flight.id,
                        SeatInventory.reservation_source == "SIMULATOR",
                        SeatInventory.is_reserved.is_(True),
                    )
                    .all()
                )
                if simulator_held and random.random() < 0.15:
                    seat = random.choice(simulator_held)
                    seat.is_reserved = False
                    seat.reservation_source = "AVAILABLE"

                sync_seat_counters(db, flight)
                price = compute_price(
                    flight.base_fare,
                    flight.seats_left,
                    flight.seats_total,
                    flight.demand_score,
                    flight.date,
                )
                db.add(FareHistory(flight_id=flight.id, price=price))
            db.commit()
            db.close()
        except Exception as exc:
            print("Simulator error", exc)
        await asyncio.sleep(SIM_LOOP)


@app.on_event("startup")
async def start_background_tasks():
    asyncio.create_task(simulator_loop())


@app.get("/api/flights/search", response_model=FlightSearchResponse)
def search_flights(
    origin: str = Query(..., description="Origin ICAO code e.g. VIDP"),
    destination: str = Query(..., description="Destination ICAO code e.g. VABB"),
    date: str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    api = aero_flights_by_airport(origin, date)
    departures = api.get("departures", [])
    results: List[FlightOut] = []
    for flight in departures:
        dest = flight.get("arrival", {}).get("airport", {}).get("icao", "")
        if not dest or dest.upper() != destination.upper():
            continue
        flight_num = flight.get("number") or flight.get("callsign") or "N/A"
        dep_time = flight.get("departure", {}).get("scheduledTimeLocal")
        arr_time = flight.get("arrival", {}).get("scheduledTimeLocal")

        cache = ensure_flight_cache(
            db,
            flight_num,
            date,
            origin,
            dest,
            flight.get("airline", {}).get("name"),
        )
        price = compute_price(
            cache.base_fare, cache.seats_left, cache.seats_total, cache.demand_score, cache.date
        )
        buckets = build_price_buckets(db, cache)
        results.append(
            FlightOut(
                flight_id=cache.id,
                flight_number=flight_num,
                airline=cache.airline,
                origin=origin,
                destination=destination,
                departure_time=dep_time,
                arrival_time=arr_time,
                price=price,
                seats_left=cache.seats_left,
                seats_total=cache.seats_total,
                demand_score=round(cache.demand_score, 3),
                price_buckets=buckets,
            )
        )
    return FlightSearchResponse(total=len(results), flights=results)


@app.get("/api/flights/{flight_id}/seats", response_model=List[SeatInfo])
def seat_map(flight_id: int, db: Session = Depends(get_db)):
    flight = db.query(FlightCache).get(flight_id)
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")
    ensure_seat_inventory(db, flight)
    sync_seat_counters(db, flight)

    seats = (
        db.query(SeatInventory)
        .filter(SeatInventory.flight_id == flight.id)
        .order_by(SeatInventory.cabin_class.desc(), SeatInventory.seat_number)
        .all()
    )

    seat_infos: List[SeatInfo] = []
    for seat in seats:
        multiplier = PRICING_MULTIPLIERS.get(seat.cabin_class, {"multiplier": 1.0})["multiplier"]
        seat_price = compute_price(
            flight.base_fare,
            flight.seats_left,
            flight.seats_total,
            flight.demand_score,
            flight.date,
            tier_multiplier=multiplier,
        )
        seat_infos.append(
            SeatInfo(
                seat_number=seat.seat_number,
                cabin_class=seat.cabin_class,
                is_reserved=seat.is_reserved,
                reservation_source=seat.reservation_source,
                price=seat_price,
            )
        )
    return seat_infos


@app.post("/api/bookings/hold", response_model=BookingHoldResponse, status_code=status.HTTP_201_CREATED)
def hold_booking(payload: BookingHoldRequest, db: Session = Depends(get_db)):
    flight = db.query(FlightCache).get(payload.flight_id)
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")

    ensure_seat_inventory(db, flight)

    if len(payload.passengers) != len(payload.seats):
        raise HTTPException(status_code=400, detail="Passenger and seat count must match")

    acquire_sqlite_lock(db)

    seat_numbers = [seat.seat_number for seat in payload.seats]
    inventory_rows = (
        db.query(SeatInventory)
        .filter(
            SeatInventory.flight_id == flight.id,
            SeatInventory.seat_number.in_(seat_numbers),
        )
        .all()
    )
    if len(inventory_rows) != len(seat_numbers):
        raise HTTPException(status_code=404, detail="One or more seats not found")

    blocked = [seat for seat in inventory_rows if seat.is_reserved]
    if blocked:
        raise HTTPException(status_code=409, detail=f"Seat {blocked[0].seat_number} already reserved")

    hold_minutes = clamp(payload.hold_minutes, 5, 60)
    hold_expires_at = datetime.utcnow() + timedelta(minutes=hold_minutes)

    booking = Booking(
        user_name=payload.contact_name,
        email=payload.contact_email,
        contact_phone=payload.contact_phone,
        flight_number=flight.flight_number,
        flight_cache_id=flight.id,
        origin=flight.origin,
        destination=flight.destination,
        date=flight.date,
        passengers=len(payload.passengers),
        passenger_manifest=json.dumps([p.dict() for p in payload.passengers]),
        status="HOLD",
        payment_status="PENDING",
        currency=payload.currency,
        hold_expires_at=hold_expires_at,
    )

    seats_left_tracker = flight.seats_left
    total_amount = 0.0
    for req_seat in payload.seats:
        multiplier = PRICING_MULTIPLIERS.get(req_seat.cabin_class, {"multiplier": 1.0})["multiplier"]
        seat_price = compute_price(
            flight.base_fare,
            seats_left_tracker,
            flight.seats_total,
            flight.demand_score,
            flight.date,
            tier_multiplier=multiplier,
        )
        seats_left_tracker = max(0, seats_left_tracker - 1)
        total_amount += seat_price

    booking.price = total_amount
    booking.total_amount = total_amount

    db.add(booking)
    db.flush()

    for seat in inventory_rows:
        seat.is_reserved = True
        seat.reserved_by_booking_id = booking.id
        seat.reservation_source = "BOOKING"
        db.add(
            SeatAssignment(
                booking_id=booking.id,
                flight_id=flight.id,
                seat_number=seat.seat_number,
                cabin_class=seat.cabin_class,
            )
        )

    flight.seats_left = max(0, flight.seats_left - len(inventory_rows))
    db.commit()

    return BookingHoldResponse(
        booking_id=booking.id,
        status=booking.status,
        total_amount=round(total_amount, 2),
        currency=booking.currency,
        hold_expires_at=booking.hold_expires_at,
        price_breakdown=build_price_buckets(db, flight),
    )


@app.post("/api/bookings/{booking_id}/payment", response_model=PaymentResponse)
def process_payment(booking_id: int, payload: PaymentRequest, db: Session = Depends(get_db)):
    booking = db.query(Booking).get(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.status not in {"HOLD", "PAYMENT_FAILED"}:
        raise HTTPException(status_code=400, detail="Booking is not pending payment")

    if booking.hold_expires_at and booking.hold_expires_at < datetime.utcnow():
        release_booking_seats(db, booking)
        booking.status = "EXPIRED"
        booking.payment_status = "FAILED"
        db.commit()
        raise HTTPException(status_code=400, detail="Hold window expired")

    force = (payload.force_outcome or "").upper()
    if force not in {"SUCCESS", "FAIL", ""}:
        raise HTTPException(status_code=400, detail="force_outcome must be SUCCESS or FAIL")

    success = force == "SUCCESS" or (force == "" and random.random() > 0.25)
    reference = f"SIM-{int(datetime.utcnow().timestamp())}-{random.randint(1000,9999)}"

    booking.payment_attempts = (booking.payment_attempts or 0) + 1

    if success:
        booking.status = "CONFIRMED"
        booking.payment_status = "SUCCESS"
        booking.payment_reference = reference
        booking.pnr = booking.pnr or generate_pnr(db)
        booking.updated_at = datetime.utcnow()
        db.commit()
        return PaymentResponse(
            status="CONFIRMED",
            message="Payment successful",
            pnr=booking.pnr,
            payment_reference=reference,
        )

    released = release_booking_seats(db, booking)
    booking.status = "PAYMENT_FAILED"
    booking.payment_status = "FAILED"
    booking.payment_reference = reference
    booking.updated_at = datetime.utcnow()
    if booking.flight:
        booking.flight.seats_left = max(0, booking.flight.seats_left + released)
    db.commit()
    raise HTTPException(status_code=402, detail="Payment failed � seats released")


@app.post("/api/bookings/{booking_id}/cancel", response_model=CancellationResponse)
def cancel_booking(booking_id: int, db: Session = Depends(get_db)):
    booking = db.query(Booking).get(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.status in {"CANCELLED", "EXPIRED"}:
        return CancellationResponse(status=booking.status, message="Booking already closed")

    release_booking_seats(db, booking)
    booking.status = "CANCELLED"
    if booking.payment_status == "SUCCESS":
        booking.payment_status = "REFUNDED"
    booking.updated_at = datetime.utcnow()
    db.commit()

    return CancellationResponse(status=booking.status, message="Booking cancelled")


@app.get("/api/bookings", response_model=BookingHistoryResponse)
@app.get("/api/bookings/history", response_model=BookingHistoryResponse)
def list_bookings(email: str | None = Query(default=None), db: Session = Depends(get_db)):
    query = db.query(Booking)
    if email:
        query = query.filter(Booking.email == email)
    bookings = query.order_by(Booking.created_at.desc()).all()
    payload = [serialize_booking(booking) for booking in bookings]
    return BookingHistoryResponse(count=len(payload), bookings=payload)


@app.get("/api/bookings/{booking_id}", response_model=BookingDetail)
def booking_detail(booking_id: int, db: Session = Depends(get_db)):
    booking = db.query(Booking).get(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return serialize_booking(booking)


@app.get("/api/fare-history/{flight_number}/{date}", response_model=FareHistoryOut)
def fare_history(flight_number: str, date: str, db: Session = Depends(get_db)):
    flight = db.query(FlightCache).filter_by(flight_number=flight_number, date=date).first()
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not tracked")
    points = [FarePoint(timestamp=fh.timestamp, price=fh.price) for fh in flight.fares]
    return FareHistoryOut(flight_number=flight_number, date=date, history=points)
