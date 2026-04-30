from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.api.router import api_router
from app.middleware.rate_limit import TriageRateLimitMiddleware

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="PainSync — AI-powered chronic pain management API",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow all origins for mobile clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting (must be added after CORS middleware)
app.add_middleware(TriageRateLimitMiddleware)

# Include all routes
app.include_router(api_router)


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy"}
