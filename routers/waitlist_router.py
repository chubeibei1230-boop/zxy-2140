from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from datetime import date
from database import get_db
from models import User, UserRole, WaitlistStatus
from schemas import WaitlistCreate, WaitlistCancel
from auth import require_roles, log_operation, get_current_user
import crud

router = APIRouter(prefix="/api/waitlist", tags=["候补预约"])


def _build_waitlist_response(db, entry):
    position = crud.get_waitlist_position_for_entry(db, entry)
    return {
        "id": entry.id,
        "user_id": entry.user_id,
        "user_name": entry.user.real_name if entry.user else "未知",
        "room_id": entry.room_id,
        "room_name": entry.room.name if entry.room else "未知",
        "start_time": entry.start_time,
        "end_time": entry.end_time,
        "reason": entry.reason,
        "status": entry.status,
        "position": position,
        "notified_at": entry.notified_at,
        "confirm_deadline": entry.confirm_deadline,
        "confirmed_at": entry.confirmed_at,
        "cancelled_at": entry.cancelled_at,
        "cancel_reason": entry.cancel_reason,
        "booking_id": entry.booking_id,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at
    }


@router.post("", summary="提交候补申请")
async def create_waitlist(
    data: WaitlistCreate,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.EXECUTOR, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        entry = crud.create_waitlist_entry(db, current_user.id, data)
        log_operation(
            db, current_user.id, "提交候补", "WaitlistEntry", entry.id,
            f"候补练习间{entry.room_id} {entry.start_time.strftime('%Y-%m-%d %H:%M')}-{entry.end_time.strftime('%H:%M')}",
            request
        )
        return _build_waitlist_response(db, entry)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/my", summary="获取我的候补记录")
async def get_my_waitlist(
    waitlist_status: WaitlistStatus = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(require_roles([UserRole.EXECUTOR, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    skip = (page - 1) * page_size
    entries, total = crud.list_waitlist_entries(
        db,
        status=waitlist_status,
        user_id=current_user.id,
        skip=skip,
        limit=page_size
    )
    items = [_build_waitlist_response(db, e) for e in entries]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/{entry_id}", summary="获取候补详情")
async def get_waitlist_detail(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    entry = crud.get_waitlist_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="候补记录不存在")

    if current_user.role not in [UserRole.ADMIN, UserRole.REVIEWER] and entry.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看该候补记录")

    return _build_waitlist_response(db, entry)


@router.post("/{entry_id}/cancel", summary="取消候补申请")
async def cancel_waitlist(
    entry_id: int,
    data: WaitlistCancel,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.EXECUTOR, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        entry = crud.cancel_waitlist_entry(db, entry_id, current_user.id, data)
        log_operation(
            db, current_user.id, "取消候补", "WaitlistEntry", entry_id,
            f"取消候补{entry_id}: {data.cancel_reason or '用户主动取消'}",
            request
        )
        return {
            "message": "候补已取消",
            "id": entry.id,
            "status": entry.status,
            "cancelled_at": entry.cancelled_at,
            "cancel_reason": entry.cancel_reason
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{entry_id}/confirm", summary="确认候补机会")
async def confirm_waitlist(
    entry_id: int,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.EXECUTOR, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        entry = crud.confirm_waitlist_entry(db, entry_id, current_user.id)
        log_operation(
            db, current_user.id, "确认候补", "WaitlistEntry", entry_id,
            f"确认候补{entry_id}，转为预约{entry.booking_id}",
            request
        )
        return _build_waitlist_response(db, entry)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", summary="获取候补列表（复核者/管理者）")
async def list_waitlist(
    waitlist_status: WaitlistStatus = None,
    room_id: int = None,
    user_id: int = None,
    start_date: date = None,
    end_date: date = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(require_roles([UserRole.REVIEWER, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    skip = (page - 1) * page_size
    entries, total = crud.list_waitlist_entries(
        db,
        status=waitlist_status,
        room_id=room_id,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=page_size
    )
    items = [_build_waitlist_response(db, e) for e in entries]
    return {
        "filters": {
            "status": waitlist_status,
            "room_id": room_id,
            "user_id": user_id,
            "start_date": start_date,
            "end_date": end_date
        },
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0
    }


@router.get("/stats/overview", summary="候补统计概览（管理者）")
async def get_waitlist_stats(
    days: int = 30,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    stats = crud.get_waitlist_statistics(db, days=days)
    return {
        "generated_at": __import__("datetime").datetime.now(),
        **stats
    }
