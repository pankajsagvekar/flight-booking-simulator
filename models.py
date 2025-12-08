from datetime import datetime
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)  # In a real application, this should be hashed!
    full_name = Column(String)
    role = Column(String, default="user")  # 'user' or 'admin'

    bookings = relationship("Booking", back_populates="user")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    email = Column(String, index=True)
    contact_phone = Column(String, nullable=True)
    flight_number = Column(String, index=True)
    flight_cache_id = Column(Integer, ForeignKey("flight_cache.id"), nullable=True)
    origin = Column(String)
    destination = Column(String)
    date = Column(String)  # YYYY-MM-DD
    price = Column(Float, default=0.0)
    total_amount = Column(Float, default=0.0)
    passengers = Column(Integer, default=1)
    passenger_manifest = Column(Text, nullable=True)
    pnr = Column(String, index=True, unique=True, nullable=True)
    status = Column(String, default="HOLD")  # HOLD, CONFIRMED, CANCELLED, FAILED
    payment_status = Column(String, default="PENDING")
    payment_reference = Column(String, nullable=True)
    currency = Column(String, default="INR")
    payment_attempts = Column(Integer, default=0)
    hold_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="bookings")
    flight = relationship("FlightCache", back_populates="bookings")
    seats = relationship(
        "SeatAssignment", back_populates="booking", cascade="all, delete-orphan"
    )


class FlightCache(Base):
    """Local cache of flights and pricing metadata."""

    __tablename__ = "flight_cache"

    id = Column(Integer, primary_key=True, index=True)
    flight_number = Column(String, index=True)
    airline = Column(String, nullable=True)
    origin = Column(String, index=True)
    destination = Column(String, index=True)
    date = Column(String, index=True)  # YYYY-MM-DD
    base_fare = Column(Float, default=3000.0)
    seats_total = Column(Integer, default=180)
    seats_left = Column(Integer, default=180)
    demand_score = Column(Float, default=0.2)  # 0.0..1.0
    last_updated = Column(DateTime, default=datetime.utcnow)

    fares = relationship("FareHistory", back_populates="flight", cascade="all")
    seats = relationship(
        "SeatInventory", back_populates="flight", cascade="all, delete-orphan"
    )
    bookings = relationship("Booking", back_populates="flight")


class FareHistory(Base):
    __tablename__ = "fare_history"

    id = Column(Integer, primary_key=True, index=True)
    flight_id = Column(Integer, ForeignKey("flight_cache.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    price = Column(Float)

    flight = relationship("FlightCache", back_populates="fares")


class SeatInventory(Base):
    __tablename__ = "seat_inventory"
    __table_args__ = (UniqueConstraint("flight_id", "seat_number", name="uq_seat"),)

    id = Column(Integer, primary_key=True, index=True)
    flight_id = Column(Integer, ForeignKey("flight_cache.id"), index=True)
    seat_number = Column(String, index=True)
    cabin_class = Column(String)
    is_reserved = Column(Boolean, default=False)
    reservation_source = Column(String, default="AVAILABLE")
    reserved_by_booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True)

    flight = relationship("FlightCache", back_populates="seats")


class SeatAssignment(Base):
    __tablename__ = "seat_assignments"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"))
    flight_id = Column(Integer, ForeignKey("flight_cache.id"))
    seat_number = Column(String)
    cabin_class = Column(String)

    booking = relationship("Booking", back_populates="seats")
