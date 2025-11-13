from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Date
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    user_name = Column(String, index=True)
    email = Column(String, index=True)
    flight_number = Column(String)
    origin = Column(String)
    destination = Column(String)
    date = Column(String)  # YYYY-MM-DD
    price = Column(Float)
    passengers = Column(Integer)

class FlightCache(Base):
    """
    Local cache of flights we serve prices for.
    Keyed by flight_number + date + origin + destination to be unique enough.
    """
    __tablename__ = "flight_cache"
    id = Column(Integer, primary_key=True, index=True)
    flight_number = Column(String, index=True)
    origin = Column(String, index=True)
    destination = Column(String, index=True)
    date = Column(String, index=True)  # YYYY-MM-DD
    base_fare = Column(Float, default=3000.0)
    seats_total = Column(Integer, default=120)
    seats_left = Column(Integer, default=120)
    demand_score = Column(Float, default=0.2)  # 0.0..1.0
    last_updated = Column(DateTime, default=datetime.utcnow)

    fares = relationship("FareHistory", back_populates="flight")

class FareHistory(Base):
    __tablename__ = "fare_history"
    id = Column(Integer, primary_key=True, index=True)
    flight_id = Column(Integer, ForeignKey("flight_cache.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    price = Column(Float)

    flight = relationship("FlightCache", back_populates="fares")
