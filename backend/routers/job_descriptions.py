import os
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Position, User
from backend.auth import get_current_user
from backend.services.ingestion.parsing import extract_text_from_file, is_supported_jd_file, SUPPORTED_JD_EXTENSIONS
from backend.services.ingestion.storage import save_upload_file
from backend.services.llm.ai_service import summarize_jd

router = APIRouter(tags=["job-descriptions"])


class PositionCreateRequest(BaseModel):
    title: str
    jd_text: str
    file_url: Optional[str] = None
    original_filename: Optional[str] = None


class PositionUpdateRequest(BaseModel):
    title: Optional[str] = None
    jd_text: Optional[str] = None
    file_url: Optional[str] = None
    original_filename: Optional[str] = None


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    jd_text: str
    jd_summary: Optional[str] = None
    jd_version: int
    created_by: str
    created_at: datetime
    file_url: Optional[str] = None
    original_filename: Optional[str] = None


class JDExtractResponse(BaseModel):
    title: str
    jd_text: str
    original_filename: str
    file_url: str


def list_jds(db: Session):
    return db.query(Position).order_by(Position.created_at.desc()).all()


def create_jd(req: PositionCreateRequest, db: Session, user: User) -> Position:
    if not req.title.strip() or not req.jd_text.strip():
        raise HTTPException(400, "Title and JD text cannot be blank.")
    pos = Position(
        title=req.title.strip(),
        jd_text=req.jd_text.strip(),
        jd_version=1,
        created_by=user.id,
        created_at=datetime.utcnow(),
        file_url=req.file_url,
        original_filename=req.original_filename,
    )
    db.add(pos)
    db.commit()
    db.refresh(pos)
    return pos


def get_jd(jd_id: str, db: Session) -> Position:
    pos = db.query(Position).filter(Position.id == jd_id).first()
    if not pos:
        raise HTTPException(404, "Job Description not found.")
    return pos


def update_jd(jd_id: str, req: PositionUpdateRequest, db: Session) -> Position:
    pos = get_jd(jd_id, db)
    changed = False
    if req.title and req.title.strip() != pos.title:
        pos.title = req.title.strip()
        changed = True
    if req.jd_text and req.jd_text.strip() != pos.jd_text:
        pos.jd_text = req.jd_text.strip()
        pos.jd_version += 1
        pos.jd_summary = None
        changed = True
    if req.file_url is not None:
        pos.file_url = req.file_url
        changed = True
    if req.original_filename is not None:
        pos.original_filename = req.original_filename
        changed = True
    if changed:
        db.commit()
        db.refresh(pos)
    return pos


def summarize_jd_endpoint(jd_id: str, db: Session):
    pos = get_jd(jd_id, db)
    pos.jd_summary = summarize_jd(pos.title, pos.jd_text)
    db.commit()
    db.refresh(pos)
    return {"id": pos.id, "title": pos.title, "jd_version": pos.jd_version, "jd_summary": pos.jd_summary}


async def _handle_jd_file_upload(file: UploadFile):
    filename = file.filename or "job_description.txt"
    if not is_supported_jd_file(filename):
        raise HTTPException(
            400,
            f"Unsupported file format '{os.path.splitext(filename)[1]}'. "
            "Supported formats: PDF (.pdf), Word Documents (.docx, .doc, .rtf, .odt, .txt, .md), "
            "and Images (.jpg, .jpeg, .png, .webp, .bmp, .tiff)."
        )

    data = await file.read()
    if not data:
        raise HTTPException(400, "Uploaded JD file is empty.")

    # Save to dedicated JD storage folder
    file_url, _ = save_upload_file(filename, data, category="job_descriptions")

    # Extract text using comprehensive parser (PDF / Docx / RapidOCR for images)
    try:
        extracted_text = extract_text_from_file(filename, data)
    except Exception as exc:
        raise HTTPException(500, f"Error processing file for text extraction: {exc}")

    if not extracted_text or not extracted_text.strip():
        raise HTTPException(400, "No readable text found in the uploaded JD file.")

    raw_title = os.path.splitext(os.path.basename(filename))[0].replace("_", " ").replace("-", " ").strip()
    clean_title = raw_title or "Uploaded Job Description"

    return clean_title, extracted_text.strip(), file_url, filename


# ============================================================
# API Endpoints
# ============================================================

@router.get("/api/job-descriptions", response_model=List[PositionResponse])
def get_job_descriptions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return list_jds(db)


@router.post("/api/job-descriptions", response_model=PositionResponse)
def post_job_description(req: PositionCreateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return create_jd(req, db, user)


@router.post("/api/job-descriptions/upload", response_model=PositionResponse)
async def upload_job_description(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Upload a JD file (PDF, Word Document, or Image), extract text, save file in dedicated JD directory,
    and persist as a Position.
    """
    clean_title, extracted_text, file_url, filename = await _handle_jd_file_upload(file)
    final_title = title.strip() if (title and title.strip()) else clean_title

    pos_req = PositionCreateRequest(
        title=final_title,
        jd_text=extracted_text,
        file_url=file_url,
        original_filename=filename,
    )
    return create_jd(pos_req, db, user)


@router.post("/api/job-descriptions/extract-text", response_model=JDExtractResponse)
async def extract_job_description_text(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """
    Upload a JD file (PDF, Word Document, or Image), save in dedicated folder, and return
    extracted text without immediately creating the position, allowing user review/edit in UI.
    """
    clean_title, extracted_text, file_url, filename = await _handle_jd_file_upload(file)
    return JDExtractResponse(
        title=clean_title,
        jd_text=extracted_text,
        original_filename=filename,
        file_url=file_url,
    )


@router.get("/api/job-descriptions/{id}", response_model=PositionResponse)
def get_job_description(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_jd(id, db)


@router.put("/api/job-descriptions/{id}", response_model=PositionResponse)
def put_job_description(id: str, req: PositionUpdateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return update_jd(id, req, db)


@router.post("/api/job-descriptions/{id}/summarize")
def post_summarize_job_description(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return summarize_jd_endpoint(id, db)


# ============================================================
# Mirrors on /api/positions for backwards compatibility
# ============================================================

@router.get("/api/positions", response_model=List[PositionResponse])
def get_positions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return list_jds(db)


@router.post("/api/positions", response_model=PositionResponse)
def post_position(req: PositionCreateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return create_jd(req, db, user)


@router.post("/api/positions/upload", response_model=PositionResponse)
async def post_position_upload(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await upload_job_description(file=file, title=title, db=db, user=user)


@router.post("/api/positions/extract-text", response_model=JDExtractResponse)
async def post_position_extract_text(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    return await extract_job_description_text(file=file, user=user)


@router.get("/api/positions/{id}", response_model=PositionResponse)
def get_position(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_jd(id, db)


@router.put("/api/positions/{id}", response_model=PositionResponse)
def put_position(id: str, req: PositionUpdateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return update_jd(id, req, db)


@router.post("/api/positions/{id}/summarize")
def post_summarize_position(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return summarize_jd_endpoint(id, db)
