from fastapi import APIRouter
from app.api.routes import auth, pain_log, chat, triage, users, analytics

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(pain_log.router)
api_router.include_router(chat.router)
api_router.include_router(triage.router)
api_router.include_router(users.router)
api_router.include_router(analytics.router)
