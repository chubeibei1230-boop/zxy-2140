from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from datetime import date
from database import get_db
from models import User, UserRole, AppealStatus, AppealType
from schemas import AppealCreate, AppealReview
from auth import require_roles, log_operation, get_current_user
import crud

router = APIRouter(prefix="/api/appeals", tags=["申诉管理"])


def _build_appeal_response(db, appeal):
    target_info = crud.get_appeal_target_info(db, appeal)
    return {
        "id": appeal.id,
        "user_id": appeal.user_id,
        "user_name": appeal.user.real_name if appeal.user else "未知",
        "appeal_type": appeal.appeal_type,
        "target_type": appeal.target_type,
        "target_id": appeal.target_id,
        "target_info": target_info,
        "reason": appeal.reason,
        "supplement": appeal.supplement,
        "status": appeal.status,
        "reviewer_id": appeal.reviewer_id,
        "reviewer_name": appeal.reviewer.real_name if appeal.reviewer else None,
        "review_opinion": appeal.review_opinion,
        "reviewed_at": appeal.reviewed_at,
        "created_at": appeal.created_at,
        "updated_at": appeal.updated_at
    }


@router.post("", summary="提交申诉")
async def create_appeal(
    data: AppealCreate,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.EXECUTOR, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        appeal = crud.create_appeal(db, current_user.id, data)
        log_operation(
            db, current_user.id, "提交申诉", "Appeal", appeal.id,
            f"申诉类型:{data.appeal_type.value} 目标:{data.target_type}/{data.target_id}",
            request
        )
        db.commit()
        return _build_appeal_response(db, appeal)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/my", summary="获取我的申诉列表")
async def get_my_appeals(
    status: AppealStatus = None,
    appeal_type: AppealType = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(require_roles([UserRole.EXECUTOR, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    skip = (page - 1) * page_size
    appeals, total = crud.list_appeals(
        db,
        status=status,
        appeal_type=appeal_type,
        user_id=current_user.id,
        skip=skip,
        limit=page_size
    )
    items = [_build_appeal_response(db, a) for a in appeals]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/{appeal_id}", summary="获取申诉详情")
async def get_appeal_detail(
    appeal_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    appeal = crud.get_appeal(db, appeal_id)
    if not appeal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="申诉记录不存在")

    if current_user.role not in [UserRole.ADMIN, UserRole.REVIEWER] and appeal.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看该申诉记录")

    return _build_appeal_response(db, appeal)


@router.get("", summary="获取申诉列表（复核者/管理者）")
async def list_appeals(
    status: AppealStatus = None,
    appeal_type: AppealType = None,
    user_id: int = None,
    start_date: date = None,
    end_date: date = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(require_roles([UserRole.REVIEWER, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    skip = (page - 1) * page_size
    appeals, total = crud.list_appeals(
        db,
        status=status,
        appeal_type=appeal_type,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=page_size
    )
    items = [_build_appeal_response(db, a) for a in appeals]
    return {
        "filters": {
            "status": status,
            "appeal_type": appeal_type,
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


@router.post("/{appeal_id}/review", summary="审核申诉（通过/驳回）")
async def review_appeal(
    appeal_id: int,
    data: AppealReview,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.REVIEWER, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        appeal = crud.review_appeal(db, appeal_id, current_user.id, data)
        log_operation(
            db, current_user.id, "审核申诉", "Appeal", appeal_id,
            f"审核结果:{data.status.value} 意见:{data.review_opinion}",
            request
        )
        db.commit()
        return {
            "message": "审核完成",
            "appeal": _build_appeal_response(db, appeal)
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/stats/overview", summary="申诉统计概览（管理者）")
async def get_appeal_stats(
    days: int = 30,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    stats = crud.get_appeal_statistics(db, days=days)
    return {
        "generated_at": __import__("datetime").datetime.now(),
        **stats
    }
