import json
from typing import List, Dict, Any
import logging
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

logger = logging.getLogger(__name__)

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
        timeout=180.0, # 3 minutes per module
    )


async def synthesize_user_stories_stream(raw_requirements_text: str):
    """
    Streaming version of synthesize_user_stories.
    Yields dicts with 'status' and 'message'.
    Final yield is the list of stories.
    """
    if not raw_requirements_text or not raw_requirements_text.strip():
        yield {"status": "error", "message": "No requirements provided"}
        return

    try:
        from .graph_workflows import story_review_graph

        initial_state = {
            "requirements_text": raw_requirements_text,
            "draft_stories": "",
            "validated_stories": [],
            "review_status": "PENDING",
            "review_feedback": "",
            "review_cycle": 0,
        }

        # Use LangGraph astream to track progress
        async for event in story_review_graph.astream(initial_state, stream_mode="updates"):
            # event is a dict mapping node_name -> output_of_node
            for node_name, output in event.items():
                if node_name == "generate":
                    cycle = output.get("review_cycle", 1)
                    if cycle == 1:
                        yield {"status": "progress", "message": "🤖 Story Agent is drafting stories...", "step": 2}
                    else:
                        yield {"status": "progress", "message": f"🔄 Reworking stories based on feedback (Cycle {cycle-1})...", "step": 2}
                
                elif node_name == "review":
                    status = output.get("review_status")
                    feedback = output.get("review_feedback")
                    if status == "REWORK":
                        yield {"status": "progress", "message": f"🔍 Agile Coach found issues: {feedback[:100]}...", "step": 3}
                    else:
                        yield {"status": "progress", "message": "✅ Agile Coach approved the stories!", "step": 4}

        # Get final state to return stories
        # Since we use astream, we need to keep track of the final validated_stories
        # Or just run one final ainvoke to get the full state if needed, but astream updates should have it
        # Actually, the last event in 'updates' mode for a node that finishes will have the state change.
        # Let's just do a final ainvoke if we want the full end state easily, or track it in the loop.
        
        final_state = await story_review_graph.ainvoke(initial_state)
        validated = final_state.get("validated_stories", [])
        yield {"status": "complete", "stories": validated}

    except Exception as e:
        logger.error(f"Streaming story generation failed: {e}")
        yield {"status": "error", "message": str(e)}

async def synthesize_user_stories(raw_requirements_text: str) -> List[Dict[str, Any]]:
    if not raw_requirements_text or not raw_requirements_text.strip():
        return []

    # ── Try LangGraph review loop first ──
    try:
        from .graph_workflows import story_review_graph

        graph_result = await story_review_graph.ainvoke({
            "requirements_text": raw_requirements_text,
            "draft_stories": "",
            "validated_stories": [],
            "review_status": "PENDING",
            "review_feedback": "",
            "review_cycle": 0,
        })

        validated = graph_result.get("validated_stories", [])
        cycles = graph_result.get("review_cycle", 1)
        verdict = graph_result.get("review_status", "PASS")
        logger.info(
            "Story review loop done | cycles=%d verdict=%s stories=%d",
            cycles, verdict, len(validated)
        )
        if validated:
            return validated
        # If graph returned empty, fall through to single-shot
        logger.warning("Story review graph returned 0 stories, falling back to single-shot.")
    except Exception as e:
        logger.error(f"Story review graph failed, falling back to single-shot: {e}")

    # ── Fallback: original single-shot generation ──
    client = _init_client()
    model_name = os.getenv("LLM_MODEL_PRO", "deepseek-v4-pro")
    
    try:
        max_tokens = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "4096"))
    except:
        max_tokens = 4096

    prompt_template = load_prompt("story_generator.md")
    prompt = prompt_template.format(requirements_text=raw_requirements_text)

    logger.info(f"Calling DeepSeek API ({model_name}) for story generation (single-shot fallback)...")
    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a professional business analyst that outputs only valid JSON arrays."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=max_tokens
        )
        response_text = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"DeepSeek API call failed: {str(e)}")
        raise ValueError(f"AI generation failed: {str(e)}")

    if not response_text:
        return []

    # Robust JSON extraction
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
            
        if json_start == -1 or json_end == 0:
            logger.error(f"No JSON found in response snippet: {response_text[:200]}")
            return []

        json_str = response_text[json_start:json_end]
        data = json.loads(json_str)
        stories = data if isinstance(data, list) else [data]
        
    except Exception as e:
        logger.error(f"JSON parsing failed: {e}")
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
            "acceptance_criteria": [str(c).strip() for c in story.get("acceptance_criteria", story.get("acceptanceCriteria", [])) if str(c).strip()]
        })

    return validated

