from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Float, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"


class LockStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    RELEASED = "released"
    CONVERTED = "converted"


class BookingStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    ABNORMAL = "abnormal"


class AppealType(str, enum.Enum):
    NO_SHOW = "no_show"
    ABNORMAL = "abnormal"
    DUPLICATE_BOOKING = "duplicate_booking"
    BLACKLIST = "blacklist"


class AppealStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class WaitlistStatus(str, enum.Enum):
    PENDING = "pending"
    NOTIFIED = "notified"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    real_name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False, default=UserRole.EXECUTOR)
    phone = Column(String(20))
    email = Column(String(100))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    locks = relationship("Lock", back_populates="user", foreign_keys="Lock.user_id", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="user", foreign_keys="Booking.user_id", cascade="all, delete-orphan")
    blacklist_records = relationship("Blacklist", back_populates="user", foreign_keys="Blacklist.user_id", cascade="all, delete-orphan")
    appeals = relationship("Appeal", back_populates="user", foreign_keys="Appeal.user_id", cascade="all, delete-orphan")
    waitlist_entries = relationship("WaitlistEntry", back_populates="user", foreign_keys="WaitlistEntry.user_id", cascade="all, delete-orphan")


class PracticeRoom(Base):
    __tablename__ = "practice_rooms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    location = Column(String(200))
    capacity = Column(Integer, default=1)
    equipment = Column(Text)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    time_slots = relationship("TimeSlot", back_populates="room", cascade="all, delete-orphan")
    locks = relationship("Lock", back_populates="room", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="room", cascade="all, delete-orphan")
    waitlist_entries = relationship("WaitlistEntry", back_populates="room", cascade="all, delete-orphan")


class TimeSlot(Base):
    __tablename__ = "time_slots"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("practice_rooms.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)
    start_time = Column(String(5), nullable=False)
    end_time = Column(String(5), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    room = relationship("PracticeRoom", back_populates="time_slots")


class BookingRule(Base):
    __tablename__ = "booking_rules"

    id = Column(Integer, primary_key=True, index=True)
    lock_duration_minutes = Column(Integer, default=15)
    max_booking_hours = Column(Float, default=4)
    min_booking_hours = Column(Float, default=0.5)
    max_daily_bookings = Column(Integer, default=2)
    advance_booking_days = Column(Integer, default=7)
    no_show_threshold = Column(Integer, default=3)
    auto_release_minutes = Column(Integer, default=15)
    waitlist_confirm_minutes = Column(Integer, default=15)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Blacklist(Base):
    __tablename__ = "blacklist"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason = Column(Text, nullable=False)
    added_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="blacklist_records", foreign_keys=[user_id])
    admin = relationship("User", foreign_keys=[added_by])


class Lock(Base):
    __tablename__ = "locks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("practice_rooms.id"), nullable=False)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False, index=True)
    status = Column(String(20), nullable=False, default=LockStatus.ACTIVE)
    expires_at = Column(DateTime, nullable=False)
    extended_count = Column(Integer, default=0)
    max_extensions = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    released_at = Column(DateTime)
    release_reason = Column(String(100))

    user = relationship("User", back_populates="locks")
    room = relationship("PracticeRoom", back_populates="locks")
    booking = relationship("Booking", back_populates="lock", uselist=False)


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("practice_rooms.id"), nullable=False)
    lock_id = Column(Integer, ForeignKey("locks.id"))
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False, index=True)
    status = Column(String(20), nullable=False, default=BookingStatus.PENDING)
    purpose = Column(Text)
    check_in_time = Column(DateTime)
    check_out_time = Column(DateTime)
    cancelled_at = Column(DateTime)
    cancel_reason = Column(Text)
    reviewer_id = Column(Integer, ForeignKey("users.id"))
    reviewer_note = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="bookings", foreign_keys=[user_id])
    room = relationship("PracticeRoom", back_populates="bookings")
    lock = relationship("Lock", back_populates="booking")
    reviewer = relationship("User", foreign_keys=[reviewer_id])
    abnormal_records = relationship("AbnormalRecord", back_populates="booking", cascade="all, delete-orphan")
    feedback = relationship("Feedback", back_populates="booking", uselist=False, cascade="all, delete-orphan")


class AbnormalRecord(Base):
    __tablename__ = "abnormal_records"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    reporter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    abnormal_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=False)
    is_confirmed = Column(Boolean, default=False)
    confirmed_by = Column(Integer, ForeignKey("users.id"))
    confirmed_at = Column(DateTime)
    handling_result = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    booking = relationship("Booking", back_populates="abnormal_records")
    reporter = relationship("User", foreign_keys=[reporter_id])
    confirmer = relationship("User", foreign_keys=[confirmed_by])


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("practice_rooms.id"), nullable=False)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False, index=True)
    reason = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default=WaitlistStatus.PENDING)
    notified_at = Column(DateTime)
    confirm_deadline = Column(DateTime)
    confirmed_at = Column(DateTime)
    cancelled_at = Column(DateTime)
    cancel_reason = Column(Text)
    booking_id = Column(Integer, ForeignKey("bookings.id"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="waitlist_entries", foreign_keys=[user_id])
    room = relationship("PracticeRoom", back_populates="waitlist_entries")
    booking = relationship("Booking", foreign_keys=[booking_id])


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    operation_type = Column(String(50), nullable=False)
    target_type = Column(String(50))
    target_id = Column(Integer)
    detail = Column(Text)
    ip_address = Column(String(50))
    user_agent = Column(String(255))
    created_at = Column(DateTime, server_default=func.now(), index=True)

    operator = relationship("User", foreign_keys=[user_id])


class FeedbackStatus(str, enum.Enum):
    PENDING = "pending"
    HANDLED = "handled"


class Feedback(Base):
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    check_out_time = Column(DateTime, nullable=False)
    actual_usage = Column(Text)
    equipment_rating = Column(Integer, nullable=False)
    environment_rating = Column(Integer, nullable=False)
    overall_rating = Column(Integer, nullable=False)
    problem_description = Column(Text)
    needs_follow_up = Column(Boolean, default=False)
    status = Column(String(20), nullable=False, default=FeedbackStatus.PENDING)
    handled_by = Column(Integer, ForeignKey("users.id"))
    handled_at = Column(DateTime)
    handling_result = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    booking = relationship("Booking", back_populates="feedback")
    user = relationship("User", foreign_keys=[user_id])
    handler = relationship("User", foreign_keys=[handled_by])


class Appeal(Base):
    __tablename__ = "appeals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    appeal_type = Column(String(50), nullable=False)
    target_type = Column(String(50), nullable=False)
    target_id = Column(Integer, nullable=False)
    reason = Column(Text, nullable=False)
    supplement = Column(Text)
    status = Column(String(20), nullable=False, default=AppealStatus.PENDING)
    reviewer_id = Column(Integer, ForeignKey("users.id"))
    review_opinion = Column(Text)
    reviewed_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="appeals", foreign_keys=[user_id])
    reviewer = relationship("User", foreign_keys=[reviewer_id])
