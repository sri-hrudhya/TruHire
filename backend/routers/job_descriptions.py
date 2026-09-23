import os
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Position, User
from backend.auth import get_current_user
from backend.services.ai_service import summarize_jd

router = APIRouter(tags=["job-descriptions"])


class PositionCreateRequest(BaseModel):
    title: str
    jd_text: str


class PositionUpdateRequest(BaseModel):
    title: Optional[str] = None
    jd_text: Optional[str] = None


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    jd_text: str
    jd_summary: Optional[str] = None
    jd_version: int
    created_by: str
    created_at: datetime


# Handlers that can be mapped to both /api/job-descriptions and /api/positions

def list_jds(db: Session):
    return db.query(Position).order_by(Position.created_at.desc()).all()


def create_jd(req: PositionCreateRequest, db: Session, user: User):
    if not req.title.strip() or not req.jd_text.strip():
        raise HTTPException(status_code=400, detail="Title and JD text cannot be blank.")
    
    pos = Position(
        title=req.title.strip(),
        jd_text=req.jd_text.strip(),
        jd_version=1,
        created_by=user.id,
        created_at=datetime.utcnow()
    )
    db.add(pos)
    db.commit()
    db.refresh(pos)
    return pos


def get_jd(jd_id: str, db: Session):
    pos = db.query(Position).filter(Position.id == jd_id).first()
    if not pos:
        raise HTTPException(status_code=404, detail="Job Description not found.")
    return pos


def update_jd(jd_id: str, req: PositionUpdateRequest, db: Session):
    pos = db.query(Position).filter(Position.id == jd_id).first()
    if not pos:
        raise HTTPException(status_code=404, detail="Job Description not found.")

    changed = False
    if req.title and req.title.strip() != pos.title:
        pos.title = req.title.strip()
        changed = True

    # If jd_text changed, bump version and invalidate old summary
    if req.jd_text and req.jd_text.strip() != pos.jd_text:
        pos.jd_text = req.jd_text.strip()
        pos.jd_version += 1
        pos.jd_summary = None  # Requires re-summarization
        changed = True

    if changed:
        db.commit()
        db.refresh(pos)

    return pos


def summarize_jd_endpoint(jd_id: str, db: Session):
    pos = db.query(Position).filter(Position.id == jd_id).first()
    if not pos:
        raise HTTPException(status_code=404, detail="Job Description not found.")

    summary = summarize_jd(pos.title, pos.jd_text)
    pos.jd_summary = summary
    db.commit()
    db.refresh(pos)

    return {
        "id": pos.id,
        "title": pos.title,
        "jd_version": pos.jd_version,
        "jd_summary": pos.jd_summary
    }


# Register routes on /api/job-descriptions
@router.get("/api/job-descriptions", response_model=List[PositionResponse])
def get_job_descriptions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return list_jds(db)



@router.post("/upload")
async def upload_job_description(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Upload a JD document, extract text, and create a job description.

    Supported formats: PDF, TXT, and Markdown.
    """
    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()

    if not filename:
        raise HTTPException(status_code=400, detail="No file name supplied")

    allowed = {".pdf", ".txt", ".md"}
    ext = os.path.splitext(filename)[1]
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail="Unsupported JD file type. Use PDF, TXT, or MD."
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded JD file is empty")

    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            from io import BytesIO
            reader = PdfReader(BytesIO(data))
            jd_text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        else:
            jd_text = data.decode("utf-8", errors="replace").strip()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unable to extract text from JD file: {exc}"
        )

    if not jd_text:
        raise HTTPException(
            status_code=400,
            detail="No readable text was found in the uploaded JD."
        )

    # Reuse the existing create logic/model when possible.
    title = os.path.splitext(os.path.basename(file.filename))[0].strip() or "Uploaded Job Description"

    position = Position(
        title=title,
        jd_text=jd_text,
        user_id=current_user.id,
    )
    db.add(position)
    db.commit()
    db.refresh(position)

    return position

@router.post("/api/job-descriptions", response_model=PositionResponse)
def post_job_description(req: PositionCreateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return create_jd(req, db, user)


@router.get("/api/job-descriptions/{id}", response_model=PositionResponse)
def get_job_description(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_jd(id, db)


@router.put("/api/job-descriptions/{id}", response_model=PositionResponse)
def put_job_description(id: str, req: PositionUpdateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return update_jd(id, req, db)


@router.post("/api/job-descriptions/{id}/summarize")
def post_summarize_job_description(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return summarize_jd_endpoint(id, db)


# Register backward-compatible routes on /api/positions (strictly matching the same clean methods)
@router.get("/api/positions", response_model=List[PositionResponse])
def get_positions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return list_jds(db)


@router.post("/api/positions", response_model=PositionResponse)
def post_position(req: PositionCreateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return create_jd(req, db, user)


@router.get("/api/positions/{id}", response_model=PositionResponse)
def get_position(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_jd(id, db)


@router.put("/api/positions/{id}", response_model=PositionResponse)
def put_position(id: str, req: PositionUpdateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return update_jd(id, req, db)


@router.post("/api/positions/{id}/summarize")
def post_summarize_position(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return summarize_jd_endpoint(id, db)
