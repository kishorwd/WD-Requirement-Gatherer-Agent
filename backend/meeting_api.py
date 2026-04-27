import json
from typing import Generator

import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session

# Removed: serialize_project helper function
from backend.models import SessionLocal, Project, MeetingSession, Requirement
from core.post_meeting_analyzer import analyze_transcript_text, extract_speakers_llm, read_transcript_bytes
from core.scope_gap_analyzer import analyze_requirement_scope

router = APIRouter()

# ------------------------
# Dependency: Get DB session
# ------------------------
def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------------
# Helper: serialize model instances (KEEP only meeting-related serializers)
# ------------------------
def serialize_session(s: MeetingSession) -> dict:
    return {
        "id": s.id,
        "project_id": s.project_id,
        "session_number": s.session_number,
        "mom": s.mom,
        "analysis_json": json.loads(s.analysis_json) if s.analysis_json else None,
    }

def serialize_requirement(r: Requirement) -> dict:
    return {
        "id": r.id,
        "session_id": r.session_id,
        "text": r.text,
        "module": r.module,
        "status": r.status,
        "scope_status": r.scope_status,
        "scope_justification": r.scope_justification,
    }

# ------------------------
# Endpoint: Upload Discovery Plan (CSV / XLSX) (KEEP)
# ------------------------
@router.post("/project/{project_id}/upload-plan")
async def upload_discovery_plan(project_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        # Read into DataFrame and store as JSON records
        if file.filename.endswith(".csv"):
            df = pd.read_csv(file.file)
        else:
            df = pd.read_excel(file.file)
        project.discovery_plan_json = df.to_json(orient="records")
        db.commit()
        db.refresh(project)
        return {"status": "success", "message": "Discovery Plan uploaded"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading discovery plan: {e}")

# ------------------------
# Endpoint: Analyze Transcript (KEEP)
# ------------------------
@router.post("/analyze-transcript")
async def analyze_transcript_endpoint(
    project_id: int = Form(...),
    session_number: int = Form(...),
    speaker_tags_json: str = Form(...),  # JSON string: {"John": "Client"}
    transcript_file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # 1. Read transcript content
    try:
        transcript_text = read_transcript_bytes(transcript_file.filename, await transcript_file.read())
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading transcript file: {e}")

    # 2. Load project
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Parse speaker tags
    try:
        speaker_tags = json.loads(speaker_tags_json) if speaker_tags_json else {}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"speaker_tags_json is not valid JSON: {e}")

    # Parse discovery plan if present
    discovery_plan = {}
    if project.discovery_plan_json:
        try:
            discovery_plan = json.loads(project.discovery_plan_json)
        except Exception:
            discovery_plan = {}

    # 3. Call the AI analyzer 
    analysis_result = await analyze_transcript_text(
        transcript_text,
        speaker_tags,
        discovery_plan,
        project.sow_text or ""
    )

    # Ensure analysis_result contains mom & lists. Normalize provisional_user_stories format.
    # If provisional_user_stories are strings, convert to dicts with text+module keys.
    provisional = analysis_result.get("provisional_user_stories", [])
    normalized_provisional = []
    for item in provisional:
        if isinstance(item, dict):
            normalized_provisional.append(item)
        else:
            normalized_provisional.append({"text": str(item), "module": "General"})
    analysis_result["provisional_user_stories"] = normalized_provisional

    # 4. Save session into DB
    new_session = MeetingSession(
        project_id=project_id,
        session_number=session_number,
        mom=analysis_result.get("mom", ""),
        analysis_json=json.dumps(analysis_result),
        transcript_text=transcript_text  # Save the transcript text
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    # 5. For each requirement: run scope analysis, save it, and update response payload
    requirements_added = 0
    for idx, req_obj in enumerate(analysis_result["provisional_user_stories"]):
        req_text = req_obj.get("text", "")
        req_module = req_obj.get("module", "General")
        scope_result = await analyze_requirement_scope(project.sow_text or "", req_text)
        scope_status = scope_result.get("scope_status", "Needs Clarification")
        justification = scope_result.get("justification", "")

        new_req = Requirement(
            session_id=new_session.id,
            text=req_text,
            module=req_module,
            status="Provisional",
            scope_status=scope_status,
            scope_justification=justification
        )
        db.add(new_req)
        requirements_added += 1

        # Reflect scope results back into analysis_result so frontend renders them
        analysis_result["provisional_user_stories"][idx]["status"] = req_obj.get("status", "Provisional")
        analysis_result["provisional_user_stories"][idx]["scope_status"] = scope_status
        analysis_result["provisional_user_stories"][idx]["scope_justification"] = justification

    db.commit()

    return {
        "status": "success",
        "session_id": new_session.id,
        "requirements_added": requirements_added,
        "analysis_result": analysis_result
    }

# ------------------------
# Endpoint: Get Sessions for a Project (KEEP)
# ------------------------
@router.get("/sessions")
def get_project_sessions(project_id: int, db: Session = Depends(get_db)):
    try:
        # Check if project exists
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=404,
                detail=f"Project with ID {project_id} not found"
            )
            
        # Query sessions
        sessions = db.query(MeetingSession).filter(
            MeetingSession.project_id == project_id
        ).order_by(MeetingSession.session_number).all()
        
        # Log the number of sessions found for debugging
        print(f"Found {len(sessions)} sessions for project {project_id}")
        
        # Return serialized sessions
        return [serialize_session(s) for s in sessions]
        
    except Exception as e:
        # Log the full error for debugging
        print(f"Error in get_project_sessions: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Return a more user-friendly error message
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving sessions for project {project_id}: {str(e)}"
        )

# ------------------------
# Endpoint: Get Requirements for a Session (KEEP)
# ------------------------
@router.get("/session/{session_id}/requirements")
def get_session_requirements(session_id: int, db: Session = Depends(get_db)):
    requirements = db.query(Requirement).filter(Requirement.session_id == session_id).all()
    return [serialize_requirement(r) for r in requirements]


# ------------------------
# New Endpoint: Extract Speakers via LLM
# ------------------------
@router.post("/extract-speakers")
async def extract_speakers_endpoint(transcript_file: UploadFile = File(...)):
    """
    Accept a transcript file and return speaker name candidates using LLM.
    Response: { "speakers": ["Name1", "Name2", ...] }
    """
    try:
        transcript_text = read_transcript_bytes(transcript_file.filename, await transcript_file.read())
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading transcript file: {e}")

    speakers = await extract_speakers_llm(transcript_text)
    return {"speakers": speakers}
