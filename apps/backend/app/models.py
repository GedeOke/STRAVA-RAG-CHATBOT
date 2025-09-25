from sqlalchemy import (
    Column, Integer, Float, String, ForeignKey,
    TIMESTAMP, func, Index
)
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from .db import Base


class Athlete(Base):
    __tablename__ = "athletes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    firstname = Column(String(100), nullable=True)
    lastname = Column(String(100), nullable=True)

    # Relationship
    activities = relationship(
        "Activity",
        back_populates="athlete",
        cascade="all, delete-orphan"
    )


class Club(Base):
    __tablename__ = "clubs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strava_id = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)

    # Relationship
    activities = relationship(
        "Activity",
        back_populates="club",
        cascade="all, delete-orphan"
    )


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strava_id = Column(String(64), unique=True, index=True, nullable=False)

    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False, index=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True, index=True)

    name = Column(String(255), nullable=False)  # Judul aktivitas
    sport_type = Column(String(50), nullable=False)  # Run, Ride, Swim, dll.

    distance_m = Column(Float, nullable=False)  # meter
    moving_time_s = Column(Integer, nullable=False)  # detik
    elapsed_time_s = Column(Integer, nullable=False)  # detik
    elev_gain_m = Column(Float, nullable=True)

    date = Column(TIMESTAMP(timezone=True), nullable=False)  # start_date_local dari Strava
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    # Embedding untuk semantic search
    embedding = Column(Vector(768))

    # Relationships
    athlete = relationship("Athlete", back_populates="activities")
    club = relationship("Club", back_populates="activities")

    __table_args__ = (
        Index("idx_activities_date", "date"),
        Index("idx_activities_athlete_id", "athlete_id"),
        Index("idx_activities_club_id", "club_id"),
        Index("idx_activities_sport_type", "sport_type"),
    )
