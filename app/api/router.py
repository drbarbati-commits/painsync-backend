from fastapi import APIRouter
from app.api.routes import auth, pain_log, chat, triage, users, analytics, wellness, activity_log, upload, social_auth

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(pain_log.router)
api_router.include_router(chat.router)
api_router.include_router(triage.router)
api_router.include_router(users.router)
api_router.include_router(analytics.router)
api_router.include_router(wellness.router)
api_router.include_router(activity_log.router)
api_router.include_router(upload.router)
api_router.include_router(social_auth.router)
