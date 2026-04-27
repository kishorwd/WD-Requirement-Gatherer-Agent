from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship, declarative_base

# Database location
DATABASE_URL = "sqlite:///./data/projects.db"

# Base class for models
Base = declarative_base()

# ------------------------
# Project Table
# ------------------------
class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    client_name = Column(String, unique=True, index=True)
    industry = Column(String, nullable=True)
    sow_text = Column(Text, nullable=True)
    discovery_plan_json = Column(Text, nullable=True)  # Store plan as JSON string
    pre_meeting_brief = Column(Text, nullable=True)    # Stores the generated intelligence brief

    # Relationship to sessions
    sessions = relationship("MeetingSession", back_populates="project", cascade="all, delete-orphan")

# ------------------------
# MeetingSession Table
# ------------------------
class MeetingSession(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    session_number = Column(Integer)
    transcript_text = Column(Text)  # Store the meeting transcript
    mom = Column(Text)  # Minutes of Meeting
    analysis_json = Column(Text)  # Store the full AI analysis

    # Relationships
    project = relationship("Project", back_populates="sessions")
    requirements = relationship("Requirement", back_populates="session", cascade="all, delete-orphan")

# ------------------------
# Requirement Table
# ------------------------
class Requirement(Base):
    __tablename__ = "requirements"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"))
    text = Column(Text, nullable=False)
    module = Column(String)
    status = Column(String, default="Provisional")  # Provisional, Confirmed
    scope_status = Column(String, default="Pending")  # In Scope, Out of Scope...
    scope_justification = Column(Text)

    # Relationship
    session = relationship("MeetingSession", back_populates="requirements")

# ------------------------
# Database Engine & Session
# ------------------------
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ------------------------
# Helper to Create Tables
# ------------------------
def create_db_and_tables():
    Base.metadata.create_all(bind=engine)

# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
