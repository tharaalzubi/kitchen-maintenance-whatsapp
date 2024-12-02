# app/database/DatabaseIntegration.py
from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from sqlalchemy import and_, or_, not_, case, text, Boolean, String
from sqlalchemy.sql.expression import true, false
from typing import Optional, Dict, Any, Union
from enum import Enum
import json
import os

# Get database URL from environment variable or use default
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./kitchen_maintenance.db"
)

# Create engine with proper SQLite URL handling
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Rest of your code remains the same
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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)

class DatabaseOperations:
    @staticmethod
    def get_customer_session(db: Session, phone_number: str) -> Optional[CustomerSession]:
        try:
            # Use scalar() to get a single result or None
            session = db.query(CustomerSession).filter(
                CustomerSession.phone_number == phone_number
            ).scalar()

            # Now session is either None or a CustomerSession object
            if session is not None:
                if not isinstance(session.session_data, dict):
                    session.session_data = {}
                    db.commit()

            return session
        except Exception as e:
            print(f"Error getting customer session: {str(e)}")
            return None


    @staticmethod
    def update_customer_session(
        db: Session, 
        phone_number: str, 
        session_data: Dict[str, Any],
        language: str
    ) -> CustomerSession:
        try:
            # Use scalar() instead of first()
            session = db.query(CustomerSession).filter(
                CustomerSession.phone_number == phone_number
            ).scalar()

            if session is not None:
                # Update existing session with type validation
                session.session_data = session_data if isinstance(session_data, dict) else {}
                session.language = language if isinstance(language, str) else "en"
            else:
                # Create new session with validated types
                session = CustomerSession(
                    phone_number=phone_number,
                    session_data=session_data if isinstance(session_data, dict) else {},
                    language=language if isinstance(language, str) else "en"
                )
                db.add(session)

            db.commit()
            db.refresh(session)
            return session
        except Exception as e:
            db.rollback()
            raise e

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