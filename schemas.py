from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class FlightOut(BaseModel):
    flight_number: str
    airline: Optional[str]
    origin: str
    destination: str
    departure_time: Optional[str]
    arrival_time: Optional[str]
    price: float
    seats_left: int
    seats_total: int
    demand_score: float

class BookingCreate(BaseModel):
    user_name: str
    email: str
    flight_number: str
    origin: str
    destination: str
    date: str  # YYYY-MM-DD
    price: float
    passengers: int

class BookingOut(BookingCreate):
    id: int
    class Config:
        orm_mode = True

class FarePoint(BaseModel):
    timestamp: datetime
    price: float

class FareHistoryOut(BaseModel):
    flight_number: str
    date: str
    history: List[FarePoint]
