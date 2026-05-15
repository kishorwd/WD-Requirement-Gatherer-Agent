import json
from typing import List, Dict, Any, Optional
import logging
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

logger = logging.getLogger(__name__)
MAX_REVIEW_CYCLES = 2  # must match graph_workflows.py


def load_prompt(filename: str) -> str:
    path = os.path.join(os.path.dirname(__file__), "..", "sub_agents", filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _init_client() -> AsyncOpenAI:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY environment variable not set")
    return AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        timeout=180.0,
    )


def _build_requirements_block(requirements_text: str, conflict_context: str = "", clarification_context: str = "") -> str:
    """Prepend conflict resolutions and/or clarification context to the requirements block."""
    sections = []
    if conflict_context:
        sections.append(f"CONFLICT RESOLUTIONS — when requirements touch these topics, use ONLY the LATEST statement:\n{conflict_context}")
    if clarification_context:
        sections.append(f"CLARIFICATION FROM BA — apply this to all affected stories:\n{clarification_context}")
    sections.append(f"Raw Requirements:\n{requirements_text}")
    return "\n\n---\n\n".join(sections)


async def run_story_graph(
    requirements_text: str,
    conflict_context: str = "",
    clarification_context: str = "",
) -> Dict[str, Any]:
    """
    Run the LangGraph story review loop for a single module batch.

    Returns:
        {
            "stories": [...],           # validated story dicts (may be last draft even if held)
            "review_status": str,       # final PASS or REWORK
            "review_cycle": int,        # how many cycles ran
            "coach_feedback": str,      # last coach feedback
            "needs_clarification": bool # True when capped with REWORK
        }
    """
    from .graph_workflows import story_review_graph

    effective_text = _build_requirements_block(requirements_text, conflict_context, clarification_context)

    initial_state = {
        "requirements_text": effective_text,
        "draft_stories": "",
        "validated_stories": [],
        "review_status": "PENDING",
        "review_feedback": "",
        "review_cycle": 0,
    }

    try:
        final_state = await story_review_graph.ainvoke(initial_state)
        review_status = final_state.get("review_status", "PASS")
        review_cycle = final_state.get("review_cycle", 1)
        needs_clarification = (review_status == "REWORK" and review_cycle >= MAX_REVIEW_CYCLES)

        return {
            "stories": final_state.get("validated_stories", []),
            "review_status": review_status,
            "review_cycle": review_cycle,
            "coach_feedback": final_state.get("review_feedback", ""),
            "needs_clarification": needs_clarification,
        }
    except Exception as e:
        logger.error("run_story_graph failed: %s", e)
        return {
            "stories": [],
            "review_status": "PASS",
            "review_cycle": 1,
            "coach_feedback": "",
            "needs_clarification": False,
        }


async def cluster_held_batches(held_batches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Call the clusterer LLM to group held batches into focused BA questions.

    Each held batch: {module_name, requirements_text, coach_feedback, last_draft}
    Returns list of question dicts from the clusterer prompt output.
    """
    if not held_batches:
        return []

    from .graph_workflows import _init_llm
    llm = _init_llm(use_flash=False)
    if not llm:
        # Fallback: one question per module
        return [
            {
                "module_name": b["module_name"],
                "question_text": f"The AI could not generate approved stories for {b['module_name']}. "
                                 f"Please clarify: {b['coach_feedback'][:200]}",
                "context_text": f"Agile Coach feedback after {MAX_REVIEW_CYCLES} cycles: {b['coach_feedback'][:300]}",
                "held_batch_indices": [i],
            }
            for i, b in enumerate(held_batches)
        ]

    prompt_template = load_prompt("story_clarification_clusterer.md")
    held_json = json.dumps([
        {
            "index": i,
            "module_name": b["module_name"],
            "requirements_text": b["requirements_text"][:500],
            "coach_feedback": b["coach_feedback"],
            "last_draft_count": len(b.get("last_draft", [])),
        }
        for i, b in enumerate(held_batches)
    ], indent=2)
    prompt = prompt_template.format(held_batches_json=held_json)

    try:
        msg = await llm.ainvoke(prompt)
        content = getattr(msg, "content", "").strip()
        from .graph_workflows import _parse_json
        parsed = _parse_json(content)
        if isinstance(parsed, dict):
            return parsed.get("questions", [])
    except Exception as e:
        logger.error("cluster_held_batches failed: %s", e)

    # Fallback
    return [
        {
            "module_name": b["module_name"],
            "question_text": f"Please clarify requirements for {b['module_name']}: {b['coach_feedback'][:200]}",
            "context_text": b["coach_feedback"][:300],
            "held_batch_indices": [i],
        }
        for i, b in enumerate(held_batches)
    ]


async def analyze_implications(
    clarification_qa: List[Dict[str, str]],
    converged_stories: List[Dict[str, Any]],
) -> List[str]:
    """
    Identify BRNs of converged stories that might need updating after BA clarifications.
    Returns list of affected BRN strings.
    """
    if not clarification_qa or not converged_stories:
        return []

    from .graph_workflows import _init_llm, _parse_json
    llm = _init_llm(use_flash=False)
    if not llm:
        return []

    qa_block = "\n".join(
        f"Q: {item['question']}\nA: {item['answer']}" for item in clarification_qa
    )
    stories_block = "\n".join(
        f"{s.get('brn','?')} | {s.get('module_name','?')} | {s.get('description','')[:120]}"
        for s in converged_stories
    )

    prompt_template = load_prompt("story_implications_analyzer.md")
    prompt = prompt_template.format(
        clarification_qa_block=qa_block,
        stories_summary_block=stories_block,
    )

    try:
        msg = await llm.ainvoke(prompt)
        content = getattr(msg, "content", "").strip()
        parsed = _parse_json(content)
        if isinstance(parsed, dict):
            return parsed.get("affected_brns", [])
    except Exception as e:
        logger.error("analyze_implications failed: %s", e)

    return []


def build_conflict_context(sessions) -> str:
    """
    Build a conflict resolution summary from all MeetingSession records.
    Uses ALL sessions (sorted by session_number); latest statement wins per topic.
    """
    all_conflicts = []

    sorted_sessions = sorted(sessions, key=lambda s: s.session_number or 0)
    for session in sorted_sessions:
        if not session.analysis_json:
            continue
        try:
            analysis = json.loads(session.analysis_json)
            conflicts = analysis.get("conflicting_topics", [])
            for conflict in conflicts:
                all_conflicts.append({**conflict, "session_number": session.session_number})
        except Exception:
            continue

    if not all_conflicts:
        return ""

    lines = []
    for conflict in all_conflicts:
        topic = conflict.get("topic", "")
        prior = conflict.get("prior_statement", "")
        prior_mtg = conflict.get("prior_meeting", "earlier session")
        current = conflict.get("current_statement", "")
        current_mtg = conflict.get("current_meeting", f"Session {conflict.get('session_number', '?')}")
        lines.append(f"- {topic}: earlier ({prior_mtg}) said \"{prior}\"; latest ({current_mtg}) says \"{current}\" — USE LATEST")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Legacy streaming helper (called by SSE endpoint in user_story_api.py)
# ---------------------------------------------------------------------------

async def synthesize_user_stories_stream(raw_requirements_text: str, conflict_context: str = ""):
    """
    Streaming version. Yields progress dicts. Final yield: complete event with stories.
    Now returns converged/held split via the 'complete' event.
    """
    if not raw_requirements_text or not raw_requirements_text.strip():
        yield {"status": "error", "message": "No requirements provided"}
        return

    try:
        from .graph_workflows import story_review_graph

        effective_text = _build_requirements_block(raw_requirements_text, conflict_context)
        initial_state = {
            "requirements_text": effective_text,
            "draft_stories": "",
            "validated_stories": [],
            "review_status": "PENDING",
            "review_feedback": "",
            "review_cycle": 0,
        }

        async for event in story_review_graph.astream(initial_state, stream_mode="updates"):
            for node_name, output in event.items():
                if node_name == "generate":
                    cycle = output.get("review_cycle", 1)
                    if cycle == 1:
                        yield {"status": "progress", "message": "🤖 Story Agent is drafting stories...", "step": 2}
                    else:
                        yield {"status": "progress", "message": f"🔄 Reworking stories based on feedback (Cycle {cycle-1})...", "step": 2}
                elif node_name == "review":
                    status = output.get("review_status")
                    feedback = output.get("review_feedback", "")
                    if status == "REWORK":
                        yield {"status": "progress", "message": f"🔍 Agile Coach found issues: {feedback[:100]}...", "step": 3}
                    else:
                        yield {"status": "progress", "message": "✅ Agile Coach approved the stories!", "step": 4}

        final_state = await story_review_graph.ainvoke(initial_state)
        review_status = final_state.get("review_status", "PASS")
        review_cycle = final_state.get("review_cycle", 1)
        needs_clarification = (review_status == "REWORK" and review_cycle >= MAX_REVIEW_CYCLES)

        yield {
            "status": "complete",
            "stories": final_state.get("validated_stories", []),
            "needs_clarification": needs_clarification,
            "coach_feedback": final_state.get("review_feedback", ""),
        }

    except Exception as e:
        logger.error("Streaming story generation failed: %s", e)
        yield {"status": "error", "message": str(e)}


async def synthesize_user_stories(raw_requirements_text: str) -> List[Dict[str, Any]]:
    """Non-streaming single-shot fallback (kept for compatibility)."""
    if not raw_requirements_text or not raw_requirements_text.strip():
        return []

    result = await run_story_graph(raw_requirements_text)
    if result["stories"]:
        return result["stories"]

    # Fallback: single-shot via OpenAI client
    client = _init_client()
    model_name = os.getenv("LLM_MODEL_PRO", "deepseek-v4-pro")
    try:
        max_tokens = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "4096"))
    except Exception:
        max_tokens = 4096

    prompt_template = load_prompt("story_generator.md")
    prompt = prompt_template.format(requirements_text=f"Raw Requirements:\n{raw_requirements_text}")

    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a professional business analyst that outputs only valid JSON arrays."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
        )
        response_text = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("DeepSeek API call failed: %s", e)
        raise ValueError(f"AI generation failed: {e}")

    if not response_text:
        return []

    try:
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        json_start = response_text.find("[")
        json_end = response_text.rfind("]") + 1
        if json_start == -1 or json_end == 0:
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1

        json_str = response_text[json_start:json_end]
        data = json.loads(json_str)
        stories = data if isinstance(data, list) else [data]
    except Exception as e:
        logger.error("JSON parsing failed: %s", e)
        return []

    validated = []
    for story in stories:
        if not isinstance(story, dict):
            continue
        desc = story.get("description", story.get("userStory", ""))
        if not desc:
            continue
        validated.append({
            "module_name": str(story.get("module_name", "Uncategorized")).strip(),
            "sub_module_name": str(story.get("sub_module_name", "General")).strip(),
            "description": str(desc).strip(),
            "acceptance_criteria": [
                str(c).strip()
                for c in story.get("acceptance_criteria", story.get("acceptanceCriteria", []))
                if str(c).strip()
            ],
            "assumption": str(story.get("assumption", "")).strip(),
        })

    return validated
