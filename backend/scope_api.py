from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import json
import logging

from .models import Project, MeetingSession, Requirement, get_db
from core.multi_session_scope_analyzer import analyze_project_scope, consolidate_requirements

router = APIRouter(tags=["Scope Analysis"])

@router.post("/projects/{project_id}/analyze-scope", status_code=status.HTTP_200_OK)
async def analyze_project_scope_endpoint(project_id: int, db: Session = Depends(get_db)):
    """
    Analyze scope by processing raw transcripts from all sessions against the SOW
    """
    try:
        # Get project with SOW
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Get all sessions with transcripts for this project
        sessions = db.query(MeetingSession).filter(
            MeetingSession.project_id == project_id,
            MeetingSession.transcript_text.isnot(None)
        ).all()
        
        if not sessions:
            return {
                "status": "success",
                "message": "No sessions with transcripts found for analysis",
                "project_id": project_id,
                "requirements_analyzed": 0,
                "results": []
            }
        
        # Prepare session data with transcripts
        session_transcripts = []
        for session in sessions:
            if session.transcript_text:
                session_transcripts.append({
                    'session_id': session.id,
                    'transcript': session.transcript_text,
                    'session_number': session.session_number or 0
                })
        
        # Get SOW text
        sow_text = project.sow_text or ""
        
        # Analyze transcripts against SOW to extract and analyze requirements
        analyzed_requirements = analyze_project_scope(sow_text, session_transcripts)
        
        # Consolidate duplicate requirements
        consolidated_results = consolidate_requirements(analyzed_requirements)
        
        return {
            "status": "success",
            "message": "Scope analysis completed",
            "project_id": project_id,
            "sessions_analyzed": len(sessions),
            "requirements_identified": len(consolidated_results),
            "results": consolidated_results
        }
        
    except Exception as e:
        logging.error(f"Error in analyze_project_scope: {str(e)}")
        db.rollback()
        logging.exception("Error in analyze_project_scope_endpoint")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error analyzing project scope: {str(e)}"
        )

@router.get("/projects/{project_id}/requirements")
async def get_project_requirements(
    project_id: int, 
    module: Optional[str] = None,
    scope_status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get all requirements across all sessions for a project with scope analysis
    """
    try:
        query = db.query(Requirement).join(
            MeetingSession, 
            Requirement.session_id == MeetingSession.id
        ).filter(
            MeetingSession.project_id == project_id
        )
        
        # Apply filters if provided
        if module:
            query = query.filter(Requirement.module == module)
        if scope_status:
            query = query.filter(Requirement.scope_status == scope_status)
        
        requirements = query.all()
        
        # Group by requirement text and module to consolidate
        requirements_by_text = {}
        for req in requirements:
            key = (req.text.strip().lower(), req.module.strip().lower() if req.module else "")
            if key not in requirements_by_text:
                requirements_by_text[key] = {
                    "id": req.id,
                    "text": req.text,
                    "module": req.module,
                    "status": req.status,
                    "scope_status": req.scope_status,
                    "scope_justification": req.scope_justification,
                    "session_ids": [],
                    "occurrences": 0
                }
            requirements_by_text[key]["session_ids"].append(req.session_id)
            requirements_by_text[key]["occurrences"] += 1
        
        # Convert to list and add session count
        result = list(requirements_by_text.values())
        
        return {
            "status": "success",
            "count": len(result),
            "project_id": project_id,
            "requirements": result
        }
        
    except Exception as e:
        logging.exception("Error in get_project_requirements")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching requirements: {str(e)}"
        )
