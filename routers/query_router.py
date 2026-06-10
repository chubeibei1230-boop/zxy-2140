from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import datetime, date
from database import get_db
from models import User, UserRole, LockStatus, BookingStatus
from auth import get_current_user, require_roles
import crud

router = APIRouter(prefix="/api/query", tags=["查询与统计"])


# ==================== 可用时段查询 ====================

@router.get("/available-slots", summary="查询练习间可用时段")
async def get_available_slots(
    room_id: int,
    target_date: date,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        crud.expire_locks(db)
        slots = crud.get_available_slots(db, room_id, target_date)
        available_count = sum(1 for s in slots if s["is_available"])
        booked_count = len(slots) - available_count - sum(1 for s in slots if s.get("is_past", False))
        past_count = sum(1 for s in slots if s.get("is_past", False))
        return {
            "room_id": room_id,
            "target_date": target_date,
            "total_slots": len(slots),
            "available_count": available_count,
            "locked_or_booked_count": booked_count,
            "past_count": past_count,
            "slots": slots
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ==================== 预约多条件查询 ====================

@router.get("/bookings", summary="预约多条件查询")
async def query_bookings(
    room_id: int = None,
    user_id: int = None,
    start_date: date = None,
    end_date: date = None,
    status: BookingStatus = None,
    is_overtime: bool = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    skip = (page - 1) * page_size
    crud.expire_locks(db)
    crud.process_auto_no_show(db)
    bookings, total = crud.list_bookings(
        db,
        room_id=room_id,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        status=status,
        is_overtime=is_overtime,
        skip=skip,
        limit=page_size
    )
    items = []
    for b in bookings:
        items.append({
            "id": b.id,
            "user_id": b.user_id,
            "user_name": b.user.real_name if b.user else "未知",
            "room_id": b.room_id,
            "room_name": b.room.name if b.room else "未知",
            "lock_id": b.lock_id,
            "start_time": b.start_time,
            "end_time": b.end_time,
            "status": b.status,
            "purpose": b.purpose,
            "check_in_time": b.check_in_time,
            "check_out_time": b.check_out_time,
            "cancelled_at": b.cancelled_at,
            "cancel_reason": b.cancel_reason,
            "reviewer_name": b.reviewer.real_name if b.reviewer else None,
            "reviewer_note": b.reviewer_note,
            "created_at": b.created_at,
            "updated_at": b.updated_at
        })
    return {
        "filters": {
            "room_id": room_id,
            "user_id": user_id,
            "start_date": start_date,
            "end_date": end_date,
            "status": status,
            "is_overtime": is_overtime
        },
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0
    }


# ==================== 锁定多条件查询 ====================

@router.get("/locks", summary="锁定多条件查询")
async def query_locks(
    room_id: int = None,
    user_id: int = None,
    status: LockStatus = None,
    is_expired: bool = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from models import Lock
    crud.expire_locks(db)
    skip = (page - 1) * page_size

    query = db.query(Lock)
    if room_id:
        query = query.filter(Lock.room_id == room_id)
    if user_id:
        query = query.filter(Lock.user_id == user_id)
    if status:
        query = query.filter(Lock.status == status)

    total = query.count()
    locks = query.order_by(Lock.created_at.desc()).offset(skip).limit(page_size).all()

    now = datetime.now()
    items = []
    for lock in locks:
        expired = lock.expires_at <= now or lock.status != LockStatus.ACTIVE
        if is_expired is not None and expired != is_expired:
            continue
        remaining = int((lock.expires_at - now).total_seconds())
        items.append({
            "id": lock.id,
            "user_id": lock.user_id,
            "user_name": lock.user.real_name if lock.user else "未知",
            "room_id": lock.room_id,
            "room_name": lock.room.name if lock.room else "未知",
            "start_time": lock.start_time,
            "end_time": lock.end_time,
            "status": lock.status,
            "expires_at": lock.expires_at,
            "extended_count": lock.extended_count,
            "max_extensions": lock.max_extensions,
            "created_at": lock.created_at,
            "released_at": lock.released_at,
            "release_reason": lock.release_reason,
            "is_expired": expired,
            "remaining_seconds": max(0, remaining)
        })

    return {
        "filters": {
            "room_id": room_id,
            "user_id": user_id,
            "status": status,
            "is_expired": is_expired
        },
        "items": items,
        "total": len(items),
        "page": page,
        "page_size": page_size
    }


# ==================== 统计接口 ====================

@router.get("/stats/current-locks", summary="当前锁定清单")
async def get_current_lock_list(
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.REVIEWER])),
    db: Session = Depends(get_db)
):
    crud.expire_locks(db)
    locks = crud.get_current_lock_list(db)
    return {
        "generated_at": datetime.now(),
        "total_active_locks": len(locks),
        "locks": locks
    }


@router.get("/stats/upcoming-releases", summary="即将释放时段")
async def get_upcoming_releases(
    within_minutes: int = Query(10, ge=1, le=120, description="未来多少分钟内即将释放"),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.REVIEWER, UserRole.EXECUTOR])),
    db: Session = Depends(get_db)
):
    crud.expire_locks(db)
    releases = crud.get_upcoming_releases(db, within_minutes=within_minutes)
    return {
        "generated_at": datetime.now(),
        "within_minutes": within_minutes,
        "total_releases": len(releases),
        "releases": releases
    }


@router.get("/stats/abnormal-ranking", summary="异常占用排行")
async def get_abnormal_ranking(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    top_n: int = Query(10, ge=1, le=100, description="返回前N名"),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.REVIEWER])),
    db: Session = Depends(get_db)
):
    ranking = crud.get_abnormal_ranking(db, days=days, top_n=top_n)
    total_abnormal = sum(r["total_abnormal"] for r in ranking)
    return {
        "generated_at": datetime.now(),
        "stat_days": days,
        "top_n": top_n,
        "total_abnormal_count": total_abnormal,
        "ranking": ranking
    }


@router.get("/stats/dashboard", summary="综合概览数据")
async def get_dashboard_stats(
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.REVIEWER])),
    db: Session = Depends(get_db)
):
    from models import Lock, Booking, PracticeRoom, User

    crud.expire_locks(db)
    crud.process_auto_no_show(db)
    now = datetime.now()
    today = now.date()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())

    total_rooms = db.query(PracticeRoom).filter(PracticeRoom.is_active == True).count()
    total_users = db.query(User).filter(User.is_active == True).count()

    active_locks_count = db.query(Lock).filter(
        Lock.status == LockStatus.ACTIVE,
        Lock.expires_at > now
    ).count()

    today_bookings = db.query(Booking).filter(
        Booking.start_time >= today_start,
        Booking.start_time <= today_end
    ).count()

    confirmed_bookings = db.query(Booking).filter(
        Booking.start_time >= today_start,
        Booking.start_time <= today_end,
        Booking.status == BookingStatus.CONFIRMED
    ).count()

    checked_in_bookings = db.query(Booking).filter(
        Booking.start_time >= today_start,
        Booking.start_time <= today_end,
        Booking.status == BookingStatus.CHECKED_IN
    ).count()

    cancelled_bookings = db.query(Booking).filter(
        Booking.start_time >= today_start,
        Booking.start_time <= today_end,
        Booking.status == BookingStatus.CANCELLED
    ).count()

    no_show_count = db.query(Booking).filter(
        Booking.start_time >= today_start,
        Booking.start_time <= today_end,
        Booking.status == BookingStatus.NO_SHOW
    ).count()

    from models import AbnormalRecord
    pending_abnormal = db.query(AbnormalRecord).filter(
        AbnormalRecord.is_confirmed == False
    ).count()

    upcoming_releases = crud.get_upcoming_releases(db, within_minutes=15)

    return {
        "generated_at": now,
        "overview": {
            "active_rooms": total_rooms,
            "active_users": total_users,
            "active_locks": active_locks_count,
            "today_bookings": today_bookings
        },
        "today_breakdown": {
            "confirmed": confirmed_bookings,
            "checked_in": checked_in_bookings,
            "cancelled": cancelled_bookings,
            "no_show": no_show_count
        },
        "pending_actions": {
            "pending_abnormal_records": pending_abnormal,
            "upcoming_releases_15min": len(upcoming_releases)
        }
    }


# ==================== 操作日志查询 ====================

@router.get("/operation-logs", summary="查询操作日志")
async def get_operation_logs(
    user_id: int = None,
    operation_type: str = None,
    start_date: date = None,
    end_date: date = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    skip = (page - 1) * page_size
    logs, total = crud.get_operation_logs(
        db,
        user_id=user_id,
        operation_type=operation_type,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=page_size
    )
    items = []
    for log in logs:
        items.append({
            "id": log.id,
            "user_name": log.operator.real_name if log.operator else "系统",
            "operation_type": log.operation_type,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "detail": log.detail,
            "ip_address": log.ip_address,
            "created_at": log.created_at
        })
    return {
        "filters": {
            "user_id": user_id,
            "operation_type": operation_type,
            "start_date": start_date,
            "end_date": end_date
        },
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0
    }
