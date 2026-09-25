import os
from datetime import datetime
from io import BytesIO
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import Position, User
from backend.auth import get_current_user
from backend.services.ai_service import summarize_jd

router = APIRouter(tags=["job-descriptions"])
class PositionCreateRequest(BaseModel): title: str; jd_text: str
class PositionUpdateRequest(BaseModel): title: Optional[str] = None; jd_text: Optional[str] = None
class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str; title: str; jd_text: str; jd_summary: Optional[str] = None; jd_version: int; created_by: str; created_at: datetime

def list_jds(db): return db.query(Position).order_by(Position.created_at.desc()).all()
def create_jd(req, db, user):
    if not req.title.strip() or not req.jd_text.strip(): raise HTTPException(400, "Title and JD text cannot be blank.")
    pos = Position(title=req.title.strip(), jd_text=req.jd_text.strip(), jd_version=1, created_by=user.id, created_at=datetime.utcnow()); db.add(pos); db.commit(); db.refresh(pos); return pos

def get_jd(jd_id, db):
    pos = db.query(Position).filter(Position.id == jd_id).first()
    if not pos: raise HTTPException(404, "Job Description not found.")
    return pos

def update_jd(jd_id, req, db):
    pos = get_jd(jd_id, db); changed = False
    if req.title and req.title.strip() != pos.title: pos.title = req.title.strip(); changed = True
    if req.jd_text and req.jd_text.strip() != pos.jd_text: pos.jd_text = req.jd_text.strip(); pos.jd_version += 1; pos.jd_summary = None; changed = True
    if changed: db.commit(); db.refresh(pos)
    return pos

def summarize_jd_endpoint(jd_id, db):
    pos = get_jd(jd_id, db); pos.jd_summary = summarize_jd(pos.title, pos.jd_text); db.commit(); db.refresh(pos)
    return {"id": pos.id, "title": pos.title, "jd_version": pos.jd_version, "jd_summary": pos.jd_summary}

@router.get("/api/job-descriptions", response_model=List[PositionResponse])
def get_job_descriptions(db: Session = Depends(get_db), user: User = Depends(get_current_user)): return list_jds(db)
@router.post("/api/job-descriptions", response_model=PositionResponse)
def post_job_description(req: PositionCreateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)): return create_jd(req, db, user)

@router.post("/api/job-descriptions/upload", response_model=PositionResponse)
async def upload_job_description(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    filename = file.filename or "job_description.txt"; ext = os.path.splitext(filename)[1].lower()
    if ext not in {".pdf", ".txt", ".md"}: raise HTTPException(400, "Unsupported JD file type. Use PDF, TXT, or MD.")
    data = await file.read()
    if not data: raise HTTPException(400, "Uploaded JD file is empty.")
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(data)); text = "\n".join((p.extract_text() or "") for p in reader.pages).strip()
    else: text = data.decode("utf-8", errors="replace").strip()
    if not text: raise HTTPException(400, "No readable text found in the uploaded JD.")
    title = os.path.splitext(os.path.basename(filename))[0].replace("_", " ").replace("-", " ").strip() or "Uploaded Job Description"
    return create_jd(PositionCreateRequest(title=title, jd_text=text), db, user)

@router.get("/api/job-descriptions/{id}", response_model=PositionResponse)
def get_job_description(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)): return get_jd(id, db)
@router.put("/api/job-descriptions/{id}", response_model=PositionResponse)
def put_job_description(id: str, req: PositionUpdateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)): return update_jd(id, req, db)
@router.post("/api/job-descriptions/{id}/summarize")
def post_summarize_job_description(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)): return summarize_jd_endpoint(id, db)

@router.get("/api/positions", response_model=List[PositionResponse])
def get_positions(db: Session = Depends(get_db), user: User = Depends(get_current_user)): return list_jds(db)
@router.post("/api/positions", response_model=PositionResponse)
def post_position(req: PositionCreateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)): return create_jd(req, db, user)
@router.get("/api/positions/{id}", response_model=PositionResponse)
def get_position(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)): return get_jd(id, db)
@router.put("/api/positions/{id}", response_model=PositionResponse)
def put_position(id: str, req: PositionUpdateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)): return update_jd(id, req, db)
@router.post("/api/positions/{id}/summarize")
def post_summarize_position(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)): return summarize_jd_endpoint(id, db)
