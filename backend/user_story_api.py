from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import logging
import json

# Import database models and schemas
from backend.models import (
    Project, 
    MeetingSession, 
    Requirement, 
    get_db
)
from core.story_generator import synthesize_user_stories

router = APIRouter()
logger = logging.getLogger(__name__)

# CORS middleware is already added in main.py, so we don't need it here

@router.get("/stories/projects", response_model=List[Dict[str, Any]])
async def list_projects(db: Session = Depends(get_db)):
    """
    List all projects available for story generation.
    """
    try:
        projects = db.query(Project).all()
        return [{"id": p.id, "name": f"{p.client_name} (Project {p.id})"} for p in projects]
    except Exception as e:
        logger.error(f"Error listing projects: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch projects"
        )

@router.get("/stories/project/{project_id}/requirements", response_model=List[Dict[str, Any]])
async def get_project_requirements(project_id: int, db: Session = Depends(get_db)):
    """
    Get all requirements for a specific project.
    """
    try:
        requirements = db.query(Requirement).join(
            MeetingSession,
            Requirement.session_id == MeetingSession.id
        ).filter(
            MeetingSession.project_id == project_id
        ).all()
        
        return [{
            "id": r.id,
            "text": r.text,
            "module": r.module,
            "session_id": r.session_id
        } for r in requirements]
        
    except Exception as e:
        logger.error(f"Error fetching requirements: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch requirements"
        )

@router.post("/stories/generate-stories/{project_id}", response_model=List[Dict[str, Any]])
async def generate_user_stories(project_id: int, db: Session = Depends(get_db)):
    """
    Generate user stories for a given project by processing all requirements
    from related meeting sessions.
    
    Args:
        project_id: ID of the project to generate stories for
        db: Database session dependency
        
    Returns:
        List of generated user stories with BRNs and acceptance criteria
        
    Raises:
        HTTPException: If no requirements found or processing fails
    """
    try:
        logger.info(f"Generating user stories for project_id: {project_id}")
        
        # Verify project exists
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project with ID {project_id} not found"
            )
        
        # Get all requirements for the project
        requirements = db.query(Requirement).join(
            MeetingSession,
            Requirement.session_id == MeetingSession.id
        ).filter(
            MeetingSession.project_id == project_id
        ).all()
        
        if not requirements:
            logger.warning(f"No requirements found for project_id: {project_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No requirements found for project: {project.client_name}"
            )
        
        # Combine all requirement texts with their context
        combined_requirements = "\n\n".join(
            f"Requirement ID: {req.id}\n"
            f"Module: {req.module or 'Uncategorized'}\n"
            f"Text: {req.text}\n"
            f"From Session: {req.session_id}"
            for req in requirements
        )
        
        logger.info(f"Processing {len(requirements)} requirements for story generation")
        
        # Generate user stories using the AI
        stories = await synthesize_user_stories(combined_requirements)
        
        # Log generation completion
        logger.info(f"Successfully generated {len(stories)} user stories for project_id: {project_id}")
        
        return stories
        
    except HTTPException as he:
        # Re-raise HTTP exceptions
        raise he
        
    except ValueError as ve:
        logger.error(f"Error in story generation: {str(ve)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to process requirements: {str(ve)}"
        )
        
    except Exception as e:
        logger.error(f"Unexpected error in generate_user_stories: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while generating user stories"
        )
