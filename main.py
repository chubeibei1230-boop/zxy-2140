from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import logging

from database import engine, SessionLocal
from models import Base, User, UserRole, PracticeRoom, TimeSlot, BookingRule
from auth import hash_password, log_operation
import crud

from routers.auth_router import router as auth_router
from routers.admin_router import router as admin_router
from routers.executor_router import router as executor_router
from routers.reviewer_router import router as reviewer_router
from routers.query_router import router as query_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def scheduled_lock_expiry():
    try:
        db = SessionLocal()
        count = crud.expire_locks(db)
        if count > 0:
            logger.info(f"自动释放了 {count} 个过期锁定")
        db.close()
    except Exception as e:
        logger.error(f"锁定过期处理异常: {e}")


def scheduled_no_show_process():
    try:
        db = SessionLocal()
        count = crud.process_auto_no_show(db)
        if count > 0:
            logger.info(f"自动标记了 {count} 个爽约预约")
        db.close()
    except Exception as e:
        logger.error(f"爽约自动处理异常: {e}")


def init_database():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = User(
                username="admin",
                password_hash=hash_password("admin123456"),
                real_name="系统管理员",
                role=UserRole.ADMIN,
                phone="13800000000",
                email="admin@example.com"
            )
            db.add(admin)
            logger.info("创建默认管理员账号: admin / admin123456")

        reviewer = db.query(User).filter(User.username == "reviewer").first()
        if not reviewer:
            reviewer = User(
                username="reviewer",
                password_hash=hash_password("reviewer123"),
                real_name="复核员示例",
                role=UserRole.REVIEWER,
                phone="13800000001",
                email="reviewer@example.com"
            )
            db.add(reviewer)
            logger.info("创建默认复核员账号: reviewer / reviewer123")

        executor = db.query(User).filter(User.username == "executor").first()
        if not executor:
            executor = User(
                username="executor",
                password_hash=hash_password("executor123"),
                real_name="执行者示例",
                role=UserRole.EXECUTOR,
                phone="13800000002",
                email="executor@example.com"
            )
            db.add(executor)
            logger.info("创建默认执行者账号: executor / executor123")

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
            logger.info("创建默认预约规则")

        rooms = db.query(PracticeRoom).count()
        if rooms == 0:
            room1 = PracticeRoom(
                name="钢琴练习室A",
                location="教学楼1号楼101",
                capacity=1,
                equipment="雅马哈三角钢琴1台、谱架、座椅",
                description="标准钢琴练习室，隔音良好"
            )
            room2 = PracticeRoom(
                name="钢琴练习室B",
                location="教学楼1号楼102",
                capacity=1,
                equipment="立式钢琴1台、谱架、座椅",
                description="标准钢琴练习室"
            )
            room3 = PracticeRoom(
                name="小提琴练习室",
                location="教学楼1号楼103",
                capacity=2,
                equipment="谱架、座椅、镜子",
                description="弦乐练习专用"
            )
            room4 = PracticeRoom(
                name="合奏排练室",
                location="教学楼1号楼201",
                capacity=10,
                equipment="钢琴1台、谱架10个、座椅、音响设备",
                description="适合小型合奏排练"
            )
            db.add_all([room1, room2, room3, room4])
            db.flush()
            logger.info("创建4个示例练习间")

            for room in [room1, room2, room3, room4]:
                for day in range(7):
                    slots_data = [
                        ("08:00", "10:00"),
                        ("10:00", "12:00"),
                        ("14:00", "16:00"),
                        ("16:00", "18:00"),
                        ("19:00", "21:00"),
                        ("21:00", "23:00")
                    ]
                    for start, end in slots_data:
                        slot = TimeSlot(
                            room_id=room.id,
                            day_of_week=day,
                            start_time=start,
                            end_time=end
                        )
                        db.add(slot)
            logger.info("为每个练习间创建了每日6个时段（一周7天）")

        db.commit()
        logger.info("数据库初始化完成")

    except Exception as e:
        logger.error(f"数据库初始化异常: {e}")
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("启动共享练习间预约系统后端服务...")
    init_database()

    scheduler.add_job(
        scheduled_lock_expiry,
        'interval',
        seconds=30,
        id='lock_expiry_job',
        replace_existing=True
    )
    logger.info("已启动锁定自动过期任务（每30秒执行）")

    scheduler.add_job(
        scheduled_no_show_process,
        'interval',
        minutes=5,
        id='no_show_job',
        replace_existing=True
    )
    logger.info("已启动爽约自动处理任务（每5分钟执行）")

    scheduler.start()
    logger.info("后台任务调度器已启动")

    yield

    logger.info("正在关闭服务...")
    if scheduler.running:
        scheduler.shutdown()
    logger.info("服务已关闭")


app = FastAPI(
    title="共享练习间预约系统 API",
    description="""
## 业务场景
共享练习间的预约、临时锁定、签到确认和取消释放系统。

## 使用者角色
- **管理者 (admin)**: 维护练习间、开放时段、预约规则和黑名单
- **执行者 (executor)**: 提交预约、延长锁定、签到确认
- **复核者 (reviewer)**: 确认异常占用、爽约和重复预约处理

## 核心交互
用户选择练习间和时段后，先发起**临时锁定**，锁定成功后在限定时间内提交正式预约。
正式预约成功前，其他用户不能抢占同一时段。

## 核心机制
- **临时锁过期自动释放**: 到期后自动失效，不影响查询
- **主动取消释放**: 用户主动取消或提交失败时释放
- **JWT 认证**: 所有操作需登录后使用 Bearer Token
- **操作日志**: 记录关键操作便于审计

## 默认测试账号
- 管理员: `admin` / `admin123456`
- 复核者: `reviewer` / `reviewer123`
- 执行者: `executor` / `executor123`
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(executor_router)
app.include_router(reviewer_router)
app.include_router(query_router)


@app.get("/", tags=["系统"], summary="健康检查")
async def root():
    return {
        "service": "共享练习间预约系统",
        "version": "1.0.0",
        "status": "running",
        "time": datetime.now().isoformat(),
        "docs": {
            "swagger_ui": "/docs",
            "redoc": "/redoc",
            "openapi_json": "/openapi.json"
        }
    }


@app.get("/health", tags=["系统"], summary="健康检查端点")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8119,
        reload=False
    )
