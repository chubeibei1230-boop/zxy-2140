from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from datetime import datetime
from database import get_db
from models import User, UserRole
from schemas import (
    LockCreate, LockExtend,
    BookingCreate, BookingCancel
)
from auth import require_roles, log_operation, get_current_user
import crud

router = APIRouter(prefix="/api/executor", tags=["执行者"])


# ==================== 临时锁定 ====================

@router.post("/locks", summary="创建临时锁定")
async def create_lock(
    data: LockCreate,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.EXECUTOR, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        crud.expire_locks(db)
        lock = crud.create_lock(db, current_user.id, data)
        log_operation(
            db, current_user.id, "创建锁定", "Lock", lock.id,
            f"锁定练习间{lock.room_id} {lock.start_time.strftime('%Y-%m-%d %H:%M')}-{lock.end_time.strftime('%H:%M')}",
            request
        )
        now = datetime.now()
        remaining = int((lock.expires_at - now).total_seconds())
        return {
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
            "is_expired": lock.expires_at <= now,
            "remaining_seconds": max(0, remaining)
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/locks/my", summary="获取我的锁定列表")
async def get_my_locks(
    current_user: User = Depends(require_roles([UserRole.EXECUTOR, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    crud.expire_locks(db)
    locks = crud.list_active_locks(db, user_id=current_user.id)
    now = datetime.now()
    result = []
    for lock in locks:
        remaining = int((lock.expires_at - now).total_seconds())
        result.append({
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
            "is_expired": lock.expires_at <= now,
            "remaining_seconds": max(0, remaining)
        })
    return result


@router.post("/locks/{lock_id}/extend", summary="延长锁定时间")
async def extend_lock(
    lock_id: int,
    data: LockExtend,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.EXECUTOR, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        crud.expire_locks(db)
        lock = crud.extend_lock(db, lock_id, current_user.id, data)
        log_operation(db, current_user.id, "延长锁定", "Lock", lock_id, f"延长锁定{lock_id} {data.extend_minutes}分钟", request)
        now = datetime.now()
        remaining = int((lock.expires_at - now).total_seconds())
        return {
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
            "is_expired": lock.expires_at <= now,
            "remaining_seconds": max(0, remaining)
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/locks/{lock_id}/release", summary="主动释放锁定")
async def release_lock(
    lock_id: int,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.EXECUTOR, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        lock = crud.release_lock(db, lock_id, current_user.id, "用户主动释放")
        log_operation(db, current_user.id, "释放锁定", "Lock", lock_id, f"主动释放锁定{lock_id}", request)
        return {
            "message": "锁定已释放",
            "lock_id": lock.id,
            "status": lock.status,
            "release_reason": lock.release_reason
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ==================== 预约管理 ====================

@router.post("/bookings", summary="提交正式预约（基于锁定）")
async def create_booking(
    data: BookingCreate,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.EXECUTOR, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        crud.expire_locks(db)
        booking = crud.create_booking(db, current_user.id, data)
        log_operation(
            db, current_user.id, "创建预约", "Booking", booking.id,
            f"预约练习间{booking.room_id} {booking.start_time.strftime('%Y-%m-%d %H:%M')}-{booking.end_time.strftime('%H:%M')}",
            request
        )
        return {
            "id": booking.id,
            "user_id": booking.user_id,
            "user_name": booking.user.real_name if booking.user else "未知",
            "room_id": booking.room_id,
            "room_name": booking.room.name if booking.room else "未知",
            "lock_id": booking.lock_id,
            "start_time": booking.start_time,
            "end_time": booking.end_time,
            "status": booking.status,
            "purpose": booking.purpose,
            "check_in_time": booking.check_in_time,
            "check_out_time": booking.check_out_time,
            "cancelled_at": booking.cancelled_at,
            "cancel_reason": booking.cancel_reason,
            "created_at": booking.created_at,
            "updated_at": booking.updated_at
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/bookings/my", summary="获取我的预约列表")
async def get_my_bookings(
    status: str = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(require_roles([UserRole.EXECUTOR, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    skip = (page - 1) * page_size
    bookings, total = crud.list_bookings(
        db,
        user_id=current_user.id,
        status=status,
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
            "created_at": b.created_at,
            "updated_at": b.updated_at
        })
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.post("/bookings/{booking_id}/check-in", summary="预约签到")
async def check_in_booking(
    booking_id: int,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.EXECUTOR, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        booking = crud.check_in_booking(db, booking_id, current_user.id)
        log_operation(db, current_user.id, "签到确认", "Booking", booking_id, f"预约{booking_id}签到成功", request)
        return {
            "message": "签到成功",
            "id": booking.id,
            "status": booking.status,
            "check_in_time": booking.check_in_time
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/bookings/{booking_id}/cancel", summary="取消预约")
async def cancel_booking(
    booking_id: int,
    data: BookingCancel,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.EXECUTOR, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        booking = crud.cancel_booking(db, booking_id, current_user.id, data)
        log_operation(
            db, current_user.id, "取消预约", "Booking", booking_id,
            f"取消预约{booking_id}: {data.cancel_reason or '用户主动取消'}",
            request
        )
        return {
            "message": "预约已取消",
            "id": booking.id,
            "status": booking.status,
            "cancelled_at": booking.cancelled_at,
            "cancel_reason": booking.cancel_reason
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
