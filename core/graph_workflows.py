"""
LangGraph Review-Loop Workflows
================================
This module defines three Actor-Critic feedback loops using LangGraph:

1. Post-Meeting MoM Loop     — generates MoM → reviews → optional rework
2. Story Generation Loop     — generates stories → reviews → optional rework
3. Scope Analysis Loop       — classifies scope → reviews → optional rework

Each graph follows the same pattern:
  GENERATE  →  REVIEW  →  (PASS → END  |  REWORK → GENERATE)
                              ↑ max 2 rework cycles to avoid runaway costs
"""

import os
import json
import logging
from typing import TypedDict, Any, Dict, List, Optional

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────
MAX_REVIEW_CYCLES = 2  # at most 2 rework rounds per artifact

def _load_prompt(filename: str) -> str:
    path = os.path.join(os.path.dirname(__file__), "..", "sub_agents", filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _init_llm(use_flash: bool = False) -> Optional[ChatOpenAI]:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return None
    model = os.getenv("LLM_MODEL_FLASH" if use_flash else "LLM_MODEL_PRO",
                       "deepseek-v4-flash" if use_flash else "deepseek-v4-pro")
    return ChatOpenAI(
        model=model, api_key=api_key,
        base_url="https://api.deepseek.com", temperature=0.0
    )


def _parse_json(raw: str) -> Any:
    """Robust JSON extraction from LLM output."""
    raw = raw.strip()
    # Try direct parse
    try:
        return json.loads(raw)
    except Exception:
        pass
    # Strip code fences
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
    if raw.endswith("```"):
        raw = raw.rsplit("\n", 1)[0]
    raw = raw.strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    # Find inner JSON
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end+1])
        except Exception:
            pass
    return None


# ╔══════════════════════════════════════════════════════════════╗
# ║  1.  POST-MEETING MoM REVIEW LOOP                          ║
# ╚══════════════════════════════════════════════════════════════╝

class MomState(TypedDict):
    # --- inputs (set once, never mutated by nodes) ---
    transcript: str
    speaker_tags_block: str
    discovery_block: str
    sow_block: str
    # --- mutable state ---
    draft_mom: str           # latest MoM HTML
    review_status: str       # "PENDING" | "PASS" | "REWORK"
    review_feedback: str     # feedback text from reviewer
    review_cycle: int        # how many rework rounds so far


async def _generate_mom(state: MomState) -> dict:
    """Actor node — generate or regenerate the MoM."""
    llm = _init_llm()
    if not llm:
        return {"draft_mom": "<p>LLM unavailable</p>", "review_status": "PASS"}

    cycle = state.get("review_cycle", 0)

    if cycle == 0:
        # First attempt — use the standard prompt
        prompt_template = _load_prompt("mom_generator.md")
        prompt = prompt_template.format(
            transcript_block=state["transcript"],
            speaker_tags_block=state["speaker_tags_block"],
            discovery_block=state["discovery_block"],
            sow_block=state["sow_block"],
        )
    else:
        # Rework — include the previous draft + reviewer feedback
        prompt = (
            f"You previously generated this MoM:\n\n{state['draft_mom']}\n\n"
            f"The reviewer gave this feedback:\n{state['review_feedback']}\n\n"
            f"Please regenerate the MoM incorporating this feedback. "
            f"Output ONLY valid HTML starting with <div class=\"mom-report\">.\n\n"
            f"Original Transcript:\n{state['transcript']}\n"
            f"Speaker Tags: {state['speaker_tags_block']}\n"
        )

    try:
        msg = await llm.ainvoke(prompt)
        content = getattr(msg, "content", "").strip()
        logger.info("[GRAPH-MOM] Generated MoM | cycle=%d length=%d", cycle, len(content))
        return {"draft_mom": content, "review_cycle": cycle + 1}
    except Exception as e:
        logger.error("[GRAPH-MOM] Generation failed: %s", e)
        return {"draft_mom": "<p>Generation failed</p>", "review_status": "PASS"}


async def _review_mom(state: MomState) -> dict:
    """Critic node — review the MoM draft."""
    llm = _init_llm()
    if not llm:
        return {"review_status": "PASS", "review_feedback": ""}

    prompt_template = _load_prompt("mom_reviewer.md")
    prompt = prompt_template.format(
        transcript_block=state["transcript"],
        draft_mom=state["draft_mom"],
    )

    try:
        msg = await llm.ainvoke(prompt)
        content = getattr(msg, "content", "").strip()
        parsed = _parse_json(content)

        if isinstance(parsed, dict):
            status = parsed.get("status", "PASS").upper()
            feedback = parsed.get("feedback", "")
            logger.info("[GRAPH-MOM] Review result: %s | cycle=%d", status, state.get("review_cycle", 0))
            return {"review_status": status, "review_feedback": feedback}
    except Exception as e:
        logger.error("[GRAPH-MOM] Review failed: %s", e)

    # If review itself fails, accept the current draft
    return {"review_status": "PASS", "review_feedback": ""}


def _mom_should_continue(state: MomState) -> str:
    """Conditional edge — decide whether to rework or finish."""
    if state.get("review_status") == "REWORK" and state.get("review_cycle", 0) < MAX_REVIEW_CYCLES:
        return "rework"
    return "done"


def build_mom_review_graph() -> StateGraph:
    """Build and compile the MoM review loop graph."""
    graph = StateGraph(MomState)

    graph.add_node("generate", _generate_mom)
    graph.add_node("review", _review_mom)

    graph.set_entry_point("generate")
    graph.add_edge("generate", "review")
    graph.add_conditional_edges("review", _mom_should_continue, {
        "rework": "generate",
        "done": END,
    })

    return graph.compile()


# ╔══════════════════════════════════════════════════════════════╗
# ║  2.  USER STORY REVIEW LOOP                                ║
# ╚══════════════════════════════════════════════════════════════╝

class StoryState(TypedDict):
    requirements_text: str
    draft_stories: str       # JSON string of drafted stories
    validated_stories: list   # parsed & validated list of dicts
    review_status: str
    review_feedback: str
    review_cycle: int


async def _generate_stories(state: StoryState) -> dict:
    """Actor node — generate or regenerate user stories."""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return {"draft_stories": "[]", "validated_stories": [], "review_status": "PASS"}

    llm = _init_llm()
    if not llm:
        return {"draft_stories": "[]", "validated_stories": [], "review_status": "PASS"}

    cycle = state.get("review_cycle", 0)

    if cycle == 0:
        prompt_template = _load_prompt("story_generator.md")
        prompt = prompt_template.format(requirements_text=state["requirements_text"])
    else:
        prompt = (
            f"You previously generated these user stories:\n{state['draft_stories']}\n\n"
            f"The Agile Coach reviewer gave this feedback:\n{state['review_feedback']}\n\n"
            f"Please regenerate the stories incorporating this feedback.\n"
            f"Return ONLY valid JSON array.\n\n"
            f"Original Requirements:\n{state['requirements_text']}\n"
        )

    try:
        msg = await llm.ainvoke(prompt)
        content = getattr(msg, "content", "").strip()
        logger.info("[GRAPH-STORY] Generated stories | cycle=%d length=%d", cycle, len(content))

        # Parse the stories into validated format
        response_text = content
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        json_start = response_text.find("[")
        json_end = response_text.rfind("]") + 1
        if json_start == -1 or json_end == 0:
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1

        if json_start != -1 and json_end > 0:
            json_str = response_text[json_start:json_end]
            data = json.loads(json_str)
            stories = data if isinstance(data, list) else [data]
        else:
            stories = []

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
                ]
            })

        return {
            "draft_stories": json.dumps(validated, indent=2),
            "validated_stories": validated,
            "review_cycle": cycle + 1,
        }
    except Exception as e:
        logger.error("[GRAPH-STORY] Generation failed: %s", e)
        return {"draft_stories": "[]", "validated_stories": [], "review_status": "PASS"}


async def _review_stories(state: StoryState) -> dict:
    """Critic node — Agile Coach reviews the stories."""
    llm = _init_llm()
    if not llm:
        return {"review_status": "PASS", "review_feedback": ""}

    prompt_template = _load_prompt("story_reviewer.md")
    prompt = prompt_template.format(draft_stories=state["draft_stories"])

    try:
        msg = await llm.ainvoke(prompt)
        content = getattr(msg, "content", "").strip()
        parsed = _parse_json(content)

        if isinstance(parsed, dict):
            status = parsed.get("status", "PASS").upper()
            feedback = parsed.get("feedback", "")
            logger.info("[GRAPH-STORY] Review result: %s | cycle=%d", status, state.get("review_cycle", 0))
            return {"review_status": status, "review_feedback": feedback}
    except Exception as e:
        logger.error("[GRAPH-STORY] Review failed: %s", e)

    return {"review_status": "PASS", "review_feedback": ""}


def _story_should_continue(state: StoryState) -> str:
    if state.get("review_status") == "REWORK" and state.get("review_cycle", 0) < MAX_REVIEW_CYCLES:
        return "rework"
    return "done"


def build_story_review_graph() -> StateGraph:
    """Build and compile the Story review loop graph."""
    graph = StateGraph(StoryState)

    graph.add_node("generate", _generate_stories)
    graph.add_node("review", _review_stories)

    graph.set_entry_point("generate")
    graph.add_edge("generate", "review")
    graph.add_conditional_edges("review", _story_should_continue, {
        "rework": "generate",
        "done": END,
    })

    return graph.compile()


# ╔══════════════════════════════════════════════════════════════╗
# ║  3.  SCOPE ANALYSIS REVIEW LOOP                            ║
# ╚══════════════════════════════════════════════════════════════╝

class ScopeState(TypedDict):
    formatted_sow: str
    requirement_text: str
    draft_scope: str         # JSON string of scope classification
    scope_result: dict       # parsed scope result
    review_status: str
    review_feedback: str
    review_cycle: int


async def _generate_scope(state: ScopeState) -> dict:
    """Actor node — classify scope of a requirement."""
    llm = _init_llm()
    if not llm:
        return {
            "draft_scope": json.dumps({"scope_status": "Needs Clarification", "justification": "LLM unavailable"}),
            "scope_result": {"scope_status": "Needs Clarification", "justification": "LLM unavailable"},
            "review_status": "PASS",
        }

    cycle = state.get("review_cycle", 0)

    if cycle == 0:
        prompt_template = _load_prompt("requirement_scope_analyzer.md")
        prompt = prompt_template.format(
            formatted_sow=state["formatted_sow"],
            requirement_text=state["requirement_text"],
        )
    else:
        prompt = (
            f"You previously classified this requirement's scope as:\n{state['draft_scope']}\n\n"
            f"The compliance reviewer gave this feedback:\n{state['review_feedback']}\n\n"
            f"Please re-classify the scope based on this feedback.\n\n"
            f"SOW:\n{state['formatted_sow']}\n\n"
            f"Requirement:\n{state['requirement_text']}\n\n"
            f"Respond STRICTLY with JSON only:\n"
            f'{{"scope_status": "In Scope | Out of Scope | Needs Clarification", '
            f'"justification": "short reason", "sow_citation": "quote or empty"}}'
        )

    try:
        msg = await llm.ainvoke(prompt)
        content = getattr(msg, "content", "").strip()
        parsed = _parse_json(content)

        if isinstance(parsed, dict):
            status = str(parsed.get("scope_status", "")).strip()
            just = str(parsed.get("justification", "")).strip()
            cite = str(parsed.get("sow_citation", "")).strip()

            # Normalize
            s = status.lower()
            if "in" in s and "scope" in s:
                status = "In Scope"
            elif "out" in s and "scope" in s:
                status = "Out of Scope"
            else:
                status = "Needs Clarification"

            result = {"scope_status": status, "justification": just if just else cite}
            draft = json.dumps({"scope_status": status, "justification": just, "sow_citation": cite})

            logger.info("[GRAPH-SCOPE] Classified: %s | cycle=%d", status, cycle)
            return {"draft_scope": draft, "scope_result": result, "review_cycle": cycle + 1}

    except Exception as e:
        logger.error("[GRAPH-SCOPE] Classification failed: %s", e)

    fallback = {"scope_status": "Needs Clarification", "justification": "Classification failed"}
    return {"draft_scope": json.dumps(fallback), "scope_result": fallback, "review_status": "PASS"}


async def _review_scope(state: ScopeState) -> dict:
    """Critic node — compliance reviewer checks the scope classification."""
    llm = _init_llm()
    if not llm:
        return {"review_status": "PASS", "review_feedback": ""}

    prompt_template = _load_prompt("scope_reviewer.md")
    prompt = prompt_template.format(
        formatted_sow=state["formatted_sow"],
        requirement_text=state["requirement_text"],
        draft_scope=state["draft_scope"],
    )

    try:
        msg = await llm.ainvoke(prompt)
        content = getattr(msg, "content", "").strip()
        parsed = _parse_json(content)

        if isinstance(parsed, dict):
            status = parsed.get("status", "PASS").upper()
            feedback = parsed.get("feedback", "")
            logger.info("[GRAPH-SCOPE] Review result: %s | cycle=%d", status, state.get("review_cycle", 0))
            return {"review_status": status, "review_feedback": feedback}
    except Exception as e:
        logger.error("[GRAPH-SCOPE] Review failed: %s", e)

    return {"review_status": "PASS", "review_feedback": ""}


def _scope_should_continue(state: ScopeState) -> str:
    if state.get("review_status") == "REWORK" and state.get("review_cycle", 0) < MAX_REVIEW_CYCLES:
        return "rework"
    return "done"


def build_scope_review_graph() -> StateGraph:
    """Build and compile the Scope review loop graph."""
    graph = StateGraph(ScopeState)

    graph.add_node("generate", _generate_scope)
    graph.add_node("review", _review_scope)

    graph.set_entry_point("generate")
    graph.add_edge("generate", "review")
    graph.add_conditional_edges("review", _scope_should_continue, {
        "rework": "generate",
        "done": END,
    })

    return graph.compile()


# ──────────────────────────────────────────────
# Convenience: pre-compiled graph singletons
# ──────────────────────────────────────────────
mom_review_graph = build_mom_review_graph()
story_review_graph = build_story_review_graph()
scope_review_graph = build_scope_review_graph()
