from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .db import Base


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(120), nullable=True)
    filename = Column(String(255), nullable=True)
    rows_received = Column(Integer, default=0)
    rows_accepted = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    listings = relationship("Listing", back_populates="run", cascade="all, delete-orphan")


class Listing(Base):
    __tablename__ = "listings"
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("ingestion_runs.id"), index=True)
    listing_id = Column(String(64), index=True)
    list_price = Column(Float, default=0)
    beds = Column(Float, default=0)
    baths = Column(Float, default=0)
    sqft = Column(Float, default=0)
    dom = Column(Integer, default=0)
    condition = Column(String(64), default="")
    remarks = Column(Text, default="")

    score = Column(Float, default=0)
    bucket = Column(String(32), default="skip")
    ai_risk_count = Column(Integer, default=0)
    ai_upside_count = Column(Integer, default=0)
    ai_summary = Column(Text, nullable=True)

    run = relationship("IngestionRun", back_populates="listings")


class ScorecardConfig(Base):
    __tablename__ = "scorecard_configs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), default="default")
    ppsf_low_bonus = Column(Float, default=12)
    ppsf_mid_bonus = Column(Float, default=6)
    dom_low_bonus = Column(Float, default=6)
    dom_mid_bonus = Column(Float, default=3)
    dom_high_penalty = Column(Float, default=3)
    condition_good_bonus = Column(Float, default=8)
    condition_fair_penalty = Column(Float, default=6)
    ai_upside_bonus = Column(Float, default=2)
    ai_risk_penalty = Column(Float, default=2.5)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FeedbackLabel(Base):
    __tablename__ = "feedback_labels"
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("ingestion_runs.id"), index=True)
    listing_id = Column(String(64), index=True)
    label = Column(String(32), index=True)  # good_lead|false_positive|false_negative
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
