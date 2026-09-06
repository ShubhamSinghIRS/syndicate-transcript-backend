from fastapi import APIRouter

from .auth import router as auth_router
from .cart import router as cart_router
from .inquiries import support_router, topics_router
from .orders import router as orders_router, webhook_router as orders_webhook_router
from .system import router as system_router
from .transcript_ingest import router as transcript_ingest_router
from .transcripts import router as transcripts_router
from .users import router as users_router

api_router = APIRouter()
api_router.include_router(system_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(transcripts_router)
api_router.include_router(transcript_ingest_router)
api_router.include_router(cart_router)
api_router.include_router(orders_router)
api_router.include_router(orders_webhook_router)
api_router.include_router(support_router)
api_router.include_router(topics_router)
