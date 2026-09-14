import uuid

from .users_handler import handle_get_profile
from .users_schema import ProfileResponse


def get_profile(user_id: uuid.UUID, access_token_expires_in: int) -> ProfileResponse:
    return handle_get_profile(user_id, access_token_expires_in)
