from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field
from database import get_db
from models import User, UserRole
from schemas import (
    AbnormalRecordCreate, AbnormalRecordConfirm
)
from auth import require_roles, log_operation, get_current_user
import crud

router = APIRouter(prefix="/api/reviewer", tags=["复核者"])


class DuplicateBookingHandle(BaseModel):
    booking_ids: List[int] = Field(..., min_length=2)
    keep_id: int
    note: str = Field(..., min_length=1)


class NoShowMark(BaseModel):
    note: Optional[str] = None


# ==================== 异常记录 ====================

@router.post("/abnormal-records", summary="上报异常占用/情况")
async def create_abnormal_record(
    data: AbnormalRecordCreate,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.REVIEWER, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        record = crud.create_abnormal_record(db, current_user.id, data)
        log_operation(
            db, current_user.id, "上报异常", "AbnormalRecord", record.id,
            f"类型:{data.abnormal_type} 预约:{data.booking_id}",
            request
        )
        booking = crud.get_booking(db, record.booking_id)
        return {
            "id": record.id,
            "booking_id": record.booking_id,
            "booking_info": {
                "id": booking.id,
                "room_name": booking.room.name if booking.room else "未知",
                "user_name": booking.user.real_name if booking.user else "未知",
                "start_time": booking.start_time,
                "end_time": booking.end_time,
                "status": booking.status
            } if booking else None,
            "reporter_name": record.reporter.real_name if record.reporter else "未知",
            "abnormal_type": record.abnormal_type,
            "description": record.description,
            "is_confirmed": record.is_confirmed,
            "confirmed_by_name": record.confirmer.real_name if record.confirmer else None,
            "confirmed_at": record.confirmed_at,
            "handling_result": record.handling_result,
            "created_at": record.created_at
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/abnormal-records", summary="获取异常记录列表")
async def list_abnormal_records(
    is_confirmed: bool = None,
    room_id: int = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(require_roles([UserRole.REVIEWER, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    skip = (page - 1) * page_size
    records, total = crud.list_abnormal_records(
        db, is_confirmed=is_confirmed, room_id=room_id, skip=skip, limit=page_size
    )
    items = []
    for record in records:
        booking = crud.get_booking(db, record.booking_id)
        items.append({
            "id": record.id,
            "booking_id": record.booking_id,
            "booking_info": {
                "id": booking.id,
                "room_name": booking.room.name if booking.room else "未知",
                "user_name": booking.user.real_name if booking.user else "未知",
                "start_time": booking.start_time,
                "end_time": booking.end_time,
                "status": booking.status
            } if booking else None,
            "reporter_name": record.reporter.real_name if record.reporter else "未知",
            "abnormal_type": record.abnormal_type,
            "description": record.description,
            "is_confirmed": record.is_confirmed,
            "confirmed_by_name": record.confirmer.real_name if record.confirmer else None,
            "confirmed_at": record.confirmed_at,
            "handling_result": record.handling_result,
            "created_at": record.created_at
        })
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.post("/abnormal-records/{record_id}/confirm", summary="确认/处理异常记录")
async def confirm_abnormal_record(
    record_id: int,
    data: AbnormalRecordConfirm,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.REVIEWER, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        record = crud.confirm_abnormal_record(db, record_id, current_user.id, data)
        log_operation(
            db, current_user.id, "处理异常", "AbnormalRecord", record_id,
            f"确认:{data.is_confirmed} 处理结果:{data.handling_result or '无'}",
            request
        )
        booking = crud.get_booking(db, record.booking_id)
        return {
            "message": "处理完成",
            "id": record.id,
            "booking_id": record.booking_id,
            "booking_info": {
                "id": booking.id,
                "room_name": booking.room.name if booking.room else "未知",
                "user_name": booking.user.real_name if booking.user else "未知",
                "start_time": booking.start_time,
                "end_time": booking.end_time,
                "status": booking.status
            } if booking else None,
            "is_confirmed": record.is_confirmed,
            "confirmed_by_name": record.confirmer.real_name if record.confirmer else None,
            "confirmed_at": record.confirmed_at,
            "handling_result": record.handling_result
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ==================== 爽约处理 ====================

@router.post("/bookings/{booking_id}/mark-no-show", summary="标记爽约")
async def mark_no_show(
    booking_id: int,
    data: NoShowMark,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.REVIEWER, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        booking = crud.mark_no_show(db, booking_id, current_user.id, data.note)
        log_operation(
            db, current_user.id, "标记爽约", "Booking", booking_id,
            f"标记预约{booking_id}为爽约: {data.note or '无备注'}",
            request
        )
        return {
            "message": "已标记为爽约",
            "id": booking.id,
            "user_name": booking.user.real_name if booking.user else "未知",
            "room_name": booking.room.name if booking.room else "未知",
            "start_time": booking.start_time,
            "end_time": booking.end_time,
            "status": booking.status,
            "reviewer_note": booking.reviewer_note
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ==================== 重复预约处理 ====================

@router.post("/bookings/handle-duplicates", summary="处理重复预约")
async def handle_duplicate_bookings(
    data: DuplicateBookingHandle,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.REVIEWER, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        if data.keep_id not in data.booking_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="保留的预约ID必须在待处理列表中")
        cancelled = crud.handle_duplicate_bookings(
            db, data.booking_ids, current_user.id, data.keep_id, data.note
        )
        log_operation(
            db, current_user.id, "处理重复预约", "Booking", None,
            f"保留{data.keep_id}，取消{len(cancelled)}个: {data.note}",
            request
        )
        kept = crud.get_booking(db, data.keep_id)
        return {
            "message": "重复预约处理完成",
            "kept_booking": {
                "id": kept.id if kept else None,
                "user_name": kept.user.real_name if kept and kept.user else "未知",
                "room_name": kept.room.name if kept and kept.room else "未知",
                "start_time": kept.start_time if kept else None,
                "end_time": kept.end_time if kept else None,
                "status": kept.status if kept else None
            },
            "cancelled_count": len(cancelled),
            "cancelled_bookings": [
                {
                    "id": b.id,
                    "user_name": b.user.real_name if b.user else "未知",
                    "cancel_reason": b.cancel_reason
                }
                for b in cancelled
            ]
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
