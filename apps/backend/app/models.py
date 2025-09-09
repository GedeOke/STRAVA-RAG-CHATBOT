from sqlalchemy import Column, Integer, Float, String, ForeignKey, TIMESTAMP, func
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from .db import Base

class Athlete(Base):
    __tablename__ = "athletes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    firstname = Column(String, nullable=True)
    lastname = Column(String, nullable=True)

    activities = relationship("Activity", back_populates="athlete")

class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"))
    name = Column(String)
    sport_type = Column(String)
    distance_m = Column(Float)
    moving_time_s = Column(Integer)
    elapsed_time_s = Column(Integer)
    elev_gain_m = Column(Float)
    created_at = Column(TIMESTAMP, server_default=func.now())

    embedding = Column(Vector(768))  # embedding langsung di sini

    athlete = relationship("Athlete", back_populates="activities")
