from datetime import datetime, timedelta, date, time
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from models import (
    User, PracticeRoom, TimeSlot, BookingRule, Blacklist,
    Lock, Booking, AbnormalRecord, LockStatus, BookingStatus, UserRole,
    Appeal, AppealStatus, AppealType
)
from schemas import (
    UserCreate, UserUpdate, PracticeRoomCreate, PracticeRoomUpdate,
    TimeSlotCreate, TimeSlotUpdate, BookingRuleUpdate,
    BlacklistCreate, BlacklistUpdate, LockCreate, LockExtend,
    BookingCreate, BookingCancel, AbnormalRecordCreate, AbnormalRecordConfirm,
    PasswordChange, AppealCreate, AppealReview
)
from auth import hash_password, verify_password


def check_time_overlap(
    start1: datetime, end1: datetime,
    start2: datetime, end2: datetime
) -> bool:
    return start1 < end2 and end1 > start2


def get_booking_rule(db: Session) -> BookingRule:
    rule = db.query(BookingRule).first()
    if not rule:
        rule = BookingRule(
            lock_duration_minutes=15,
            max_booking_hours=4,
            min_booking_hours=0.5,
            max_daily_bookings=2,
            advance_booking_days=7,
            no_show_threshold=3,
            auto_release_minutes=15
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
    return rule


def check_user_in_blacklist(db: Session, user_id: int) -> bool:
    now = datetime.now()
    record = db.query(Blacklist).filter(
        Blacklist.user_id == user_id,
        Blacklist.is_active == True,
        Blacklist.start_date <= now,
        or_(Blacklist.end_date == None, Blacklist.end_date >= now)
    ).first()
    return record is not None


def get_active_locks_for_room(
    db: Session,
    room_id: int,
    start_time: datetime,
    end_time: datetime,
    exclude_lock_id: Optional[int] = None
) -> List[Lock]:
    query = db.query(Lock).filter(
        Lock.room_id == room_id,
        Lock.status == LockStatus.ACTIVE,
        Lock.expires_at > datetime.now()
    )
    if exclude_lock_id:
        query = query.filter(Lock.id != exclude_lock_id)
    locks = query.all()
    return [l for l in locks if check_time_overlap(l.start_time, l.end_time, start_time, end_time)]


def get_active_bookings_for_room(
    db: Session,
    room_id: int,
    start_time: datetime,
    end_time: datetime,
    exclude_booking_id: Optional[int] = None
) -> List[Booking]:
    query = db.query(Booking).filter(
        Booking.room_id == room_id,
        Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN])
    )
    if exclude_booking_id:
        query = query.filter(Booking.id != exclude_booking_id)
    bookings = query.all()
    return [b for b in bookings if check_time_overlap(b.start_time, b.end_time, start_time, end_time)]


def get_user_active_locks(
    db: Session,
    user_id: int,
    start_time: datetime,
    end_time: datetime
) -> List[Lock]:
    query = db.query(Lock).filter(
        Lock.user_id == user_id,
        Lock.status == LockStatus.ACTIVE,
        Lock.expires_at > datetime.now()
    )
    locks = query.all()
    return [l for l in locks if check_time_overlap(l.start_time, l.end_time, start_time, end_time)]


def get_user_daily_bookings(db: Session, user_id: int, target_date: date) -> int:
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())
    return db.query(Booking).filter(
        Booking.user_id == user_id,
        Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN]),
        Booking.start_time >= start_of_day,
        Booking.start_time <= end_of_day
    ).count()


def get_user_no_show_count(db: Session, user_id: int, days: int = 30) -> int:
    since = datetime.now() - timedelta(days=days)
    return db.query(Booking).filter(
        Booking.user_id == user_id,
        Booking.status == BookingStatus.NO_SHOW,
        Booking.created_at >= since
    ).count()


# ==================== User CRUD ====================

def create_user(db: Session, user_data: UserCreate) -> User:
    if db.query(User).filter(User.username == user_data.username).first():
        raise ValueError("用户名已存在")
    db_user = User(
        username=user_data.username,
        password_hash=hash_password(user_data.password),
        real_name=user_data.real_name,
        role=user_data.role.value,
        phone=user_data.phone,
        email=user_data.email
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = get_user_by_username(db, username)
    if not user or not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    return user


def update_user_password(db: Session, user_id: int, data: PasswordChange) -> bool:
    user = get_user_by_id(db, user_id)
    if not user:
        raise ValueError("用户不存在")
    if not verify_password(data.old_password, user.password_hash):
        raise ValueError("原密码错误")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return True


def update_user(db: Session, user_id: int, data: UserUpdate) -> User:
    user = get_user_by_id(db, user_id)
    if not user:
        raise ValueError("用户不存在")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user


def list_users(db: Session, role: Optional[str] = None, skip: int = 0, limit: int = 100) -> Tuple[List[User], int]:
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    total = query.count()
    users = query.offset(skip).limit(limit).all()
    return users, total


# ==================== Practice Room CRUD ====================

def create_room(db: Session, data: PracticeRoomCreate) -> PracticeRoom:
    if db.query(PracticeRoom).filter(PracticeRoom.name == data.name).first():
        raise ValueError("练习间名称已存在")
    room = PracticeRoom(**data.model_dump())
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


def get_room(db: Session, room_id: int) -> Optional[PracticeRoom]:
    return db.query(PracticeRoom).filter(PracticeRoom.id == room_id).first()


def update_room(db: Session, room_id: int, data: PracticeRoomUpdate) -> PracticeRoom:
    room = get_room(db, room_id)
    if not room:
        raise ValueError("练习间不存在")
    if data.name and data.name != room.name:
        if db.query(PracticeRoom).filter(PracticeRoom.name == data.name, PracticeRoom.id != room_id).first():
            raise ValueError("练习间名称已存在")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(room, key, value)
    db.commit()
    db.refresh(room)
    return room


def list_rooms(db: Session, is_active: Optional[bool] = None) -> List[PracticeRoom]:
    query = db.query(PracticeRoom)
    if is_active is not None:
        query = query.filter(PracticeRoom.is_active == is_active)
    return query.order_by(PracticeRoom.id).all()


# ==================== Time Slot CRUD ====================

def create_time_slot(db: Session, data: TimeSlotCreate) -> TimeSlot:
    if not get_room(db, data.room_id):
        raise ValueError("练习间不存在")
    slot = TimeSlot(**data.model_dump())
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


def get_time_slot(db: Session, slot_id: int) -> Optional[TimeSlot]:
    return db.query(TimeSlot).filter(TimeSlot.id == slot_id).first()


def update_time_slot(db: Session, slot_id: int, data: TimeSlotUpdate) -> TimeSlot:
    slot = get_time_slot(db, slot_id)
    if not slot:
        raise ValueError("时段不存在")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(slot, key, value)
    db.commit()
    db.refresh(slot)
    return slot


def delete_time_slot(db: Session, slot_id: int) -> bool:
    slot = get_time_slot(db, slot_id)
    if not slot:
        raise ValueError("时段不存在")
    db.delete(slot)
    db.commit()
    return True


def list_time_slots(db: Session, room_id: Optional[int] = None) -> List[TimeSlot]:
    query = db.query(TimeSlot)
    if room_id:
        query = query.filter(TimeSlot.room_id == room_id)
    return query.order_by(TimeSlot.room_id, TimeSlot.day_of_week, TimeSlot.start_time).all()


# ==================== Booking Rule CRUD ====================

def update_booking_rule(db: Session, data: BookingRuleUpdate) -> BookingRule:
    rule = get_booking_rule(db)
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(rule, key, value)
    db.commit()
    db.refresh(rule)
    return rule


# ==================== Blacklist CRUD ====================

def create_blacklist(db: Session, data: BlacklistCreate, added_by: int) -> Blacklist:
    if not get_user_by_id(db, data.user_id):
        raise ValueError("用户不存在")
    if data.end_date and data.end_date <= data.start_date:
        raise ValueError("结束日期必须晚于开始日期")
    record = Blacklist(**data.model_dump(), added_by=added_by)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def update_blacklist(db: Session, record_id: int, data: BlacklistUpdate) -> Blacklist:
    record = db.query(Blacklist).filter(Blacklist.id == record_id).first()
    if not record:
        raise ValueError("黑名单记录不存在")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    return record


def list_blacklist(db: Session, is_active: Optional[bool] = None, user_id: Optional[int] = None) -> List[Blacklist]:
    query = db.query(Blacklist)
    if is_active is not None:
        query = query.filter(Blacklist.is_active == is_active)
    if user_id:
        query = query.filter(Blacklist.user_id == user_id)
    return query.order_by(Blacklist.created_at.desc()).all()


# ==================== Lock CRUD ====================

def create_lock(db: Session, user_id: int, data: LockCreate) -> Lock:
    rule = get_booking_rule(db)

    if check_user_in_blacklist(db, user_id):
        raise ValueError("您已被加入黑名单，无法预约")

    no_show_count = get_user_no_show_count(db, user_id)
    if no_show_count >= rule.no_show_threshold:
        raise ValueError(f"您近期爽约次数过多（{no_show_count}次），暂时无法预约")

    room = get_room(db, data.room_id)
    if not room:
        raise ValueError("练习间不存在")
    if not room.is_active:
        raise ValueError("练习间未启用")

    now = datetime.now()
    if data.start_time < now:
        raise ValueError("不能锁定已经开始的时段")
    if data.end_time <= now:
        raise ValueError("预约时间必须晚于当前时间")

    duration_hours = (data.end_time - data.start_time).total_seconds() / 3600
    if duration_hours < rule.min_booking_hours:
        raise ValueError(f"预约时长不能少于 {rule.min_booking_hours} 小时")
    if duration_hours > rule.max_booking_hours:
        raise ValueError(f"预约时长不能超过 {rule.max_booking_hours} 小时")

    max_future_date = now + timedelta(days=rule.advance_booking_days)
    if data.start_time > max_future_date:
        raise ValueError(f"只能预约 {rule.advance_booking_days} 天以内的时段")
    if data.end_time <= now:
        raise ValueError("预约时间必须晚于当前时间")

    target_date = data.start_time.date()
    daily_count = get_user_daily_bookings(db, user_id, target_date)
    if daily_count >= rule.max_daily_bookings:
        raise ValueError(f"每日最多预约 {rule.max_daily_bookings} 次，您今日已达上限")

    user_locks = get_user_active_locks(db, user_id, data.start_time, data.end_time)
    if user_locks:
        raise ValueError("您已有重叠时段的锁定，请先处理")

    conflicting_locks = get_active_locks_for_room(db, data.room_id, data.start_time, data.end_time)
    if conflicting_locks:
        raise ValueError("该时段已被其他用户锁定")

    conflicting_bookings = get_active_bookings_for_room(db, data.room_id, data.start_time, data.end_time)
    if conflicting_bookings:
        raise ValueError("该时段已有预约记录")

    day_of_week = data.start_time.weekday()
    target_date = data.start_time.date()
    valid_slots = db.query(TimeSlot).filter(
        TimeSlot.room_id == data.room_id,
        TimeSlot.day_of_week == day_of_week,
        TimeSlot.is_active == True
    ).all()

    slot_matched = False
    for slot in valid_slots:
        sh, sm = map(int, slot.start_time.split(':'))
        eh, em = map(int, slot.end_time.split(':'))
        slot_start = datetime.combine(target_date, time(sh, sm))
        slot_end = datetime.combine(target_date, time(eh, em))
        if data.start_time >= slot_start and data.end_time <= slot_end:
            slot_matched = True
            break

    if not valid_slots:
        raise ValueError("该练习间在此日期没有开放时段，无法锁定")
    if not slot_matched:
        raise ValueError("所请求的时段不在管理员开放的时段范围内，无法锁定")

    expires_at = now + timedelta(minutes=rule.lock_duration_minutes)
    lock = Lock(
        user_id=user_id,
        room_id=data.room_id,
        start_time=data.start_time,
        end_time=data.end_time,
        status=LockStatus.ACTIVE,
        expires_at=expires_at
    )
    db.add(lock)
    db.commit()
    db.refresh(lock)
    return lock


def get_lock(db: Session, lock_id: int) -> Optional[Lock]:
    return db.query(Lock).filter(Lock.id == lock_id).first()


def extend_lock(db: Session, lock_id: int, user_id: int, data: LockExtend) -> Lock:
    lock = get_lock(db, lock_id)
    if not lock:
        raise ValueError("锁定记录不存在")
    if lock.user_id != user_id:
        raise ValueError("只能延长自己的锁定")
    if lock.status != LockStatus.ACTIVE:
        raise ValueError("锁定状态无效")
    if lock.expires_at <= datetime.now():
        raise ValueError("锁定已过期")
    if lock.extended_count >= lock.max_extensions:
        raise ValueError("已达到最大延长次数")

    lock.expires_at = lock.expires_at + timedelta(minutes=data.extend_minutes)
    lock.extended_count += 1
    db.commit()
    db.refresh(lock)
    return lock


def release_lock(db: Session, lock_id: int, user_id: Optional[int] = None, reason: str = "主动释放") -> Lock:
    lock = get_lock(db, lock_id)
    if not lock:
        raise ValueError("锁定记录不存在")
    if user_id and lock.user_id != user_id:
        raise ValueError("只能释放自己的锁定")
    if lock.status != LockStatus.ACTIVE:
        return lock

    lock.status = LockStatus.RELEASED
    lock.released_at = datetime.now()
    lock.release_reason = reason
    db.commit()
    db.refresh(lock)
    return lock


def expire_locks(db: Session) -> int:
    now = datetime.now()
    expired = db.query(Lock).filter(
        Lock.status == LockStatus.ACTIVE,
        Lock.expires_at <= now
    ).all()
    count = 0
    for lock in expired:
        lock.status = LockStatus.EXPIRED
        lock.released_at = now
        lock.release_reason = "超时自动释放"
        count += 1
    db.commit()
    return count


def list_active_locks(db: Session, user_id: Optional[int] = None, room_id: Optional[int] = None) -> List[Lock]:
    query = db.query(Lock).filter(Lock.status == LockStatus.ACTIVE)
    if user_id:
        query = query.filter(Lock.user_id == user_id)
    if room_id:
        query = query.filter(Lock.room_id == room_id)
    return query.order_by(Lock.expires_at.asc()).all()


# ==================== Booking CRUD ====================

def create_booking(db: Session, user_id: int, data: BookingCreate) -> Booking:
    lock = get_lock(db, data.lock_id)
    if not lock:
        raise ValueError("锁定记录不存在")
    if lock.user_id != user_id:
        raise ValueError("只能使用自己的锁定创建预约")
    if lock.status != LockStatus.ACTIVE:
        raise ValueError("锁定已失效，请重新锁定")
    if lock.expires_at <= datetime.now():
        raise ValueError("锁定已过期，请重新锁定")

    try:
        if check_user_in_blacklist(db, user_id):
            raise ValueError("您已被加入黑名单，无法预约")

        conflicting_bookings = get_active_bookings_for_room(
            db, lock.room_id, lock.start_time, lock.end_time
        )
        if conflicting_bookings:
            raise ValueError("该时段已被预约")

        booking = Booking(
            user_id=user_id,
            room_id=lock.room_id,
            lock_id=lock.id,
            start_time=lock.start_time,
            end_time=lock.end_time,
            status=BookingStatus.CONFIRMED,
            purpose=data.purpose
        )
        db.add(booking)
        lock.status = LockStatus.CONVERTED
        lock.released_at = datetime.now()
        lock.release_reason = "成功转换为正式预约"
        db.commit()
        db.refresh(booking)
        return booking
    except ValueError:
        lock.status = LockStatus.RELEASED
        lock.released_at = datetime.now()
        lock.release_reason = "创建预约失败，自动释放锁定"
        db.commit()
        raise


def get_booking(db: Session, booking_id: int) -> Optional[Booking]:
    return db.query(Booking).filter(Booking.id == booking_id).first()


def cancel_booking(db: Session, booking_id: int, user_id: int, data: BookingCancel) -> Booking:
    booking = get_booking(db, booking_id)
    if not booking:
        raise ValueError("预约记录不存在")
    if booking.user_id != user_id:
        raise ValueError("只能取消自己的预约")
    if booking.status not in [BookingStatus.PENDING, BookingStatus.CONFIRMED]:
        raise ValueError("当前状态无法取消预约")

    booking.status = BookingStatus.CANCELLED
    booking.cancelled_at = datetime.now()
    booking.cancel_reason = data.cancel_reason or "用户主动取消"
    db.commit()
    db.refresh(booking)
    return booking


def check_in_booking(db: Session, booking_id: int, user_id: int) -> Booking:
    booking = get_booking(db, booking_id)
    if not booking:
        raise ValueError("预约记录不存在")
    if booking.user_id != user_id:
        raise ValueError("只能为自己的预约签到")
    if booking.status not in [BookingStatus.CONFIRMED]:
        raise ValueError("当前状态无法签到")

    now = datetime.now()
    rule = get_booking_rule(db)
    window_start = booking.start_time - timedelta(minutes=rule.auto_release_minutes)

    if now < window_start:
        raise ValueError("签到时间过早，请在预约开始前适当时间签到")

    booking.status = BookingStatus.CHECKED_IN
    booking.check_in_time = now
    db.commit()
    db.refresh(booking)
    return booking


def mark_no_show(db: Session, booking_id: int, reviewer_id: int, note: Optional[str] = None) -> Booking:
    booking = get_booking(db, booking_id)
    if not booking:
        raise ValueError("预约记录不存在")
    if booking.status != BookingStatus.CONFIRMED:
        raise ValueError("当前状态无法标记为爽约")

    now = datetime.now()
    if now < booking.end_time:
        raise ValueError("预约尚未结束，无法标记为爽约")

    booking.status = BookingStatus.NO_SHOW
    booking.reviewer_id = reviewer_id
    booking.reviewer_note = note
    db.commit()
    db.refresh(booking)
    return booking


def list_bookings(
    db: Session,
    room_id: Optional[int] = None,
    user_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status: Optional[BookingStatus] = None,
    is_overtime: Optional[bool] = None,
    skip: int = 0,
    limit: int = 100
) -> Tuple[List[Booking], int]:
    query = db.query(Booking)
    if room_id:
        query = query.filter(Booking.room_id == room_id)
    if user_id:
        query = query.filter(Booking.user_id == user_id)
    if start_date:
        query = query.filter(Booking.start_time >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        query = query.filter(Booking.start_time <= datetime.combine(end_date, datetime.max.time()))
    if status:
        query = query.filter(Booking.status == status)
    if is_overtime:
        now = datetime.now()
        if is_overtime:
            query = query.filter(
                Booking.status == BookingStatus.CONFIRMED,
                Booking.end_time < now,
                Booking.check_in_time == None
            )
        else:
            query = query.filter(
                or_(
                    Booking.status != BookingStatus.CONFIRMED,
                    Booking.end_time >= now,
                    Booking.check_in_time != None
                )
            )
    total = query.count()
    bookings = query.order_by(Booking.start_time.desc()).offset(skip).limit(limit).all()
    return bookings, total


def handle_duplicate_bookings(db: Session, booking_ids: List[int], reviewer_id: int, keep_id: int, note: str) -> List[Booking]:
    results = []
    for bid in booking_ids:
        booking = get_booking(db, bid)
        if booking and bid != keep_id:
            booking.status = BookingStatus.CANCELLED
            booking.cancelled_at = datetime.now()
            booking.cancel_reason = f"重复预约处理：{note}"
            booking.reviewer_id = reviewer_id
            db.commit()
            db.refresh(booking)
            results.append(booking)
    return results


# ==================== Abnormal Record CRUD ====================

def create_abnormal_record(db: Session, reporter_id: int, data: AbnormalRecordCreate) -> AbnormalRecord:
    booking = get_booking(db, data.booking_id)
    if not booking:
        raise ValueError("预约记录不存在")
    record = AbnormalRecord(
        booking_id=data.booking_id,
        reporter_id=reporter_id,
        abnormal_type=data.abnormal_type,
        description=data.description
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def confirm_abnormal_record(db: Session, record_id: int, reviewer_id: int, data: AbnormalRecordConfirm) -> AbnormalRecord:
    record = db.query(AbnormalRecord).filter(AbnormalRecord.id == record_id).first()
    if not record:
        raise ValueError("异常记录不存在")
    if record.is_confirmed:
        raise ValueError("异常记录已处理")

    record.is_confirmed = data.is_confirmed
    record.confirmed_by = reviewer_id
    record.confirmed_at = datetime.now()
    record.handling_result = data.handling_result

    if data.is_confirmed:
        booking = get_booking(db, record.booking_id)
        if booking:
            booking.status = BookingStatus.ABNORMAL
            booking.reviewer_id = reviewer_id
            booking.reviewer_note = data.handling_result

    db.commit()
    db.refresh(record)
    return record


def list_abnormal_records(
    db: Session,
    is_confirmed: Optional[bool] = None,
    room_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100
) -> Tuple[List[AbnormalRecord], int]:
    query = db.query(AbnormalRecord)
    if is_confirmed is not None:
        query = query.filter(AbnormalRecord.is_confirmed == is_confirmed)
    if room_id:
        query = query.join(Booking).filter(Booking.room_id == room_id)
    total = query.count()
    records = query.order_by(AbnormalRecord.created_at.desc()).offset(skip).limit(limit).all()
    return records, total


# ==================== Statistics ====================

def get_current_lock_list(db: Session) -> List[dict]:
    now = datetime.now()
    active_locks = db.query(Lock).filter(
        Lock.status == LockStatus.ACTIVE,
        Lock.expires_at > now
    ).order_by(Lock.expires_at.asc()).all()
    result = []
    for lock in active_locks:
        remaining = int((lock.expires_at - now).total_seconds() / 60)
        result.append({
            "lock_id": lock.id,
            "room_name": lock.room.name if lock.room else "未知",
            "user_name": lock.user.real_name if lock.user else "未知",
            "start_time": lock.start_time,
            "end_time": lock.end_time,
            "expires_at": lock.expires_at,
            "remaining_minutes": remaining,
            "extended_count": lock.extended_count
        })
    return result


def get_upcoming_releases(db: Session, within_minutes: int = 10) -> List[dict]:
    now = datetime.now()
    threshold = now + timedelta(minutes=within_minutes)
    locks = db.query(Lock).filter(
        Lock.status == LockStatus.ACTIVE,
        Lock.expires_at > now,
        Lock.expires_at <= threshold
    ).order_by(Lock.expires_at.asc()).all()
    result = []
    for lock in locks:
        remaining = int((lock.expires_at - now).total_seconds() / 60)
        result.append({
            "lock_id": lock.id,
            "room_name": lock.room.name if lock.room else "未知",
            "user_name": lock.user.real_name if lock.user else "未知",
            "release_at": lock.expires_at,
            "time_slot": f"{lock.start_time.strftime('%H:%M')}-{lock.end_time.strftime('%H:%M')}",
            "remaining_minutes": remaining
        })
    return result


def get_abnormal_ranking(db: Session, days: int = 30, top_n: int = 10) -> List[dict]:
    since = datetime.now() - timedelta(days=days)

    no_show_counts = db.query(
        Booking.user_id,
        func.count(Booking.id).label('count')
    ).filter(
        Booking.status == BookingStatus.NO_SHOW,
        Booking.created_at >= since
    ).group_by(Booking.user_id).subquery()

    abnormal_counts = db.query(
        Booking.user_id,
        func.count(AbnormalRecord.id).label('count')
    ).join(
        AbnormalRecord, AbnormalRecord.booking_id == Booking.id
    ).filter(
        AbnormalRecord.is_confirmed == True,
        AbnormalRecord.created_at >= since
    ).group_by(Booking.user_id).subquery()

    duplicate_counts = db.query(
        Booking.user_id,
        func.count(Booking.id).label('count')
    ).filter(
        Booking.status == BookingStatus.CANCELLED,
        Booking.cancel_reason.like('%重复预约%'),
        Booking.cancelled_at >= since
    ).group_by(Booking.user_id).subquery()

    query = db.query(
        User.id,
        User.real_name,
        func.coalesce(abnormal_counts.c.count, 0).label('abnormal_count'),
        func.coalesce(no_show_counts.c.count, 0).label('no_show_count'),
        func.coalesce(duplicate_counts.c.count, 0).label('duplicate_count'),
        (
            func.coalesce(abnormal_counts.c.count, 0) +
            func.coalesce(no_show_counts.c.count, 0) +
            func.coalesce(duplicate_counts.c.count, 0)
        ).label('total')
    ).outerjoin(
        no_show_counts, no_show_counts.c.user_id == User.id
    ).outerjoin(
        abnormal_counts, abnormal_counts.c.user_id == User.id
    ).outerjoin(
        duplicate_counts, duplicate_counts.c.user_id == User.id
    ).filter(
        (
            func.coalesce(abnormal_counts.c.count, 0) +
            func.coalesce(no_show_counts.c.count, 0) +
            func.coalesce(duplicate_counts.c.count, 0)
        ) > 0
    ).order_by(
        func.desc('total')
    ).limit(top_n)

    results = query.all()
    ranking = []
    for row in results:
        ranking.append({
            "user_id": row.id,
            "user_name": row.real_name,
            "abnormal_count": int(row.abnormal_count),
            "no_show_count": int(row.no_show_count),
            "duplicate_booking_count": int(row.duplicate_count),
            "total_abnormal": int(row.total)
        })
    return ranking


def get_available_slots(db: Session, room_id: int, target_date: date) -> List[dict]:
    room = get_room(db, room_id)
    if not room:
        raise ValueError("练习间不存在")

    day_of_week = target_date.weekday()
    time_slots = db.query(TimeSlot).filter(
        TimeSlot.room_id == room_id,
        TimeSlot.day_of_week == day_of_week,
        TimeSlot.is_active == True
    ).all()

    now = datetime.now()
    result = []

    for slot in time_slots:
        start_h, start_m = map(int, slot.start_time.split(':'))
        end_h, end_m = map(int, slot.end_time.split(':'))

        slot_start = datetime.combine(target_date, time(start_h, start_m))
        slot_end = datetime.combine(target_date, time(end_h, end_m))

        is_past = slot_end < now
        is_available = not is_past

        lock_info = None
        booking_info = None

        if not is_past:
            conflicting_locks = get_active_locks_for_room(db, room_id, slot_start, slot_end)
            if conflicting_locks:
                is_available = False
                l = conflicting_locks[0]
                lock_info = {
                    "lock_id": l.id,
                    "user_name": l.user.real_name if l.user else "未知",
                    "expires_at": l.expires_at,
                    "status": l.status
                }

            conflicting_bookings = get_active_bookings_for_room(db, room_id, slot_start, slot_end)
            if conflicting_bookings:
                is_available = False
                b = conflicting_bookings[0]
                booking_info = {
                    "booking_id": b.id,
                    "user_name": b.user.real_name if b.user else "未知",
                    "status": b.status,
                    "purpose": b.purpose
                }

        result.append({
            "room_id": room_id,
            "room_name": room.name,
            "date": target_date,
            "start_time": time(start_h, start_m),
            "end_time": time(end_h, end_m),
            "is_available": is_available,
            "is_past": is_past,
            "lock_info": lock_info,
            "booking_info": booking_info
        })

    return sorted(result, key=lambda x: x["start_time"])


def get_operation_logs(
    db: Session,
    user_id: Optional[int] = None,
    operation_type: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 100
) -> Tuple[List, int]:
    from models import OperationLog
    query = db.query(OperationLog)
    if user_id:
        query = query.filter(OperationLog.user_id == user_id)
    if operation_type:
        query = query.filter(OperationLog.operation_type == operation_type)
    if start_date:
        query = query.filter(OperationLog.created_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        query = query.filter(OperationLog.created_at <= datetime.combine(end_date, datetime.max.time()))
    total = query.count()
    logs = query.order_by(OperationLog.created_at.desc()).offset(skip).limit(limit).all()
    return logs, total


def process_auto_no_show(db: Session) -> int:
    rule = get_booking_rule(db)
    now = datetime.now()
    threshold_time = now - timedelta(minutes=rule.auto_release_minutes)

    candidates = db.query(Booking).filter(
        Booking.status == BookingStatus.CONFIRMED,
        Booking.end_time < threshold_time,
        Booking.check_in_time == None
    ).all()

    count = 0
    for booking in candidates:
        booking.status = BookingStatus.NO_SHOW
        booking.reviewer_note = "系统自动标记爽约"
        count += 1

    db.commit()
    return count


# ==================== Appeal CRUD ====================

def create_appeal(db: Session, user_id: int, data: AppealCreate) -> Appeal:
    if data.appeal_type == AppealType.NO_SHOW:
        booking = get_booking(db, data.target_id)
        if not booking:
            raise ValueError("预约记录不存在")
        if booking.user_id != user_id:
            raise ValueError("只能对自己的预约记录申诉")
        if booking.status != BookingStatus.NO_SHOW:
            raise ValueError("该预约状态不是爽约，无需申诉")
    elif data.appeal_type == AppealType.ABNORMAL:
        abnormal = db.query(AbnormalRecord).filter(AbnormalRecord.id == data.target_id).first()
        if not abnormal:
            raise ValueError("异常记录不存在")
        booking = get_booking(db, abnormal.booking_id)
        if booking and booking.user_id != user_id:
            raise ValueError("只能对自己的异常记录申诉")
        if not abnormal.is_confirmed:
            raise ValueError("该异常记录尚未确认，无需申诉")
    elif data.appeal_type == AppealType.DUPLICATE_BOOKING:
        booking = get_booking(db, data.target_id)
        if not booking:
            raise ValueError("预约记录不存在")
        if booking.user_id != user_id:
            raise ValueError("只能对自己的预约记录申诉")
        if booking.status != BookingStatus.CANCELLED or not (booking.cancel_reason and "重复预约" in booking.cancel_reason):
            raise ValueError("该预约不是重复预约取消，无需申诉")
    elif data.appeal_type == AppealType.BLACKLIST:
        blacklist = db.query(Blacklist).filter(Blacklist.id == data.target_id).first()
        if not blacklist:
            raise ValueError("黑名单记录不存在")
        if blacklist.user_id != user_id:
            raise ValueError("只能对自己的黑名单记录申诉")
        if not blacklist.is_active:
            raise ValueError("该黑名单记录已失效，无需申诉")
    else:
        raise ValueError("不支持的申诉类型")

    pending_appeal = db.query(Appeal).filter(
        Appeal.user_id == user_id,
        Appeal.target_type == data.target_type,
        Appeal.target_id == data.target_id,
        Appeal.status == AppealStatus.PENDING
    ).first()
    if pending_appeal:
        raise ValueError("该记录已有待处理的申诉，请等待审核结果")

    appeal = Appeal(
        user_id=user_id,
        appeal_type=data.appeal_type.value,
        target_type=data.target_type,
        target_id=data.target_id,
        reason=data.reason,
        supplement=data.supplement,
        status=AppealStatus.PENDING
    )
    db.add(appeal)
    db.commit()
    db.refresh(appeal)
    return appeal


def get_appeal(db: Session, appeal_id: int) -> Optional[Appeal]:
    return db.query(Appeal).filter(Appeal.id == appeal_id).first()


def get_appeal_target_info(db: Session, appeal: Appeal) -> Optional[dict]:
    if appeal.target_type == "Booking" or appeal.appeal_type in [AppealType.NO_SHOW.value, AppealType.DUPLICATE_BOOKING.value]:
        booking = get_booking(db, appeal.target_id)
        if booking:
            return {
                "id": booking.id,
                "room_name": booking.room.name if booking.room else "未知",
                "room_id": booking.room_id,
                "start_time": booking.start_time,
                "end_time": booking.end_time,
                "status": booking.status,
                "purpose": booking.purpose,
                "cancel_reason": booking.cancel_reason,
                "reviewer_note": booking.reviewer_note
            }
    elif appeal.target_type == "AbnormalRecord" or appeal.appeal_type == AppealType.ABNORMAL.value:
        abnormal = db.query(AbnormalRecord).filter(AbnormalRecord.id == appeal.target_id).first()
        if abnormal:
            booking = get_booking(db, abnormal.booking_id)
            return {
                "id": abnormal.id,
                "abnormal_type": abnormal.abnormal_type,
                "description": abnormal.description,
                "is_confirmed": abnormal.is_confirmed,
                "handling_result": abnormal.handling_result,
                "booking_id": abnormal.booking_id,
                "booking_info": {
                    "room_name": booking.room.name if booking and booking.room else "未知",
                    "user_name": booking.user.real_name if booking and booking.user else "未知",
                    "start_time": booking.start_time if booking else None,
                    "end_time": booking.end_time if booking else None,
                    "status": booking.status if booking else None
                } if booking else None
            }
    elif appeal.target_type == "Blacklist" or appeal.appeal_type == AppealType.BLACKLIST.value:
        blacklist = db.query(Blacklist).filter(Blacklist.id == appeal.target_id).first()
        if blacklist:
            return {
                "id": blacklist.id,
                "reason": blacklist.reason,
                "start_date": blacklist.start_date,
                "end_date": blacklist.end_date,
                "is_active": blacklist.is_active,
                "added_by_name": blacklist.admin.real_name if blacklist.admin else "未知"
            }
    return None


def list_appeals(
    db: Session,
    status: Optional[AppealStatus] = None,
    appeal_type: Optional[AppealType] = None,
    user_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 100
) -> Tuple[List[Appeal], int]:
    query = db.query(Appeal)
    if status:
        query = query.filter(Appeal.status == status)
    if appeal_type:
        query = query.filter(Appeal.appeal_type == appeal_type)
    if user_id:
        query = query.filter(Appeal.user_id == user_id)
    if start_date:
        query = query.filter(Appeal.created_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        query = query.filter(Appeal.created_at <= datetime.combine(end_date, datetime.max.time()))
    total = query.count()
    appeals = query.order_by(Appeal.created_at.desc()).offset(skip).limit(limit).all()
    return appeals, total


def review_appeal(db: Session, appeal_id: int, reviewer_id: int, data: AppealReview) -> Appeal:
    appeal = get_appeal(db, appeal_id)
    if not appeal:
        raise ValueError("申诉记录不存在")
    if appeal.status != AppealStatus.PENDING:
        raise ValueError("该申诉已处理，无法重复审核")

    appeal.status = data.status
    appeal.reviewer_id = reviewer_id
    appeal.review_opinion = data.review_opinion
    appeal.reviewed_at = datetime.now()

    if data.status == AppealStatus.APPROVED:
        _execute_appeal_approval(db, appeal)

    db.commit()
    db.refresh(appeal)
    return appeal


def _execute_appeal_approval(db: Session, appeal: Appeal):
    if appeal.appeal_type == AppealType.NO_SHOW.value:
        booking = get_booking(db, appeal.target_id)
        if booking:
            booking.status = BookingStatus.CANCELLED
            booking.cancel_reason = f"申诉通过，取消爽约标记：{appeal.review_opinion}"
            booking.cancelled_at = datetime.now()
    elif appeal.appeal_type == AppealType.ABNORMAL.value:
        abnormal = db.query(AbnormalRecord).filter(AbnormalRecord.id == appeal.target_id).first()
        if abnormal:
            abnormal.is_confirmed = False
            abnormal.confirmed_by = None
            abnormal.confirmed_at = None
            abnormal.handling_result = f"申诉通过，撤销异常确认：{appeal.review_opinion}"
            booking = get_booking(db, abnormal.booking_id)
            if booking and booking.status == BookingStatus.ABNORMAL:
                booking.status = BookingStatus.CONFIRMED
                booking.reviewer_note = f"申诉通过，恢复预约状态：{appeal.review_opinion}"
    elif appeal.appeal_type == AppealType.DUPLICATE_BOOKING.value:
        booking = get_booking(db, appeal.target_id)
        if booking:
            booking.status = BookingStatus.CONFIRMED
            booking.cancel_reason = None
            booking.cancelled_at = None
            booking.reviewer_note = f"申诉通过，恢复预约：{appeal.review_opinion}"
    elif appeal.appeal_type == AppealType.BLACKLIST.value:
        blacklist = db.query(Blacklist).filter(Blacklist.id == appeal.target_id).first()
        if blacklist:
            blacklist.is_active = False
            blacklist.end_date = datetime.now()
            blacklist.reason = f"{blacklist.reason}（申诉通过解除：{appeal.review_opinion}）"


def get_appeal_statistics(db: Session, days: int = 30) -> dict:
    since = datetime.now() - timedelta(days=days)

    total_count = db.query(Appeal).filter(Appeal.created_at >= since).count()
    pending_count = db.query(Appeal).filter(
        Appeal.created_at >= since,
        Appeal.status == AppealStatus.PENDING
    ).count()
    approved_count = db.query(Appeal).filter(
        Appeal.created_at >= since,
        Appeal.status == AppealStatus.APPROVED
    ).count()
    rejected_count = db.query(Appeal).filter(
        Appeal.created_at >= since,
        Appeal.status == AppealStatus.REJECTED
    ).count()

    type_counts = db.query(
        Appeal.appeal_type,
        func.count(Appeal.id).label('count')
    ).filter(
        Appeal.created_at >= since
    ).group_by(Appeal.appeal_type).all()

    type_stats = {}
    for t, c in type_counts:
        type_stats[t] = c

    approval_rate = approved_count / total_count * 100 if total_count > 0 else 0

    return {
        "stat_days": days,
        "total_count": total_count,
        "pending_count": pending_count,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "approval_rate": round(approval_rate, 2),
        "type_breakdown": type_stats
    }
