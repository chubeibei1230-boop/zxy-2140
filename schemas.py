from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, date, time
from models import UserRole, LockStatus, BookingStatus, AppealType, AppealStatus


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    real_name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = None
    email: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, max_length=128)
    role: UserRole = Field(default=UserRole.EXECUTOR, deprecated=True)


class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)
    real_name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = None
    email: Optional[str] = None


class UserUpdate(BaseModel):
    real_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    id: int
    role: UserRole
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class PasswordChange(BaseModel):
    old_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=6, max_length=128)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class LoginRequest(BaseModel):
    username: str
    password: str


class PracticeRoomBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    location: Optional[str] = None
    capacity: int = Field(default=1, ge=1)
    equipment: Optional[str] = None
    description: Optional[str] = None


class PracticeRoomCreate(PracticeRoomBase):
    pass


class PracticeRoomUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    capacity: Optional[int] = Field(default=None, ge=1)
    equipment: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class PracticeRoomResponse(PracticeRoomBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TimeSlotBase(BaseModel):
    room_id: int
    day_of_week: int = Field(..., ge=0, le=6)
    start_time: str = Field(..., pattern=r'^\d{2}:\d{2}$')
    end_time: str = Field(..., pattern=r'^\d{2}:\d{2}$')


class TimeSlotCreate(TimeSlotBase):
    pass


class TimeSlotUpdate(BaseModel):
    day_of_week: Optional[int] = Field(default=None, ge=0, le=6)
    start_time: Optional[str] = Field(default=None, pattern=r'^\d{2}:\d{2}$')
    end_time: Optional[str] = Field(default=None, pattern=r'^\d{2}:\d{2}$')
    is_active: Optional[bool] = None


class TimeSlotResponse(TimeSlotBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class BookingRuleBase(BaseModel):
    lock_duration_minutes: int = Field(default=15, ge=1, le=120)
    max_booking_hours: float = Field(default=4, ge=0.5, le=24)
    min_booking_hours: float = Field(default=0.5, ge=0.25, le=4)
    max_daily_bookings: int = Field(default=2, ge=1, le=10)
    advance_booking_days: int = Field(default=7, ge=1, le=60)
    no_show_threshold: int = Field(default=3, ge=1, le=10)
    auto_release_minutes: int = Field(default=15, ge=5, le=60)


class BookingRuleUpdate(BookingRuleBase):
    pass


class BookingRuleResponse(BookingRuleBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BlacklistBase(BaseModel):
    user_id: int
    reason: str = Field(..., min_length=1)
    start_date: datetime
    end_date: Optional[datetime] = None


class BlacklistCreate(BlacklistBase):
    pass


class BlacklistUpdate(BaseModel):
    reason: Optional[str] = None
    end_date: Optional[datetime] = None
    is_active: Optional[bool] = None


class BlacklistResponse(BaseModel):
    id: int
    user_id: int
    user_name: str
    reason: str
    added_by_name: str
    start_date: datetime
    end_date: Optional[datetime]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class LockCreate(BaseModel):
    room_id: int
    start_time: datetime
    end_time: datetime

    @field_validator('end_time')
    @classmethod
    def end_after_start(cls, v, info):
        if 'start_time' in info.data and v <= info.data['start_time']:
            raise ValueError('end_time must be after start_time')
        return v


class LockExtend(BaseModel):
    extend_minutes: int = Field(default=15, ge=5, le=60)


class LockResponse(BaseModel):
    id: int
    user_id: int
    user_name: str
    room_id: int
    room_name: str
    start_time: datetime
    end_time: datetime
    status: LockStatus
    expires_at: datetime
    extended_count: int
    max_extensions: int
    created_at: datetime
    is_expired: bool
    remaining_seconds: int

    class Config:
        from_attributes = True


class BookingCreate(BaseModel):
    lock_id: int
    purpose: Optional[str] = None


class BookingCancel(BaseModel):
    cancel_reason: Optional[str] = None


class BookingCheckIn(BaseModel):
    pass


class BookingResponse(BaseModel):
    id: int
    user_id: int
    user_name: str
    room_id: int
    room_name: str
    lock_id: Optional[int]
    start_time: datetime
    end_time: datetime
    status: BookingStatus
    purpose: Optional[str]
    check_in_time: Optional[datetime]
    check_out_time: Optional[datetime]
    cancelled_at: Optional[datetime]
    cancel_reason: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AbnormalRecordCreate(BaseModel):
    booking_id: int
    abnormal_type: str
    description: str = Field(..., min_length=1)


class AbnormalRecordConfirm(BaseModel):
    is_confirmed: bool
    handling_result: Optional[str] = None


class AbnormalRecordResponse(BaseModel):
    id: int
    booking_id: int
    booking_info: Optional[dict]
    reporter_name: str
    abnormal_type: str
    description: str
    is_confirmed: bool
    confirmed_by_name: Optional[str]
    confirmed_at: Optional[datetime]
    handling_result: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AvailableSlot(BaseModel):
    room_id: int
    room_name: str
    date: date
    start_time: time
    end_time: time
    is_available: bool
    lock_info: Optional[dict] = None
    booking_info: Optional[dict] = None


class BookingQueryParams(BaseModel):
    room_id: Optional[int] = None
    user_id: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[BookingStatus] = None
    lock_status: Optional[LockStatus] = None
    is_overtime: Optional[bool] = None


class PaginatedResponse(BaseModel):
    items: List[dict]
    total: int
    page: int
    page_size: int


class CurrentLockListItem(BaseModel):
    lock_id: int
    room_name: str
    user_name: str
    start_time: datetime
    end_time: datetime
    expires_at: datetime
    remaining_minutes: int
    extended_count: int


class UpcomingReleaseItem(BaseModel):
    lock_id: int
    room_name: str
    user_name: str
    release_at: datetime
    time_slot: str
    remaining_minutes: int


class AbnormalRankingItem(BaseModel):
    user_id: int
    user_name: str
    abnormal_count: int
    no_show_count: int
    duplicate_booking_count: int
    total_abnormal: int


class OperationLogResponse(BaseModel):
    id: int
    user_name: Optional[str]
    operation_type: str
    target_type: Optional[str]
    target_id: Optional[int]
    detail: Optional[str]
    ip_address: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AppealCreate(BaseModel):
    appeal_type: AppealType
    target_type: str
    target_id: int
    reason: str = Field(..., min_length=1)
    supplement: Optional[str] = None


class AppealReview(BaseModel):
    status: AppealStatus
    review_opinion: str = Field(..., min_length=1)


class AppealResponse(BaseModel):
    id: int
    user_id: int
    user_name: str
    appeal_type: AppealType
    target_type: str
    target_id: int
    target_info: Optional[dict]
    reason: str
    supplement: Optional[str]
    status: AppealStatus
    reviewer_id: Optional[int]
    reviewer_name: Optional[str]
    review_opinion: Optional[str]
    reviewed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AppealQueryParams(BaseModel):
    status: Optional[AppealStatus] = None
    appeal_type: Optional[AppealType] = None
    user_id: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
