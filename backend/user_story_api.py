from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import logging
import json
from collections import defaultdict

from backend.models import (
    Project,
    MeetingSession,
    Requirement,
    UserStory,
    ClarificationQuestion,
    get_db,
)
from core.story_generator import (
    run_story_graph,
    synthesize_user_stories_stream,
    cluster_held_batches,
    analyze_implications,
    build_conflict_context,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _serialize_story(s: UserStory) -> Dict[str, Any]:
    return {
        "brn": s.brn,
        "sub_brn": s.sub_brn,
        "module_name": s.module_name,
        "sub_module_name": s.sub_module_name,
        "description": s.description,
        "acceptance_criteria": json.loads(s.acceptance_criteria_json) if s.acceptance_criteria_json else [],
        "generation_status": s.generation_status or "converged",
        "assumption_text": s.assumption_text or "",
        "coach_feedback": s.coach_feedback or "",
    }


def _combined_module_text(module_reqs: List[Requirement]) -> str:
    return "\n\n".join(
        f"Requirement ID: {req.id}\nModule: {req.module or 'Uncategorized'}\nText: {req.text}"
        for req in module_reqs
    )


def _pick_best_assumption(stories: List[Dict[str, Any]]) -> str:
    """Return the most meaningful assumption across a batch of stories (non-empty, non-trivial)."""
    for story in stories:
        assumption = story.get("assumption", "").strip()
        if assumption:
            return assumption
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# LIST / FETCH
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/stories/projects", response_model=List[Dict[str, Any]])
async def list_projects(db: Session = Depends(get_db)):
    try:
        projects = db.query(Project).all()
        return [{"id": p.id, "name": f"{p.client_name} (Project {p.id})"} for p in projects]
    except Exception as e:
        logger.error("Error listing projects: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch projects")


@router.get("/stories/project/{project_id}/requirements", response_model=List[Dict[str, Any]])
async def get_project_requirements(project_id: int, db: Session = Depends(get_db)):
    try:
        requirements = (
            db.query(Requirement)
            .join(MeetingSession, Requirement.session_id == MeetingSession.id)
            .filter(MeetingSession.project_id == project_id)
            .all()
        )
        return [{"id": r.id, "text": r.text, "module": r.module, "session_id": r.session_id} for r in requirements]
    except Exception as e:
        logger.error("Error fetching requirements: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch requirements")


@router.get("/stories/project/{project_id}", response_model=List[Dict[str, Any]])
async def get_user_stories(project_id: int, db: Session = Depends(get_db)):
    try:
        db_stories = db.query(UserStory).filter(UserStory.project_id == project_id).all()
        return [_serialize_story(s) for s in db_stories]
    except Exception as e:
        logger.error("Error fetching stories for project %d: %s", project_id, e)
        raise HTTPException(status_code=500, detail="Failed to fetch existing user stories")


# ──────────────────────────────────────────────────────────────────────────────
# CLARIFICATIONS
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/stories/project/{project_id}/clarifications", response_model=List[Dict[str, Any]])
async def get_clarifications(project_id: int, db: Session = Depends(get_db)):
    """Return all pending clarification questions for a project."""
    try:
        questions = (
            db.query(ClarificationQuestion)
            .filter(
                ClarificationQuestion.project_id == project_id,
                ClarificationQuestion.status == "pending",
            )
            .all()
        )
        return [
            {
                "id": q.id,
                "module_name": q.module_name,
                "question_text": q.question_text,
                "context_text": q.context_text,
                "affected_brns": json.loads(q.affected_brns_json) if q.affected_brns_json else [],
                "answer_text": q.answer_text,
                "status": q.status,
            }
            for q in questions
        ]
    except Exception as e:
        logger.error("Error fetching clarifications for project %d: %s", project_id, e)
        raise HTTPException(status_code=500, detail="Failed to fetch clarifications")


class ClarificationAnswer(BaseModel):
    question_id: int
    answer_text: str


class SubmitAnswersRequest(BaseModel):
    answers: List[ClarificationAnswer]


@router.post("/stories/project/{project_id}/clarifications/answer")
async def submit_clarification_answers(
    project_id: int,
    payload: SubmitAnswersRequest,
    db: Session = Depends(get_db),
):
    """
    Accept BA answers, regenerate held + affected converged stories, return updated story list.
    One round only — stories that still fail after this are marked manual_required.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    answered_ids = {a.question_id: a.answer_text for a in payload.answers if a.answer_text.strip()}
    if not answered_ids:
        raise HTTPException(status_code=400, detail="No non-empty answers provided")

    # Build clarification context string for injection into regeneration
    qa_pairs = []
    for q_id, answer in answered_ids.items():
        q = db.query(ClarificationQuestion).filter(
            ClarificationQuestion.id == q_id,
            ClarificationQuestion.project_id == project_id,
        ).first()
        if q:
            q.answer_text = answer
            q.status = "answered"
            qa_pairs.append({"question": q.question_text, "answer": answer})
    db.commit()

    if not qa_pairs:
        raise HTTPException(status_code=404, detail="No matching clarification questions found")

    clarification_context = "\n\n".join(
        f"Q: {pair['question']}\nA: {pair['answer']}" for pair in qa_pairs
    )

    # Build conflict context
    sessions = db.query(MeetingSession).filter(MeetingSession.project_id == project_id).all()
    conflict_ctx = build_conflict_context(sessions)

    # ── Step 1: Regenerate held stories for answered questions ──
    answered_brns: List[str] = []
    for q_id, answer in answered_ids.items():
        q = db.query(ClarificationQuestion).filter(ClarificationQuestion.id == q_id).first()
        if not q:
            continue
        req_text = ""
        if q.requirements_context_json:
            try:
                req_text = json.loads(q.requirements_context_json)
            except Exception:
                req_text = q.requirements_context_json

        result = await run_story_graph(req_text, conflict_ctx, clarification_context)
        held_stories_db = (
            db.query(UserStory)
            .filter(UserStory.project_id == project_id)
            .filter(UserStory.brn.in_(json.loads(q.affected_brns_json or "[]")))
            .all()
        )
        if result["needs_clarification"]:
            # Still couldn't converge — mark as manual_required
            for s in held_stories_db:
                s.generation_status = "manual_required"
                s.coach_feedback = result["coach_feedback"]
            q.status = "resolved"
        else:
            # Replace held stories with regenerated ones
            new_stories = result["stories"]
            # Delete old held rows
            for s in held_stories_db:
                db.delete(s)
            db.flush()
            for story in new_stories:
                assumption = story.get("assumption", "").strip()
                db_story = UserStory(
                    project_id=project_id,
                    brn="",  # will be re-indexed below
                    sub_brn="",
                    module_name=story["module_name"],
                    sub_module_name=story["sub_module_name"],
                    description=story["description"],
                    acceptance_criteria_json=json.dumps(story["acceptance_criteria"]),
                    generation_status="converged",
                    assumption_text=assumption if assumption else None,
                )
                db.add(db_story)
            q.status = "resolved"
            answered_brns.extend(json.loads(q.affected_brns_json or "[]"))

    db.commit()

    # ── Step 2: Cross-story implications analysis ──
    converged_stories = (
        db.query(UserStory)
        .filter(UserStory.project_id == project_id, UserStory.generation_status == "converged")
        .all()
    )
    converged_dicts = [_serialize_story(s) for s in converged_stories]

    affected_brns = await analyze_implications(qa_pairs, converged_dicts)
    if affected_brns:
        logger.info("Implications analysis: %d converged stories need updating: %s", len(affected_brns), affected_brns)
        # Group affected stories by module and regenerate
        affected_db = [s for s in converged_stories if s.brn in affected_brns]
        module_groups: Dict[str, List[UserStory]] = defaultdict(list)
        for s in affected_db:
            module_groups[s.module_name].append(s)

        for module_name, stories_in_module in module_groups.items():
            # Re-fetch original requirements for this module
            module_reqs = (
                db.query(Requirement)
                .join(MeetingSession, Requirement.session_id == MeetingSession.id)
                .filter(MeetingSession.project_id == project_id)
                .filter(Requirement.module == module_name)
                .all()
            )
            if not module_reqs:
                continue
            combined_text = _combined_module_text(module_reqs)
            regen_result = await run_story_graph(combined_text, conflict_ctx, clarification_context)
            if not regen_result["needs_clarification"] and regen_result["stories"]:
                for s in stories_in_module:
                    db.delete(s)
                db.flush()
                for story in regen_result["stories"]:
                    assumption = story.get("assumption", "").strip()
                    db.add(UserStory(
                        project_id=project_id,
                        brn="",
                        sub_brn="",
                        module_name=story["module_name"],
                        sub_module_name=story["sub_module_name"],
                        description=story["description"],
                        acceptance_criteria_json=json.dumps(story["acceptance_criteria"]),
                        generation_status="converged",
                        assumption_text=assumption if assumption else None,
                    ))

    db.commit()

    # ── Step 3: Re-index all BRNs ──
    all_stories_db = db.query(UserStory).filter(UserStory.project_id == project_id).all()
    for i, s in enumerate(all_stories_db, 1):
        s.brn = f"BRN-{i:03d}"
        s.sub_brn = f"BRN-{i:03d}.1"
    db.commit()

    pending_count = (
        db.query(ClarificationQuestion)
        .filter(ClarificationQuestion.project_id == project_id, ClarificationQuestion.status == "pending")
        .count()
    )

    return {
        "status": "success",
        "stories": [_serialize_story(s) for s in db.query(UserStory).filter(UserStory.project_id == project_id).all()],
        "clarification_count": pending_count,
    }


# ──────────────────────────────────────────────────────────────────────────────
# GENERATION (non-streaming POST)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/stories/generate-stories/{project_id}", response_model=List[Dict[str, Any]])
async def generate_user_stories(project_id: int, db: Session = Depends(get_db)):
    """
    Generate user stories for a project.
    - Converged stories are saved with generation_status='converged'.
    - Held batches (hit review cap still REWORK) are saved with generation_status='held'
      and ClarificationQuestion records are created.
    - Returns all stories including held ones.
    """
    import asyncio

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    requirements = (
        db.query(Requirement)
        .join(MeetingSession, Requirement.session_id == MeetingSession.id)
        .filter(MeetingSession.project_id == project_id)
        .all()
    )
    if not requirements:
        raise HTTPException(status_code=404, detail=f"No requirements found for project: {project.client_name}")

    # Build conflict context from all sessions
    sessions = db.query(MeetingSession).filter(MeetingSession.project_id == project_id).all()
    conflict_ctx = build_conflict_context(sessions)
    if conflict_ctx:
        logger.info("[STORY-GEN] Conflict context built (%d chars)", len(conflict_ctx))

    # Group requirements by module
    module_groups: Dict[str, List[Requirement]] = defaultdict(list)
    for req in requirements:
        module_groups[req.module or "Uncategorized"].append(req)

    all_stories: List[Dict[str, Any]] = []
    held_batches: List[Dict[str, Any]] = []

    for module_name, module_reqs in module_groups.items():
        logger.info("[STORY-GEN] Processing module: %s (%d reqs)", module_name, len(module_reqs))
        combined_text = _combined_module_text(module_reqs)
        try:
            result = await run_story_graph(combined_text, conflict_ctx)
            if result["needs_clarification"]:
                logger.info("[STORY-GEN] Module '%s' held for clarification", module_name)
                held_batches.append({
                    "module_name": module_name,
                    "requirements_text": combined_text,
                    "coach_feedback": result["coach_feedback"],
                    "last_draft": result["stories"],
                })
                # Store held stories in DB so BA can see them
                for story in result["stories"]:
                    assumption = story.get("assumption", "").strip()
                    all_stories.append({
                        **story,
                        "generation_status": "held",
                        "assumption_text": assumption,
                        "coach_feedback": result["coach_feedback"],
                    })
            else:
                logger.info("[STORY-GEN] Module '%s' converged (%d stories)", module_name, len(result["stories"]))
                for story in result["stories"]:
                    assumption = story.get("assumption", "").strip()
                    all_stories.append({
                        **story,
                        "generation_status": "converged",
                        "assumption_text": assumption,
                        "coach_feedback": "",
                    })
        except Exception as e:
            logger.error("[STORY-GEN] Module '%s' failed: %s", module_name, e)
            continue

        await asyncio.sleep(0.5)  # small breathing room between modules

    # Assign BRNs
    for i, story in enumerate(all_stories, 1):
        story["brn"] = f"BRN-{i:03d}"
        story["sub_brn"] = f"BRN-{i:03d}.1"

    # Persist to DB — clear old stories first
    try:
        db.query(UserStory).filter(UserStory.project_id == project_id).delete()
        for s in all_stories:
            assumption = s.get("assumption_text", "") or s.get("assumption", "")
            db.add(UserStory(
                project_id=project_id,
                brn=s["brn"],
                sub_brn=s["sub_brn"],
                module_name=s["module_name"],
                sub_module_name=s["sub_module_name"],
                description=s["description"],
                acceptance_criteria_json=json.dumps(s.get("acceptance_criteria", [])),
                generation_status=s.get("generation_status", "converged"),
                assumption_text=assumption if assumption else None,
                coach_feedback=s.get("coach_feedback") or None,
            ))
        db.commit()
        logger.info("[STORY-GEN] Persisted %d stories for project %d", len(all_stories), project_id)
    except Exception as db_err:
        db.rollback()
        logger.error("[STORY-GEN] DB persist failed: %s", db_err)

    # Cluster held batches into clarification questions
    if held_batches:
        try:
            # Clear existing pending questions before creating new ones
            db.query(ClarificationQuestion).filter(
                ClarificationQuestion.project_id == project_id,
                ClarificationQuestion.status == "pending",
            ).delete()
            db.commit()

            questions = await cluster_held_batches(held_batches)
            for q in questions:
                # Collect BRNs of held stories for this question
                batch_indices = q.get("held_batch_indices", [])
                affected_brns = []
                req_context_parts = []
                for idx in batch_indices:
                    if idx < len(held_batches):
                        batch = held_batches[idx]
                        for story in batch["last_draft"]:
                            brn = story.get("brn", "")
                            if brn:
                                affected_brns.append(brn)
                        req_context_parts.append(batch["requirements_text"])

                db.add(ClarificationQuestion(
                    project_id=project_id,
                    module_name=q.get("module_name", ""),
                    question_text=q.get("question_text", ""),
                    context_text=q.get("context_text", ""),
                    affected_brns_json=json.dumps(affected_brns),
                    requirements_context_json=json.dumps("\n\n".join(req_context_parts)),
                    status="pending",
                ))
            db.commit()
            logger.info("[STORY-GEN] Created %d clarification questions", len(questions))
        except Exception as e:
            logger.error("[STORY-GEN] Clarification clustering failed: %s", e)

    return [_serialize_story(s) for s in db.query(UserStory).filter(UserStory.project_id == project_id).all()]


# ──────────────────────────────────────────────────────────────────────────────
# STREAMING GENERATION (SSE)
# ──────────────────────────────────────────────────────────────────────────────

from fastapi.responses import StreamingResponse


@router.get("/stories/generate-stories-stream/{project_id}")
async def generate_user_stories_stream_endpoint(project_id: int, db: Session = Depends(get_db)):
    """Streaming (SSE) version of story generation."""

    async def event_generator():
        yield f"data: {json.dumps({'status': 'progress', 'message': '📡 Establishing agent link...', 'step': 0})}\n\n"

        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            yield f"data: {json.dumps({'status': 'error', 'message': 'Project not found'})}\n\n"
            return

        requirements = (
            db.query(Requirement)
            .join(MeetingSession, Requirement.session_id == MeetingSession.id)
            .filter(MeetingSession.project_id == project_id)
            .all()
        )
        if not requirements:
            yield f"data: {json.dumps({'status': 'error', 'message': 'No requirements found'})}\n\n"
            return

        yield f"data: {json.dumps({'status': 'progress', 'message': '📂 Fetching project requirements...', 'step': 0})}\n\n"

        sessions = db.query(MeetingSession).filter(MeetingSession.project_id == project_id).all()
        conflict_ctx = build_conflict_context(sessions)

        module_groups: Dict[str, List[Requirement]] = defaultdict(list)
        for req in requirements:
            module_groups[req.module or "Uncategorized"].append(req)

        yield f"data: {json.dumps({'status': 'progress', 'message': f'📦 Grouped into {len(module_groups)} modules...', 'step': 1})}\n\n"

        all_stories: List[Dict[str, Any]] = []
        held_batches: List[Dict[str, Any]] = []

        for module_name, module_reqs in module_groups.items():
            yield f"data: {json.dumps({'status': 'progress', 'message': f'🚀 Starting Multi-Agent Loop for: {module_name}', 'step': 2})}\n\n"
            combined_text = _combined_module_text(module_reqs)

            async for update in synthesize_user_stories_stream(combined_text, conflict_ctx):
                if update["status"] == "complete":
                    stories = update["stories"]
                    needs_clarification = update.get("needs_clarification", False)
                    coach_feedback = update.get("coach_feedback", "")
                    if needs_clarification:
                        held_batches.append({
                            "module_name": module_name,
                            "requirements_text": combined_text,
                            "coach_feedback": coach_feedback,
                            "last_draft": stories,
                        })
                        for story in stories:
                            all_stories.append({**story, "generation_status": "held", "coach_feedback": coach_feedback})
                        yield f"data: {json.dumps({'status': 'progress', 'message': f'❓ {module_name} needs clarification — held for BA input', 'step': 3})}\n\n"
                    else:
                        for story in stories:
                            all_stories.append({**story, "generation_status": "converged", "coach_feedback": ""})
                        yield f"data: {json.dumps({'status': 'progress', 'message': f'✅ Generated {len(stories)} stories for {module_name}', 'step': 4})}\n\n"
                elif update["status"] == "error":
                    err_msg = update.get("message", "")
                    yield f"data: {json.dumps({'status': 'progress', 'message': f'⚠️ Error in {module_name}: {err_msg}', 'step': 2})}\n\n"
                else:
                    yield f"data: {json.dumps(update)}\n\n"

        yield f"data: {json.dumps({'status': 'progress', 'message': '📊 Finalizing BRNs and persisting...', 'step': 5})}\n\n"

        for i, story in enumerate(all_stories, 1):
            story["brn"] = f"BRN-{i:03d}"
            story["sub_brn"] = f"BRN-{i:03d}.1"

        try:
            db.query(UserStory).filter(UserStory.project_id == project_id).delete()
            for s in all_stories:
                assumption = s.get("assumption", "").strip()
                db.add(UserStory(
                    project_id=project_id,
                    brn=s["brn"],
                    sub_brn=s["sub_brn"],
                    module_name=s["module_name"],
                    sub_module_name=s["sub_module_name"],
                    description=s["description"],
                    acceptance_criteria_json=json.dumps(s.get("acceptance_criteria", [])),
                    generation_status=s.get("generation_status", "converged"),
                    assumption_text=assumption if assumption else None,
                    coach_feedback=s.get("coach_feedback") or None,
                ))
            db.commit()
        except Exception as db_err:
            db.rollback()
            logger.error("SSE DB persist failed: %s", db_err)

        # Cluster held batches
        clarification_count = 0
        if held_batches:
            try:
                db.query(ClarificationQuestion).filter(
                    ClarificationQuestion.project_id == project_id,
                    ClarificationQuestion.status == "pending",
                ).delete()
                db.commit()

                questions = await cluster_held_batches(held_batches)
                clarification_count = len(questions)
                for q in questions:
                    batch_indices = q.get("held_batch_indices", [])
                    affected_brns = []
                    req_context_parts = []
                    for idx in batch_indices:
                        if idx < len(held_batches):
                            batch = held_batches[idx]
                            for story in batch["last_draft"]:
                                brn = story.get("brn", "")
                                if brn:
                                    affected_brns.append(brn)
                            req_context_parts.append(batch["requirements_text"])
                    db.add(ClarificationQuestion(
                        project_id=project_id,
                        module_name=q.get("module_name", ""),
                        question_text=q.get("question_text", ""),
                        context_text=q.get("context_text", ""),
                        affected_brns_json=json.dumps(affected_brns),
                        requirements_context_json=json.dumps("\n\n".join(req_context_parts)),
                        status="pending",
                    ))
                db.commit()
            except Exception as e:
                logger.error("SSE clarification clustering failed: %s", e)

        yield f"data: {json.dumps({'status': 'complete', 'stories': all_stories, 'clarification_count': clarification_count})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
