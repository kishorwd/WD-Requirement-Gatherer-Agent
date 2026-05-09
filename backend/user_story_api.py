from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Dict, Any
from sqlalchemy.orm import Session
import logging

# Import database models and schemas
from backend.models import (
    Project, 
    MeetingSession, 
    Requirement, 
    UserStory,
    get_db
)
from core.story_generator import synthesize_user_stories
import json

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

from fastapi.responses import StreamingResponse
from core.story_generator import synthesize_user_stories_stream

@router.get("/stories/generate-stories-stream/{project_id}")
async def generate_user_stories_stream_endpoint(project_id: int, db: Session = Depends(get_db)):
    """
    Streaming version of story generation.
    """
    logger.info(f"SSE: Received request for project {project_id}")
    async def event_generator():
        try:
            # Send immediate heartbeat to keep connection alive
            yield f"data: {json.dumps({'status': 'progress', 'message': '📡 Establishing agent link...', 'step': 0})}\n\n"
            
            # Verify project exists
            project = db.query(Project).filter(Project.id == project_id).first()
            if not project:
                logger.error(f"SSE: Project {project_id} not found")
                yield f"data: {json.dumps({'status': 'error', 'message': 'Project not found'})}\n\n"
                return

            # Get all requirements for the project
            requirements = db.query(Requirement).join(
                MeetingSession,
                Requirement.session_id == MeetingSession.id
            ).filter(
                MeetingSession.project_id == project_id
            ).all()
            
            if not requirements:
                logger.warning(f"SSE: No requirements for project {project_id}")
                yield f"data: {json.dumps({'status': 'error', 'message': 'No requirements found'})}\n\n"
                return

            yield f"data: {json.dumps({'status': 'progress', 'message': '📂 Fetching project requirements...', 'step': 0})}\n\n"

            # Group requirements by module
            from collections import defaultdict
            module_groups = defaultdict(list)
            for req in requirements:
                m = req.module or "Uncategorized"
                module_groups[m].append(req)
            
            yield f"data: {json.dumps({'status': 'progress', 'message': f'📦 Grouped into {len(module_groups)} modules...', 'step': 1})}\n\n"

            all_stories = []
            
            # Process each module group
            for module_name, module_reqs in module_groups.items():
                yield f"data: {json.dumps({'status': 'progress', 'message': f'🚀 Starting Multi-Agent Loop for: {module_name}', 'step': 2})}\n\n"
                
                combined_module_text = "\n\n".join(
                    f"Requirement ID: {req.id}\n"
                    f"Module: {req.module or 'Uncategorized'}\n"
                    f"Text: {req.text}"
                    for req in module_reqs
                )
                
                # Stream the LangGraph workflow for this module
                async for update in synthesize_user_stories_stream(combined_module_text):
                    if update["status"] == "complete":
                        module_stories = update["stories"]
                        all_stories.extend(module_stories)
                        yield f"data: {json.dumps({'status': 'progress', 'message': f'✅ Generated {len(module_stories)} stories for {module_name}', 'step': 4})}\n\n"
                    elif update["status"] == "error":
                        yield f"data: {json.dumps({'status': 'progress', 'message': f'⚠️ Error in {module_name}: {update['message']}', 'step': 2})}\n\n"
                    else:
                        # Pass through progress updates
                        yield f"data: {json.dumps(update)}\n\n"
            
            # Finalize
            yield f"data: {json.dumps({'status': 'progress', 'message': '📊 Finalizing BRNs and persisting to database...', 'step': 5})}\n\n"

            # Re-index BRNs
            for i, story in enumerate(all_stories, 1):
                story["brn"] = f"BRN-{i:03d}"
                story["sub_brn"] = f"BRN-{i:03d}.1"
            
            # Save to DB
            try:
                db.query(UserStory).filter(UserStory.project_id == project_id).delete()
                for s in all_stories:
                    db_story = UserStory(
                        project_id=project_id,
                        brn=s["brn"],
                        sub_brn=s["sub_brn"],
                        module_name=s["module_name"],
                        sub_module_name=s["sub_module_name"],
                        description=s["description"],
                        acceptance_criteria_json=json.dumps(s["acceptance_criteria"])
                    )
                    db.add(db_story)
                db.commit()
            except Exception as db_err:
                db.rollback()
                logger.error(f"DB Error: {db_err}")

            yield f"data: {json.dumps({'status': 'complete', 'stories': all_stories})}\n\n"

        except Exception as e:
            logger.error(f"Streaming failed: {e}", exc_info=True)
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

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
        
        logger.info(f"Processing {len(requirements)} requirements across modules for story generation")
        
        # Group requirements by module to avoid overloading the LLM
        from collections import defaultdict
        module_groups = defaultdict(list)
        for req in requirements:
            m = req.module or "Uncategorized"
            module_groups[m].append(req)
        
        all_stories = []
        
        # Process each module group
        for module_name, module_reqs in module_groups.items():
            logger.info(f"Generating stories for module: {module_name} ({len(module_reqs)} requirements)")
            
            combined_module_text = "\n\n".join(
                f"Requirement ID: {req.id}\n"
                f"Module: {req.module or 'Uncategorized'}\n"
                f"Text: {req.text}"
                for req in module_reqs
            )
            
            try:
                # Generate user stories for this module
                module_stories = await synthesize_user_stories(combined_module_text)
                all_stories.extend(module_stories)
                logger.info(f"Successfully generated {len(module_stories)} stories for {module_name}")
                
                # Small delay to avoid rate limits
                import asyncio
                await asyncio.sleep(1)
            except Exception as mod_error:
                logger.error(f"Failed to generate stories for module {module_name}: {mod_error}")
                # Continue with other modules instead of failing the whole request
                continue
        
        # Re-index BRNs for the entire project
        for i, story in enumerate(all_stories, 1):
            story["brn"] = f"BRN-{i:03d}"
            story["sub_brn"] = f"BRN-{i:03d}.1"
            
        # PERSIST TO DATABASE
        try:
            # Clear old stories for this project first
            db.query(UserStory).filter(UserStory.project_id == project_id).delete()
            
            # Add new stories
            for s in all_stories:
                db_story = UserStory(
                    project_id=project_id,
                    brn=s["brn"],
                    sub_brn=s["sub_brn"],
                    module_name=s["module_name"],
                    sub_module_name=s["sub_module_name"],
                    description=s["description"],
                    acceptance_criteria_json=json.dumps(s["acceptance_criteria"])
                )
                db.add(db_story)
            
            db.commit()
            logger.info(f"Persisted {len(all_stories)} user stories to database for project {project_id}")
        except Exception as db_err:
            db.rollback()
            logger.error(f"Failed to persist user stories to database: {db_err}")
            # We still return the stories to the UI even if DB save fails
            
        logger.info(f"Total stories generated: {len(all_stories)}")
        return all_stories
        
    except HTTPException as he:
        # Re-raise HTTP exceptions
        raise he
        
    except ValueError as ve:
        error_msg = f"Story Generation Error: {str(ve)}"
        logger.error(error_msg)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_msg
        )

    except Exception as e:
        import traceback
        error_msg = f"Unexpected Server Error: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )

@router.get("/stories/project/{project_id}", response_model=List[Dict[str, Any]])
async def get_user_stories(project_id: int, db: Session = Depends(get_db)):
    """
    Fetch previously generated user stories for a project.
    """
    try:
        db_stories = db.query(UserStory).filter(UserStory.project_id == project_id).all()
        
        return [{
            "brn": s.brn,
            "sub_brn": s.sub_brn,
            "module_name": s.module_name,
            "sub_module_name": s.sub_module_name,
            "description": s.description,
            "acceptance_criteria": json.loads(s.acceptance_criteria_json) if s.acceptance_criteria_json else []
        } for s in db_stories]
        
    except Exception as e:
        logger.error(f"Error fetching stories for project {project_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch existing user stories"
        )
