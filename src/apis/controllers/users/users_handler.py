import logging
import uuid

from fastapi import HTTPException

from apis.models.user import User
from services.database.postgres.connection import get_session

from .users_schema import ProfileResponse

logger = logging.getLogger(__name__)


def handle_get_profile(user_id: uuid.UUID, access_token_expires_in: int) -> ProfileResponse:
    session = get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return ProfileResponse(
            id=str(user.id),
            name=user.name,
            email=user.email,
            companyName=user.company_name,
            accessTokenExpiresIn=access_token_expires_in,
        )
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        logger.exception("Failed to fetch profile")
        raise HTTPException(status_code=500, detail="Internal error") from None
    finally:
        session.close()
