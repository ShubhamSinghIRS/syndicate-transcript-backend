import uuid

from fastapi import APIRouter, Depends

from apis.controllers.transcripts import transcripts_controller
from apis.controllers.transcripts.transcripts_schema import TranscriptFilterRequest
from apis.dependencies import get_current_user_id
from apis.rate_limiting.dependencies import rate_limit_transcripts_public
from utils.pagination import PaginationParams
from utils.response import pdf_response, success_response

from .paths import P

router = APIRouter(prefix=P.transcripts.BASE, tags=["Transcripts"])


@router.get(P.transcripts.LIST, dependencies=[Depends(rate_limit_transcripts_public)])
def list_transcripts(params: PaginationParams = Depends()):
    result = transcripts_controller.list_transcripts(params)
    return success_response(data=result)


@router.post(P.transcripts.FILTER, dependencies=[Depends(rate_limit_transcripts_public)])
def filter_transcripts(filters: TranscriptFilterRequest):
    result = transcripts_controller.filter_transcripts(filters)
    return success_response(data=result)


@router.get(P.transcripts.MY_PURCHASED)
def list_purchased_transcripts(
    params: PaginationParams = Depends(),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    result = transcripts_controller.list_purchased_transcripts(user_id, params)
    return success_response(data=result)


@router.get(P.transcripts.DOMAINS, dependencies=[Depends(rate_limit_transcripts_public)])
def list_domains():
    result = transcripts_controller.list_domains()
    return success_response(data=result)


@router.get(P.transcripts.FILTER_BOUNDS, dependencies=[Depends(rate_limit_transcripts_public)])
def get_filter_bounds():
    result = transcripts_controller.get_filter_bounds()
    return success_response(data=result)


@router.get(P.transcripts.DETAIL, dependencies=[Depends(rate_limit_transcripts_public)])
def get_transcript_detail(transcript_id: uuid.UUID):
    result = transcripts_controller.get_transcript_detail(transcript_id)
    return success_response(data=result)


@router.get(P.transcripts.SIMILAR, dependencies=[Depends(rate_limit_transcripts_public)])
def get_similar_transcripts(transcript_id: uuid.UUID, limit: int = 10):
    result = transcripts_controller.get_similar_transcripts(transcript_id, limit)
    return success_response(data=result)


# Streams the real PDF bytes inline (proxied from storage) so the frontend can
# render it in-page. Bytes come through this API, so no storage-bucket CORS needed.
@router.get(P.transcripts.VIEW)
def view_transcript(transcript_id: uuid.UUID, user_id: uuid.UUID = Depends(get_current_user_id)):
    pdf_bytes = transcripts_controller.get_transcript_file(user_id, transcript_id)
    return pdf_response(pdf_bytes, f"transcript-{transcript_id}.pdf", disposition="inline")


@router.get(P.transcripts.DOWNLOAD)
def download_transcript(transcript_id: uuid.UUID, user_id: uuid.UUID = Depends(get_current_user_id)):
    pdf_bytes = transcripts_controller.get_transcript_file(user_id, transcript_id)
    return pdf_response(pdf_bytes, f"transcript-{transcript_id}.pdf", disposition="attachment")
