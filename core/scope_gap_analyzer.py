import os
import json
import logging
from typing import Dict
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()
logging.basicConfig(level=logging.INFO)

def init_llm():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return None
    try:
        model_name = os.getenv("LLM_MODEL_PRO", "deepseek-v4-pro")
        logging.info("[SCOPE] Using model='%s' (Pro — reasoning)", model_name)
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url="https://api.deepseek.com",
            temperature=0.0
        )
    except Exception as e:
        logging.error("[SCOPE] Failed to init LLM: %s", e)
        return None
        
def load_prompt(filename: str) -> str:
    path = os.path.join(os.path.dirname(__file__), "..", "sub_agents", filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _format_sow_for_prompt(sow_text: str) -> str:
    """Format SOW text for the prompt, handling both JSON and plain text."""
    try:
        # Try to parse as JSON
        sow_data = json.loads(sow_text)
        # If it's a dictionary, format it as a string
        if isinstance(sow_data, dict):
            formatted = []
            for key, value in sow_data.items():
                if isinstance(value, (list, dict)):
                    value = json.dumps(value, indent=2)
                formatted.append(f"{key}: {value}")
            return "\n".join(formatted)
        return str(sow_data)
    except (json.JSONDecodeError, TypeError):
        # If not valid JSON, return as plain text
        return sow_text

async def analyze_requirement_scope(sow_text: str, requirement_text: str) -> Dict[str, str]:
    """
    Compare requirement_text with sow_text to decide scope status.
    Uses LangGraph review loop for Actor-Critic feedback, with fallback to single-shot.
    """
    formatted_sow = _format_sow_for_prompt(sow_text)

    # ── Try LangGraph review loop first ──
    try:
        from .graph_workflows import scope_review_graph

        graph_result = await scope_review_graph.ainvoke({
            "formatted_sow": formatted_sow,
            "requirement_text": requirement_text,
            "draft_scope": "",
            "scope_result": {},
            "review_status": "PENDING",
            "review_feedback": "",
            "review_cycle": 0,
        })

        result = graph_result.get("scope_result", {})
        cycles = graph_result.get("review_cycle", 1)
        verdict = graph_result.get("review_status", "PASS")
        logging.info(
            "[SCOPE] Review loop done | cycles=%d verdict=%s status=%s",
            cycles, verdict, result.get("scope_status", "unknown")
        )
        if result and result.get("scope_status"):
            return result
        logging.warning("[SCOPE] Graph returned empty result, falling back to single-shot.")
    except Exception as e:
        logging.error("[SCOPE] Review graph failed, falling back: %s", e)

    # ── Fallback: original single-shot + heuristic ──
    llm = init_llm()

    prompt_template = load_prompt("requirement_scope_analyzer.md")
    prompt = prompt_template.format(formatted_sow=formatted_sow, requirement_text=requirement_text)

    if llm:
        try:
            msg = await llm.ainvoke(prompt)
            content = getattr(msg, "content", "") or ""
            raw = content.strip()

            parsed = None
            try:
                if raw.startswith("{"):
                    parsed = json.loads(raw)
            except Exception:
                parsed = None

            if parsed is None:
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[-1]
                if raw.endswith("```"):
                    raw = raw.rsplit("\n", 1)[0]
                raw = raw.strip()
                try:
                    parsed = json.loads(raw)
                except Exception:
                    start = raw.find("{")
                    end = raw.rfind("}")
                    if start != -1 and end != -1 and end > start:
                        try:
                            parsed = json.loads(raw[start:end+1])
                        except Exception:
                            parsed = None

            if isinstance(parsed, dict):
                status = str(parsed.get("scope_status", "")).strip()
                just = str(parsed.get("justification", "")).strip()
                cite = str(parsed.get("sow_citation", "")).strip()

                s = status.lower()
                if "in" in s and "scope" in s:
                    status = "In Scope"
                elif "out" in s and "scope" in s:
                    status = "Out of Scope"
                elif "clar" in s:
                    status = "Needs Clarification"
                else:
                    status = "Needs Clarification"

                if status == "In Scope" and (sow_text and sow_text.strip()) and not cite:
                    return {"scope_status": "Needs Clarification", "justification": "Analyzer returned no explicit SOW evidence."}

                return {
                    "scope_status": status,
                    "justification": just if just else cite
                }
        except Exception as e:
            logging.error("[SCOPE] LLM error: %s", e)

    # Fallback heuristic
    sow_lower = (sow_text or "").lower()
    req_lower = (requirement_text or "").lower()

    if not requirement_text:
        return {"scope_status": "Needs Clarification", "justification": "Empty requirement text."}

    tokens = [t for t in req_lower.split() if len(t) > 3]
    matches = sum(1 for tok in tokens if tok in sow_lower)
    ratio = (matches / max(1, len(tokens))) if tokens else 0.0

    negative_phrases = [
        "third-party", "external vendor", "excluded", "not in scope", "out of scope",
        "beyond scope", "outside scope"
    ]
    if any(p in req_lower for p in negative_phrases):
        return {"scope_status": "Out of Scope", "justification": "Requirement indicates exclusion or externalization."}

    if ratio >= 0.35 and matches >= 3:
        return {"scope_status": "In Scope", "justification": "Substantial term overlap with SOW."}
    if ratio <= 0.05 and len(tokens) >= 8:
        return {"scope_status": "Out of Scope", "justification": "Minimal overlap with SOW terminology."}

    return {"scope_status": "Needs Clarification", "justification": "Insufficient evidence to determine scope from SOW."}


def analyze_transcript_against_sow(sow_text: str, transcript: str) -> list:
    """
    Analyze a meeting transcript against the SOW to extract and analyze requirements.
    
    Args:
        sow_text: The Statement of Work text (can be plain text or JSON string)
        transcript: Raw meeting transcript text
        
    Returns:
        List of dictionaries, each containing a requirement and its analysis
    """
    llm = init_llm()
    if not llm:
        logging.error("LLM not initialized")
        return []
    
    # Format SOW for the prompt
    formatted_sow = _format_sow_for_prompt(sow_text)
    
    prompt_template = load_prompt("transcript_scope_analyzer.md")
    prompt = prompt_template.format(formatted_sow=formatted_sow, transcript=transcript)
    
    try:
        response = llm.invoke(prompt)
        requirements = json.loads(response.content)
        
        # Validate and clean the response
        if not isinstance(requirements, list):
            logging.error("LLM did not return a list of requirements")
            return []
            
        valid_requirements = []
        for req in requirements:
            if not isinstance(req, dict) or 'text' not in req:
                continue
                
            # Ensure required fields exist
            req['module'] = req.get('module', 'General')
            req['scope_status'] = req.get('scope_status', 'Needs Clarification')
            req['justification'] = req.get('justification', 'No justification provided')
            req['sow_citation'] = req.get('sow_citation', '')
            
            valid_requirements.append(req)
            
        return valid_requirements
        
    except Exception as e:
        logging.error(f"Error in analyze_transcript_against_sow: {str(e)}")
        return []
