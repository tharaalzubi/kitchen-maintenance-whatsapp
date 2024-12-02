# DatabaseIntegration.py
from typing import Generator, TypedDict, Optional, Dict, Any, Union, List, Type, TypeVar, NotRequired
from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from sqlalchemy.orm import Session as SASession
from sqlalchemy import and_, or_, not_, case, text, Boolean
from sqlalchemy.sql.expression import true, false
from enum import Enum
import json
import os

# Define the session data type
class SessionData(TypedDict, total=False):
    """Session data type definition"""
    state: NotRequired[str]
    name: NotRequired[str]
    equipment: NotRequired[str]
    problem: NotRequired[str]
    schedule: NotRequired[str]
    photos: NotRequired[List[str]]
    contact_phone: NotRequired[str]
    latitude: NotRequired[str]
    longitude: NotRequired[str]
    location_name: NotRequired[str]

# Define the Supabase connection URL
SQLALCHEMY_DATABASE_URL = "postgresql://postgres.oblbsmcqjoyfpnrlaacm:ZTk1PlGDMAW3omIM@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"

# Create the SQLAlchemy engine with proper configuration for Supabase
# Configure the engine with pooler-specific settings
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=20,
    max_overflow=0,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={
        "options": "-c timezone=utc",
        "application_name": "kitchen_maintenance_bot"
    }
)

Base = declarative_base()

class RequestStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    DIAGNOSED = "diagnosed"
    QUOTED = "quoted"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

class CustomerSession(Base):
    __tablename__ = "customer_sessions"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, unique=True, index=True)
    session_data = Column(JSON)
    language = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class MaintenanceRequest(Base):
    __tablename__ = "maintenance_requests"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String)
    phone_number = Column(String)
    equipment_type = Column(String)
    problem_description = Column(String)
    preferred_time = Column(String)
    status = Column(SQLEnum(RequestStatus))
    photos = Column(JSON)
    # Add location fields
    latitude = Column(String)
    longitude = Column(String)
    location_name = Column(String)  # Address or place name from WhatsApp
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db() -> None:
    Base.metadata.create_all(bind=engine)

class DatabaseOperations:
    @staticmethod
    def get_customer_session(db: Session, phone_number: str) -> Optional[CustomerSession]:
        return db.query(CustomerSession).filter(CustomerSession.phone_number == phone_number).first()

    @staticmethod
    def update_customer_session(
        db: Session, 
        phone_number: str, 
        session_data: Dict[str, Any],
        language: str
    ) -> CustomerSession:
        session = (
            db.query(CustomerSession)
            .filter(CustomerSession.phone_number == phone_number)
            .first()
        )

        if session is None:
            session = CustomerSession(
                phone_number=phone_number,
                session_data=session_data,
                language=language
            )
            db.add(session)
        else:
            session.session_data = session_data
            session.language = language
            session.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def delete_customer_session(db: Session, phone_number: str) -> bool:
        session = DatabaseOperations.get_customer_session(db, phone_number)
        if session:
            db.delete(session)
            db.commit()
            return True
        return False

    @staticmethod
    def create_maintenance_request(
        db: Session, 
        request_data: Dict[str, Any]
    ) -> MaintenanceRequest:
        request = MaintenanceRequest(**request_data)
        db.add(request)
        db.commit()
        db.refresh(request)
        return request

    @staticmethod
    def get_maintenance_request(
        db: Session, 
        request_id: int
    ) -> Optional[MaintenanceRequest]:
        return db.query(MaintenanceRequest).filter(MaintenanceRequest.id == request_id).first()

    @staticmethod
    def update_maintenance_request(
        db: Session,
        request_id: int,
        update_data: Dict[str, Any]
    ) -> Optional[MaintenanceRequest]:
        request = DatabaseOperations.get_maintenance_request(db, request_id)
        if request:
            for key, value in update_data.items():
                setattr(request, key, value)
            request.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(request)
        return request

def test_database_connection():
    """Test the database connection and print detailed information"""
    try:
        # Create a test connection
        test_conn = engine.connect()

        # Try a simple query
        result = test_conn.execute(text("SELECT version();")).scalar()

        print(f"Successfully connected to database")
        print(f"PostgreSQL version: {result}")

        # Close the test connection
        test_conn.close()
        return True

    except Exception as e:
        print(f"Error connecting to database: {str(e)}")
        import traceback
        traceback.print_exc()
        return False