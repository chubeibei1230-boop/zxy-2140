from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from database import get_db
from models import User, UserRole
from schemas import (
    UserCreate, UserUpdate, UserResponse, Token,
    PasswordChange
)
from auth import (
    get_current_user, require_roles, create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES, log_operation
)
import crud

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/register", response_model=Token, summary="用户注册")
async def register(user_data: UserCreate, request: Request, db: Session = Depends(get_db)):
    try:
        user = crud.create_user(db, user_data)
        log_operation(db, user.id, "用户注册", "User", user.id, f"新用户注册: {user.username}", request)
        access_token = create_access_token(
            data={"sub": str(user.id), "role": user.role},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        return Token(access_token=access_token, user=user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/login", response_model=Token, summary="用户登录")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = crud.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        log_operation(db, None, "登录失败", "Auth", None, f"登录失败，用户名: {form_data.username}", request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    log_operation(db, user.id, "用户登录", "Auth", None, f"用户登录: {user.username}", request)
    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return Token(access_token=access_token, user=user)


@router.get("/me", response_model=UserResponse, summary="获取当前用户信息")
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me/password", summary="修改当前用户密码")
async def change_password(
    data: PasswordChange,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        crud.update_user_password(db, current_user.id, data)
        log_operation(db, current_user.id, "修改密码", "User", current_user.id, "用户修改密码", request)
        return {"message": "密码修改成功"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/me/profile", response_model=UserResponse, summary="修改当前用户信息")
async def update_profile(
    data: UserUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        user = crud.update_user(db, current_user.id, data)
        log_operation(db, current_user.id, "修改资料", "User", current_user.id, "用户修改个人信息", request)
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/users", summary="用户列表（管理者）")
async def list_users(
    role: str = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    skip = (page - 1) * page_size
    users, total = crud.list_users(db, role=role, skip=skip, limit=page_size)
    return {
        "items": [UserResponse.model_validate(u).model_dump() for u in users],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.post("/users", response_model=UserResponse, summary="创建用户（管理者）")
async def admin_create_user(
    user_data: UserCreate,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        user = crud.create_user(db, user_data)
        log_operation(db, current_user.id, "创建用户", "User", user.id, f"管理员创建用户: {user.username}", request)
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/users/{user_id}", response_model=UserResponse, summary="修改用户信息（管理者）")
async def admin_update_user(
    user_id: int,
    data: UserUpdate,
    request: Request,
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        user = crud.update_user(db, user_id, data)
        log_operation(db, current_user.id, "修改用户", "User", user_id, f"管理员修改用户信息: {user_id}", request)
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
