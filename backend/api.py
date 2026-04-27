from fastapi import APIRouter, Form, UploadFile, File, HTTPException, Depends
from typing import List, Annotated, Optional, Generator
import logging
import time
import json

# Import our new generator function
from core.briefing_generator import generate_intelligence_brief, extract_text_from_file

# Import DB models
from sqlalchemy.orm import Session
from backend.models import SessionLocal, Project, MeetingSession, Requirement

router = APIRouter()

# ------------------------
# DB Session Helper
# ------------------------
def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------------
# Project Serialization Helper (list view — lightweight)
# ------------------------
def serialize_project_summary(p: Project, db: Session) -> dict:
    session_count = db.query(MeetingSession).filter(MeetingSession.project_id == p.id).count()
    req_count = db.query(Requirement).join(MeetingSession).filter(MeetingSession.project_id == p.id).count()
    return {
        "id": p.id,
        "client_name": p.client_name,
        "industry": p.industry,
        "has_brief": bool(p.pre_meeting_brief),
        "has_discovery_plan": bool(p.discovery_plan_json),
        "session_count": session_count,
        "requirement_count": req_count,
    }

# ------------------------
# Project Serialization Helper (detail view — full data)
# ------------------------
def serialize_project_detail(p: Project, db: Session) -> dict:
    session_count = db.query(MeetingSession).filter(MeetingSession.project_id == p.id).count()
    req_count = db.query(Requirement).join(MeetingSession).filter(MeetingSession.project_id == p.id).count()
    return {
        "id": p.id,
        "client_name": p.client_name,
        "industry": p.industry,
        "sow_text": p.sow_text,
        "discovery_plan_json": p.discovery_plan_json,
        "pre_meeting_brief": p.pre_meeting_brief,
        "has_discovery_plan": bool(p.discovery_plan_json),
        "session_count": session_count,
        "requirement_count": req_count,
    }

# ------------------------
# Module 1 Endpoint: Generate Brief
# ------------------------
@router.post("/generate-brief")
async def generate_brief_endpoint(
    client_name: Annotated[str, Form()],
    industry: Annotated[str, Form()],
    ba_input: Annotated[str, Form()],
    presales_doc: Annotated[UploadFile, File()],
    additional_docs: Annotated[Optional[List[UploadFile]], File()] = None,
    additional_explanations: Annotated[Optional[List[str]], Form()] = None,
    db: Session = Depends(get_db)
):
    try:
        start_request_ts = time.perf_counter()
        logging.info(
            "[API] /generate-brief received | client='%s' industry='%s' presales='%s' additional_docs=%d",
            client_name,
            industry,
            getattr(presales_doc, 'filename', 'unknown'),
            0 if additional_docs is None else len(additional_docs),
        )
        # Read main presales doc
        presales_content = await presales_doc.read()

        # Combine additional docs safely
        processed_additional_docs = []
        docs_iterable = additional_docs or []
        explanations_list = additional_explanations or []
        for i, doc_file in enumerate(docs_iterable):
            explanation = explanations_list[i] if i < len(explanations_list) else ""
            processed_additional_docs.append({"file": doc_file, "explanation": explanation})

        # Call the core AI logic
        core_start_ts = time.perf_counter()
        brief = await generate_intelligence_brief(
            client_name=client_name,
            industry=industry,
            ba_input=ba_input,
            presales_doc_content=presales_content,
            presales_doc_name=presales_doc.filename,
            additional_docs=processed_additional_docs
        )
        core_elapsed = time.perf_counter() - core_start_ts
        total_elapsed = time.perf_counter() - start_request_ts
        logging.info(
            "[API] /generate-brief completed | core_time=%.2fs total_time=%.2fs brief_len=%d",
            core_elapsed,
            total_elapsed,
            0 if brief is None else len(brief),
        )

        # Save/Update Project with extracted SOW text, brief, and industry
        project = db.query(Project).filter(Project.client_name == client_name).first()
        if not project:
            project = Project(
                client_name=client_name,
                industry=industry,
                sow_text="", 
                discovery_plan_json=None
            )
            db.add(project)
            db.commit()
            db.refresh(project)
            logging.info(f"[API] Created new project ID: {project.id} for client: {client_name}")

        # Persist the generated brief and industry
        project.pre_meeting_brief = brief
        project.industry = industry

        # Extract SOW text from uploaded presales document and persist to Project
        try:
            presales_text_extracted = extract_text_from_file(presales_content, presales_doc.filename)
            if isinstance(presales_text_extracted, str) and presales_text_extracted.strip():
                project.sow_text = presales_text_extracted
                logging.info("[API] Project SOW updated from presales doc | chars=%d", len(project.sow_text))
        except Exception as e:
            logging.error("[API] Failed to extract/persist SOW text: %s", e)

        db.commit()
        db.refresh(project)

        return {
            "status": "success",
            "message": f"Intelligence brief generated and project '{client_name}' saved successfully.",
            "brief": brief,
            "project_id": project.id
        }

    except Exception as e:
        logging.exception("[API] /generate-brief failed: %s", e)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

# ------------------------
# Create Project
# ------------------------
@router.post("/projects/create")
def create_project(
    client_name: str = Form(...),
    industry: str = Form(None),
    sow_text: str = Form(None),
    db: Session = Depends(get_db)
):
    existing = db.query(Project).filter(Project.client_name == client_name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Project with this client_name already exists.")
    p = Project(client_name=client_name, industry=industry or "", sow_text=sow_text or "", discovery_plan_json=None)
    db.add(p)
    db.commit()
    db.refresh(p)
    return serialize_project_detail(p, db)

# ------------------------
# List Projects (summary view)
# ------------------------
@router.get("/projects")
def get_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).all()
    return [serialize_project_summary(p, db) for p in projects]

# ------------------------
# Get Project Detail (full state for restoration)
# ------------------------
@router.get("/projects/{project_id}")
def get_project_detail(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return serialize_project_detail(project, db)

# ------------------------
# Delete Project
# ------------------------
@router.delete("/projects/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    db.delete(project)
    db.commit()
    return {"status": "success", "message": f"Project {project_id} deleted successfully."}
