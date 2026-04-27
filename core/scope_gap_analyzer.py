import os
import json
import logging
from typing import Dict
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()
logging.basicConfig(level=logging.INFO)

def init_llm():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    try:
        return ChatGoogleGenerativeAI(
            model=os.getenv("LLM_MODEL", "gemini-2.5-flash"),
            google_api_key=api_key,
            temperature=0.0
        )
    except Exception as e:
        logging.error("[SCOPE] Failed to init LLM: %s", e)
        return None

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
    
    Args:
        sow_text: The Statement of Work text, can be plain text or JSON string
        requirement_text: The requirement text to analyze against the SOW
        
    Returns:
        Dict containing scope_status, justification, and optional sow_citation
    """
    llm = init_llm()
    formatted_sow = _format_sow_for_prompt(sow_text)

    prompt = f"""
    You are assisting a Senior Business Analyst.

    Task:
    Compare the given requirement against the Statement of Work (SOW) and decide scope.
    - scope_status MUST be one of: In Scope, Out of Scope, Needs Clarification.
    - justification MUST be a concise reason.
    - sow_citation SHOULD include a short quote/paraphrase from the SOW that supports the decision.

    Respond STRICTLY with JSON only (no preface, no markdown, no code fences):
    {{
      "scope_status": "In Scope | Out of Scope | Needs Clarification",
      "justification": "short reason",
      "sow_citation": "short quote from SOW or empty"
    }}

    SOW:
    {formatted_sow}

    Requirement to analyze:
    {requirement_text}
    """

    if llm:
        try:
            msg = await llm.ainvoke(prompt)
            content = getattr(msg, "content", "") or ""
            raw = content.strip()

            # Try strict JSON first, then strip code fences, then inner JSON extraction
            parsed = None
            try:
                if raw.startswith("{"):
                    parsed = json.loads(raw)
            except Exception:
                parsed = None

            if parsed is None:
                # Remove surrounding code fences if present
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[-1]
                if raw.endswith("```"):
                    raw = raw.rsplit("\n", 1)[0]
                raw = raw.strip()
                try:
                    parsed = json.loads(raw)
                except Exception:
                    # Find inner JSON object within text
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

                # Normalize status to the three allowed values
                s = status.lower()
                if "in" in s and "scope" in s:
                    status = "In Scope"
                elif "out" in s and "scope" in s:
                    status = "Out of Scope"
                elif "clar" in s:
                    status = "Needs Clarification"
                else:
                    status = "Needs Clarification"

                # If claiming In Scope but no citation provided while SOW exists, downgrade to Needs Clarification
                if status == "In Scope" and (sow_text and sow_text.strip()) and not cite:
                    return {"scope_status": "Needs Clarification", "justification": "Analyzer returned no explicit SOW evidence."}

                # Return normalized result
                return {
                    "scope_status": status,
                    "justification": just if just else cite
                }
        except Exception as e:
            logging.error("[SCOPE] LLM error: %s", e)

    # -------------------
    # Fallback heuristic
    # -------------------
    sow_lower = (sow_text or "").lower()
    req_lower = (requirement_text or "").lower()

    if not requirement_text:
        return {"scope_status": "Needs Clarification", "justification": "Empty requirement text."}

    tokens = [t for t in req_lower.split() if len(t) > 3]
    matches = sum(1 for tok in tokens if tok in sow_lower)
    ratio = (matches / max(1, len(tokens))) if tokens else 0.0

    # Strong out-of-scope indicators
    negative_phrases = [
        "third-party", "external vendor", "excluded", "not in scope", "out of scope",
        "beyond scope", "outside scope"
    ]
    if any(p in req_lower for p in negative_phrases):
        return {"scope_status": "Out of Scope", "justification": "Requirement indicates exclusion or externalization."}

    # Heuristic thresholds
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
    
    prompt = f"""
    You are a Business Analyst reviewing meeting transcripts against a Scope of Work (SOW).
    
    TASKS:
    1. Extract key requirements, user stories, or action items mentioned in the transcript.
    2. For each requirement, determine if it is In Scope, Out of Scope, or Needs Clarification
       based on the provided SOW.
    3. For each requirement, provide a brief justification and relevant SOW citation.
    Note: From the meeting transcripts, there could be conversations which are not relevant as a project user stories, so be smart to filter such conversations.
    
    SOW CONTEXT:
    {formatted_sow}
    
    MEETING TRANSCRIPT:
    {transcript}
    
    INSTRUCTIONS:
    - Focus on extracting clear requirements or user stories from the discussion.
    - For each requirement, provide:
      * A clear, concise description
      * Scope status (In Scope, Out of Scope, Needs Clarification)
      * Brief justification
      * Relevant SOW citation (if any)
    - If a requirement is ambiguous, mark it as "Needs Clarification"
    - Group related requirements when appropriate
    
    Respond with a JSON array of requirements. Each requirement should have these fields:
    {{
      "text": "The requirement/user story text",
      "module": "Relevant module/category (if mentioned)",
      "scope_status": "In Scope | Out of Scope | Needs Clarification",
      "justification": "Brief reasoning for the scope decision",
      "sow_citation": "Relevant SOW excerpt or empty"
    }}
    """
    
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
