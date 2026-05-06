"""FastAPI application entry point.

Intelligent Travel Planning Agent System.
Based on LangGraph + MCP multi-agent collaboration.
"""

import logging
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.config.settings import settings
from src.api.deps import initialize_services, shutdown_services
from src.api.routes.travel import router as travel_router
from src.api.routes.feedback import router as feedback_router
from src.api.middleware.session import RequestLoggingMiddleware

# ============================================================
# Logging Configuration
# ============================================================

def setup_logging():
    """Configure structured logging."""
    fmt = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if settings.debug else logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)

    # Quiet noisy libraries
    for lib in [
        "httpx", "httpcore", "openai", "chromadb", "urllib3",
        "h2", "hpack", "rustls", "reqwest", "hyper_util",
        "cookie_store", "primp", "ddgs",
    ]:
        logging.getLogger(lib).setLevel(logging.WARNING)


setup_logging()
logger = logging.getLogger(__name__)


# ============================================================
# Application Lifespan
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle for the FastAPI application."""
    logger.info("=" * 60)
    logger.info("  Intelligent Travel Planning Agent System")
    logger.info("  Powered by LangGraph + MCP Multi-Agent")
    logger.info("=" * 60)

    await initialize_services()

    yield

    await shutdown_services()
    logger.info("Application stopped")


# ============================================================
# FastAPI Application
# ============================================================

app = FastAPI(
    title="智能旅游规划 Agent",
    description="""
基于 LangGraph 和 MCP 协议的多 Agent 协同旅游规划系统。

## 核心功能
- **智能规划**: 将复杂旅行需求分解为结构化执行步骤
- **多 Agent 协同**: 父Agent+6个子Agent（交通/地图/天气/酒店/搜索/文件）
- **ReAct 推理**: Think-Act-Observe 循环执行
- **人工介入**: LLM自主判断信息不足并请求用户补充
- **增量优化**: 基于用户反馈智能调整，保留未调整部分
- **智能缓存**: RAG检索历史结果，避免重复MCP调用
- **上下文管理**: 消息压缩算法控制Token消耗

## 工作流
Plan → Execute → Replan → 循环，直到完成或需要人工介入
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ============================================================
# Middleware
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestLoggingMiddleware)


# ============================================================
# Routes
# ============================================================

app.include_router(travel_router)
app.include_router(feedback_router)


# ============================================================
# Static Files (Frontend)
# ============================================================

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")
    if (FRONTEND_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")


# ============================================================
# Health Check
# ============================================================

@app.get("/health")
async def health_check():
    """Service health check."""
    return {
        "status": "healthy",
        "service": "travel-planning-agent",
        "version": "1.0.0",
    }


@app.get("/")
async def serve_index():
    """Serve the frontend SPA entry page."""
    from fastapi.responses import FileResponse
    index_path = FRONTEND_DIR / "index.html"
    return FileResponse(str(index_path))


# ============================================================
# Direct run
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
    )
