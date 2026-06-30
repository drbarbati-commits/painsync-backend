from __future__ import annotations

import logging
from typing import Optional

import firebase_admin
from firebase_admin import credentials, messaging
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.user import User

logger = logging.getLogger(__name__)

_FIREBASE_APP: Optional[firebase_admin.App] = None
_FIREBASE_CRED_PATH = "serviceAccountKey.json"


def _init_firebase() -> bool:
    global _FIREBASE_APP
    if _FIREBASE_APP is not None:
        return True
    try:
        cred = credentials.Certificate(_FIREBASE_CRED_PATH)
        _FIREBASE_APP = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized")
        return True
    except Exception:
        logger.exception("Failed to initialize Firebase Admin SDK")
        return False


def send_push_notification(user_id: int, title: str, body: str) -> bool:
    if not _init_firebase():
        logger.warning("Firebase not available, skipping push notification")
        return False

    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.device_token:
            logger.warning("User %d has no device token", user_id)
            return False

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            token=user.device_token,
        )
        response = messaging.send(message)
        logger.info("Push sent to user %d, message ID: %s", user_id, response)
        return True
    except messaging.UnregisteredError:
        logger.warning("Device token for user %d is invalid, clearing", user_id)
        db.query(User).filter(User.id == user_id).update(
            {User.device_token: None, User.device_platform: None}
        )
        db.commit()
        return False
    except Exception:
        logger.exception("Failed to send push to user %d", user_id)
        return False
    finally:
        db.close()
