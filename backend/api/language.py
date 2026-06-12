from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.language_service import language_service

router = APIRouter(prefix="/api/language", tags=["language"])


class DetectRequest(BaseModel):
    text: str


class DetectResponse(BaseModel):
    language_code: str | None
    method: str


class DetectBatchRequest(BaseModel):
    texts: list[str]


class DetectBatchResponse(BaseModel):
    results: list[DetectResponse]


@router.post("/detect", response_model=DetectResponse)
def detect_language(req: DetectRequest):
    code, method = language_service.detect_language(req.text)
    return DetectResponse(language_code=code, method=method)


@router.post("/detect-batch", response_model=DetectBatchResponse)
def detect_batch(req: DetectBatchRequest):
    results = language_service.detect_batch(req.texts)
    return DetectBatchResponse(
        results=[DetectResponse(language_code=code, method=method) for code, method in results]
    )
