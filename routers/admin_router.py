from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from datetime import date
from database import get_db
from models import User, UserRole
from schemas import (
    PracticeRoomCreate, PracticeRoomUpdate, PracticeRoomResponse,
    TimeSlotCreate, TimeSlotUpdate, TimeSlotResponse,
    BookingRuleUpdate, BookingRuleResponse,
    BlacklistCreate, BlacklistUpdate,
    FeedbackHandle, FeedbackStatus
)
from auth import require_roles, log_operation, get_current_user
import crud

router = APIRouter(prefix="/api/admin", tags=["管理者"])


# ==================== 练习间管理 ====================

@router.post("/rooms", response_model=PracticeRoomResponse, summary="创建练习间")
async def create_room(
    data: PracticeRoomCreate,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        room = crud.create_room(db, data)
        log_operation(db, current_user.id, "创建练习间", "PracticeRoom", room.id, f"创建练习间: {room.name}", request)
        return room
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/rooms", response_model=list[PracticeRoomResponse], summary="获取练习间列表")
async def list_rooms(
    is_active: bool = None,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    return crud.list_rooms(db, is_active=is_active)


@router.get("/rooms/{room_id}", response_model=PracticeRoomResponse, summary="获取练习间详情")
async def get_room(
    room_id: int,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    room = crud.get_room(db, room_id)
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="练习间不存在")
    return room


@router.put("/rooms/{room_id}", response_model=PracticeRoomResponse, summary="修改练习间")
async def update_room(
    room_id: int,
    data: PracticeRoomUpdate,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        room = crud.update_room(db, room_id, data)
        log_operation(db, current_user.id, "修改练习间", "PracticeRoom", room_id, f"修改练习间: {room_id}", request)
        return room
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ==================== 时段管理 ====================

@router.post("/time-slots", response_model=TimeSlotResponse, summary="创建开放时段")
async def create_time_slot(
    data: TimeSlotCreate,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        slot = crud.create_time_slot(db, data)
        log_operation(db, current_user.id, "创建时段", "TimeSlot", slot.id, f"创建时段: 练习间{slot.room_id} 星期{slot.day_of_week}", request)
        return slot
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/time-slots", response_model=list[TimeSlotResponse], summary="获取时段列表")
async def list_time_slots(
    room_id: int = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return crud.list_time_slots(db, room_id=room_id)


@router.put("/time-slots/{slot_id}", response_model=TimeSlotResponse, summary="修改时段")
async def update_time_slot(
    slot_id: int,
    data: TimeSlotUpdate,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        slot = crud.update_time_slot(db, slot_id, data)
        log_operation(db, current_user.id, "修改时段", "TimeSlot", slot_id, f"修改时段: {slot_id}", request)
        return slot
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/time-slots/{slot_id}", summary="删除时段")
async def delete_time_slot(
    slot_id: int,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        crud.delete_time_slot(db, slot_id)
        log_operation(db, current_user.id, "删除时段", "TimeSlot", slot_id, f"删除时段: {slot_id}", request)
        return {"message": "删除成功"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ==================== 预约规则 ====================

@router.get("/booking-rule", response_model=BookingRuleResponse, summary="获取预约规则")
async def get_booking_rule(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return crud.get_booking_rule(db)


@router.put("/booking-rule", response_model=BookingRuleResponse, summary="修改预约规则")
async def update_booking_rule(
    data: BookingRuleUpdate,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    rule = crud.update_booking_rule(db, data)
    log_operation(db, current_user.id, "修改预约规则", "BookingRule", rule.id, "修改预约规则", request)
    return rule


# ==================== 黑名单管理 ====================

@router.post("/blacklist", summary="添加黑名单")
async def create_blacklist(
    data: BlacklistCreate,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        record = crud.create_blacklist(db, data, current_user.id)
        log_operation(db, current_user.id, "添加黑名单", "Blacklist", record.id, f"将用户{data.user_id}加入黑名单", request)
        return {
            "id": record.id,
            "user_id": record.user_id,
            "user_name": record.user.real_name if record.user else "未知",
            "reason": record.reason,
            "added_by_name": record.admin.real_name if record.admin else "未知",
            "start_date": record.start_date,
            "end_date": record.end_date,
            "is_active": record.is_active,
            "created_at": record.created_at
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/blacklist", summary="获取黑名单列表")
async def list_blacklist(
    is_active: bool = None,
    user_id: int = None,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    records = crud.list_blacklist(db, is_active=is_active, user_id=user_id)
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "user_name": r.user.real_name if r.user else "未知",
            "reason": r.reason,
            "added_by_name": r.admin.real_name if r.admin else "未知",
            "start_date": r.start_date,
            "end_date": r.end_date,
            "is_active": r.is_active,
            "created_at": r.created_at
        }
        for r in records
    ]


@router.put("/blacklist/{record_id}", summary="修改黑名单记录")
async def update_blacklist(
    record_id: int,
    data: BlacklistUpdate,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        record = crud.update_blacklist(db, record_id, data)
        log_operation(db, current_user.id, "修改黑名单", "Blacklist", record_id, f"修改黑名单记录: {record_id}", request)
        return {
            "id": record.id,
            "user_id": record.user_id,
            "user_name": record.user.real_name if record.user else "未知",
            "reason": record.reason,
            "added_by_name": record.admin.real_name if record.admin else "未知",
            "start_date": record.start_date,
            "end_date": record.end_date,
            "is_active": record.is_active,
            "created_at": record.created_at
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ==================== 反馈管理 ====================

@router.get("/feedbacks", summary="获取反馈列表（多条件筛选）")
async def list_feedbacks(
    room_id: int = None,
    user_id: int = None,
    start_date: date = None,
    end_date: date = None,
    min_rating: int = None,
    max_rating: int = None,
    status: FeedbackStatus = None,
    needs_follow_up: bool = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.REVIEWER])),
    db: Session = Depends(get_db)
):
    skip = (page - 1) * page_size
    feedbacks, total = crud.list_feedbacks(
        db,
        room_id=room_id,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        min_rating=min_rating,
        max_rating=max_rating,
        status=status,
        needs_follow_up=needs_follow_up,
        skip=skip,
        limit=page_size
    )
    items = []
    for f in feedbacks:
        booking = crud.get_booking(db, f.booking_id)
        items.append({
            "id": f.id,
            "booking_id": f.booking_id,
            "user_id": f.user_id,
            "user_name": f.user.real_name if f.user else "未知",
            "room_id": booking.room_id if booking else None,
            "room_name": booking.room.name if booking and booking.room else "未知",
            "check_out_time": f.check_out_time,
            "actual_usage": f.actual_usage,
            "equipment_rating": f.equipment_rating,
            "environment_rating": f.environment_rating,
            "overall_rating": f.overall_rating,
            "problem_description": f.problem_description,
            "needs_follow_up": f.needs_follow_up,
            "status": f.status,
            "handled_by_name": f.handler.real_name if f.handler else None,
            "handled_at": f.handled_at,
            "handling_result": f.handling_result,
            "created_at": f.created_at,
            "updated_at": f.updated_at,
            "booking_info": {
                "id": booking.id if booking else None,
                "start_time": booking.start_time if booking else None,
                "end_time": booking.end_time if booking else None,
                "status": booking.status if booking else None,
                "purpose": booking.purpose if booking else None
            } if booking else None
        })
    return {
        "filters": {
            "room_id": room_id,
            "user_id": user_id,
            "start_date": start_date,
            "end_date": end_date,
            "min_rating": min_rating,
            "max_rating": max_rating,
            "status": status,
            "needs_follow_up": needs_follow_up
        },
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0
    }


@router.get("/feedbacks/{feedback_id}", summary="获取反馈详情")
async def get_feedback(
    feedback_id: int,
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.REVIEWER])),
    db: Session = Depends(get_db)
):
    feedback = crud.get_feedback(db, feedback_id)
    if not feedback:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈记录不存在")
    booking = crud.get_booking(db, feedback.booking_id)
    return {
        "id": feedback.id,
        "booking_id": feedback.booking_id,
        "user_id": feedback.user_id,
        "user_name": feedback.user.real_name if feedback.user else "未知",
        "room_id": booking.room_id if booking else None,
        "room_name": booking.room.name if booking and booking.room else "未知",
        "check_out_time": feedback.check_out_time,
        "actual_usage": feedback.actual_usage,
        "equipment_rating": feedback.equipment_rating,
        "environment_rating": feedback.environment_rating,
        "overall_rating": feedback.overall_rating,
        "problem_description": feedback.problem_description,
        "needs_follow_up": feedback.needs_follow_up,
        "status": feedback.status,
        "handled_by_name": feedback.handler.real_name if feedback.handler else None,
        "handled_at": feedback.handled_at,
        "handling_result": feedback.handling_result,
        "created_at": feedback.created_at,
        "updated_at": feedback.updated_at,
        "booking_info": {
            "id": booking.id if booking else None,
            "start_time": booking.start_time if booking else None,
            "end_time": booking.end_time if booking else None,
            "check_in_time": booking.check_in_time if booking else None,
            "check_out_time": booking.check_out_time if booking else None,
            "status": booking.status if booking else None,
            "purpose": booking.purpose if booking else None
        } if booking else None
    }


@router.put("/feedbacks/{feedback_id}/handle", summary="处理反馈（标记处理结果）")
async def handle_feedback(
    feedback_id: int,
    data: FeedbackHandle,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.REVIEWER])),
    db: Session = Depends(get_db)
):
    try:
        feedback = crud.handle_feedback(db, feedback_id, current_user.id, data)
        log_operation(
            db, current_user.id, "处理反馈", "Feedback", feedback_id,
            f"处理反馈{feedback_id}: {data.handling_result}",
            request
        )
        booking = crud.get_booking(db, feedback.booking_id)
        return {
            "message": "反馈已处理",
            "id": feedback.id,
            "status": feedback.status,
            "handled_at": feedback.handled_at,
            "handling_result": feedback.handling_result,
            "handled_by_name": feedback.handler.real_name if feedback.handler else None,
            "room_name": booking.room.name if booking and booking.room else "未知"
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
