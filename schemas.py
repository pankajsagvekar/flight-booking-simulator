from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class PricingTier(BaseModel):
    cabin_class: str
    seats_left: int
    seat_price: float


class FlightOut(BaseModel):
    flight_id: int
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
    price_buckets: List[PricingTier] = Field(default_factory=list)


class FlightSearchResponse(BaseModel):
    total: int
    flights: List[FlightOut] = Field(default_factory=list)


class SeatInfo(BaseModel):
    seat_number: str
    cabin_class: str
    is_reserved: bool
    reservation_source: str
    price: float


class PassengerInfo(BaseModel):
    full_name: str
    age: Optional[int] = None
    gender: Optional[str] = None


class SeatSelection(BaseModel):
    seat_number: str
    cabin_class: str


class BookingHoldRequest(BaseModel):
    flight_id: int
    contact_name: str
    contact_email: str
    contact_phone: Optional[str] = None
    passengers: List[PassengerInfo]
    seats: List[SeatSelection]
    currency: str = "INR"
    hold_minutes: int = Field(default=15, ge=5, le=60)


class BookingHoldResponse(BaseModel):
    booking_id: int
    status: str
    total_amount: float
    currency: str
    hold_expires_at: Optional[datetime]
    price_breakdown: List[PricingTier] = Field(default_factory=list)


class BookingSeat(BaseModel):
    seat_number: str
    cabin_class: str


class BookingDetail(BaseModel):
    id: int
    pnr: Optional[str]
    status: str
    payment_status: str
    total_amount: float
    currency: str
    passengers: List[PassengerInfo] = Field(default_factory=list)
    seats: List[BookingSeat] = Field(default_factory=list)
    flight_number: str
    origin: str
    destination: str
    date: str
    hold_expires_at: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    payment_reference: Optional[str]


class PaymentRequest(BaseModel):
    payment_method: str = "SIMULATED"
    force_outcome: Optional[str] = Field(
        default=None, description="Force payment result: SUCCESS or FAIL"
    )


class PaymentResponse(BaseModel):
    status: str
    message: str
    pnr: Optional[str]
    payment_reference: Optional[str]


class CancellationResponse(BaseModel):
    status: str
    message: str


class BookingHistoryResponse(BaseModel):
    count: int
    bookings: List[BookingDetail] = Field(default_factory=list)


class FarePoint(BaseModel):
    timestamp: datetime
    price: float


class FareHistoryOut(BaseModel):
    flight_number: str
    date: str
    history: List[FarePoint]
