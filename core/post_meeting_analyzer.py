import os
import json
import logging
from typing import Dict, Any, List, Optional
from io import BytesIO
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
import re
import pandas as pd

from docx import Document  # python-docx must be installed

# Import the LLM logger
from .llm_logger import log_llm_response

# Load .env and configure logging
load_dotenv()
logging.basicConfig(level=logging.INFO)

# ------------------------
# Helper: Initialize LLM
# ------------------------
def init_llm():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logging.warning("[POST-MEETING] GOOGLE_API_KEY not found. Using fallback output.")
        return None
    model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")
    try:
        llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=0.0
        )
        logging.info("[POST-MEETING] LLM initialized | model='%s'", model_name)
        return llm
    except Exception as e:
        logging.error("[POST-MEETING] Failed to init LLM: %s", e)
        return None

# ------------------------
# Helper: Transcript Readers (.txt / .docx)
# ------------------------
def extract_text_from_docx_bytes(data: bytes) -> str:
    """Return plain text from a .docx byte stream. Requires python-docx.

    Falls back to empty string if library unavailable or parsing fails.
    """
    try:
        doc = Document(BytesIO(data))
        parts: List[str] = []
        for p in doc.paragraphs:
            if p.text:
                parts.append(p.text)
        # include simple table text
        for t in getattr(doc, "tables", []):
            for row in t.rows:
                parts.append("\t".join(cell.text for cell in row.cells))
        return "\n".join(parts)
    except Exception as e:
        logging.error("[POST-MEETING] Failed to parse .docx: %s", e)
        return ""

# ------------------------
# Helper: Normalize Speaker Names
# ------------------------
def normalize_speaker_names(items: List[str]) -> List[str]:
    pattern = re.compile(r"^[A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+){0,2}$")
    cleaned: List[str] = []
    seen = set()
    for s in items or []:
        if not isinstance(s, str):
            continue
        s2 = re.sub(r"[^A-Za-z'\-\s]", " ", s)
        s2 = re.sub(r"\s+", " ", s2).strip()
        if not s2:
            continue
        s2 = " ".join(w[:1].upper() + w[1:] for w in s2.split())
        if pattern.fullmatch(s2) and s2 not in seen:
            seen.add(s2)
            cleaned.append(s2)
    return cleaned

def _markdown_to_html(md: str) -> str:
    """Convert simple Markdown to HTML as a fallback when the LLM disobeys the HTML instruction."""
    import re as _re
    lines = md.split("\n")
    html_lines: list = []
    in_ul = False
    in_table = False
    table_header_done = False

    def flush_ul():
        nonlocal in_ul
        if in_ul:
            html_lines.append("</ul>")
            in_ul = False

    def flush_table():
        nonlocal in_table, table_header_done
        if in_table:
            html_lines.append("</tbody></table>")
            in_table = False
            table_header_done = False

    def inline(text: str) -> str:
        """Convert inline markdown (**bold**, *italic*, `code`) to HTML."""
        text = _re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', text)
        text = _re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = _re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = _re.sub(r'`(.+?)`', r'<code>\1</code>', text)
        return text

    for line in lines:
        stripped = line.strip()

        # Markdown table row
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            # separator row
            if all(_re.match(r'^[-: ]+$', c) for c in cells):
                if not table_header_done and in_table:
                    html_lines.append("</thead><tbody>")
                    table_header_done = True
                continue
            if not in_table:
                flush_ul()
                html_lines.append('<table style="width:100%;border-collapse:collapse;margin:12px 0;">')
                html_lines.append("<thead><tr>")
                for c in cells:
                    html_lines.append(f'<th style="padding:8px 12px;border:1px solid rgba(255,255,255,0.1);background:rgba(99,102,241,0.15);color:#a8b1ff;font-size:0.8rem;text-transform:uppercase;">{inline(c)}</th>')
                html_lines.append("</tr>")
                in_table = True
                table_header_done = False
            else:
                html_lines.append("<tr>")
                for c in cells:
                    html_lines.append(f'<td style="padding:8px 12px;border:1px solid rgba(255,255,255,0.1);color:#c8cdd6;vertical-align:top;">{inline(c)}</td>')
                html_lines.append("</tr>")
            continue
        else:
            flush_table()

        # Headings
        h_match = _re.match(r'^(#{1,4})\s+(.*)', stripped)
        if h_match:
            flush_ul()
            level = len(h_match.group(1))
            text = inline(h_match.group(2))
            colors = {1: '#6366f1', 2: '#6366f1', 3: '#a8b1ff', 4: '#c8cdd6'}
            color = colors.get(level, '#c8cdd6')
            border = 'border-bottom:1px solid rgba(255,255,255,0.1);padding-bottom:6px;margin:20px 0 10px;' if level <= 2 else 'margin:16px 0 8px;'
            html_lines.append(f'<h{level} style="color:{color};{border}">{text}</h{level}>')
            continue

        # Bullet list item
        if _re.match(r'^[-*+]\s+', stripped):
            if not in_ul:
                html_lines.append('<ul style="margin:8px 0 12px 0;padding-left:24px;line-height:1.7;">')
                in_ul = True
            text = inline(_re.sub(r'^[-*+]\s+', '', stripped))
            html_lines.append(f'<li style="margin-bottom:5px;color:#c8cdd6;">{text}</li>')
            continue
        else:
            flush_ul()

        # Horizontal rule
        if stripped in ('---', '***', '___'):
            html_lines.append('<hr style="border:none;border-top:1px solid rgba(255,255,255,0.1);margin:16px 0;">')
            continue

        # Empty line
        if not stripped:
            html_lines.append('')
            continue

        # Regular paragraph text
        html_lines.append(f'<p style="margin:0 0 8px 0;color:#c8cdd6;line-height:1.7;">{inline(stripped)}</p>')

    flush_ul()
    flush_table()
    return "\n".join(html_lines)


def sanitize_mom_html(raw: str) -> str:
    """Strip code fences from LLM output, and convert Markdown→HTML if the LLM disobeyed."""
    if not isinstance(raw, str):
        return ""

    s = raw.strip()

    # Strip code fences
    for fence in ("```html", "```markdown", "```"):
        if s.startswith(fence):
            s = s[len(fence):].lstrip("\n")
            break
    if s.endswith("```"):
        s = s[:s.rfind("```")].rstrip()

    s = s.strip()

    # If the output looks like Markdown (not HTML), convert it
    looks_like_html = s.startswith("<") or "<div" in s[:50] or "<h2" in s[:50] or "<h3" in s[:50]
    if not looks_like_html:
        s = _markdown_to_html(s)

    return s


# Keep old name as alias for backward compatibility
def sanitize_mom_markdown_table(md: str) -> str:
    return sanitize_mom_html(md)


def read_transcript_bytes(filename: str, content: bytes) -> str:
    """Decode uploaded file bytes to plain text.

    Supports:
    - .txt (utf-8/utf-16/latin-1 fallback)
    - .docx (via python-docx)
    """
    name = (filename or "").lower()
    if name.endswith(".docx"):
        return extract_text_from_docx_bytes(content)
    # default treat as text
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return content.decode(enc)
        except Exception:
            continue
    return ""

# ------------------------
# New: Speaker Extraction via LLM
# ------------------------
async def extract_speakers_llm(transcript: str) -> List[str]:
    """
    Use the configured LLM to extract DISTINCT human speaker names from a raw transcript.

    Returns a list of names (strings). If the LLM/key is unavailable, returns an empty list.
    """
    llm = init_llm()
    if not llm:
        return []
        
    # Prepare metadata for logging
    metadata = {
        'stage': 'speaker_extraction',
        'model': os.getenv("LLM_MODEL", "gemini-2.5-flash"),
        'transcript_length': len(transcript),
        'timestamp': pd.Timestamp.utcnow().isoformat()
    }

    system_instructions = (
        "You extract ONLY human speaker names from meeting transcripts. "
        "Return STRICT JSON with a single key 'speakers' containing an array of distinct names. "
        "Guidelines: Names are 1-3 words, capitalized properly. Exclude roles/titles (e.g., 'Manager'), "
        "exclude generic words, timestamps, and acronyms. If unsure, omit. "
        "CRITICAL: If a speaker is referred to with both first and last name, "
        "return the FULL multi-word name (e.g., 'Priya Sharma'), not split parts."
    )

    user_prompt = (
        "Transcript:\n" + transcript +
        "\n\nOutput JSON schema (no prose, no code fences): {\"speakers\": [\"Name\", ...]}"
    )

    try:
        # Combine system instructions and user prompt
        full_prompt = system_instructions + "\n\n" + user_prompt
        
        # Call the LLM
        msg = await llm.ainvoke(full_prompt)
        content = getattr(msg, "content", "").strip()
        
        # Log the response
        log_llm_response(
            prompt=full_prompt,
            response=content,
            metadata=metadata
        )
        if not content:
            return []
        try:
            data = json.loads(content)
            speakers = data.get("speakers", [])
            # Post-process: ensure unique strings, strip whitespace, remove empties
            unique = []
            seen = set()
            for s in speakers:
                if not isinstance(s, str):
                    continue
                name = s.strip()
                if not name:
                    continue
                if name not in seen:
                    seen.add(name)
                    unique.append(name)
            return normalize_speaker_names(unique)
        except Exception:
            # If model did not return JSON, try to salvage simple comma/newline separated names
            rough = [p.strip() for p in content.replace("\n", ",").split(",")]
            return normalize_speaker_names(rough)
    except Exception:
        return []

# ------------------------
# Core Analyzer Function
# ------------------------
async def analyze_transcript_text(
    transcript: str,
    speaker_tags: Dict[str, str],
    discovery_plan: Dict[str, Any],
    sow_text: str
) -> Dict[str, Any]:
    """
    Analyze transcript using five specialized prompts. Aggregates results with robust fallbacks.
    """
    llm = init_llm()

    async def call_llm_json(prompt_text: str, metadata: Optional[Dict[str, Any]] = None) -> Any:
        try:
            metadata = metadata or {}
            metadata.update({
                'stage': 'post_meeting_analysis',
                'model': os.getenv("LLM_MODEL", "gemini-2.5-flash"),
                'timestamp': pd.Timestamp.utcnow().isoformat()
            })
            msg_loc = await llm.ainvoke(prompt_text)
            content_loc = getattr(msg_loc, "content", "").strip()
            log_llm_response(prompt=prompt_text, response=content_loc, metadata=metadata)
            if not content_loc:
                return None
            # Try direct JSON
            try:
                return json.loads(content_loc)
            except Exception:
                pass
            # Strip code-fence wrappers
            cleaned = content_loc
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("\n", 1)[0]
            cleaned = cleaned.strip()
            try:
                return json.loads(cleaned)
            except Exception:
                start = cleaned.find("{")
                end = cleaned.rfind("}")
                if start != -1 and end != -1 and end > start:
                    inner = cleaned[start:end+1]
                    try:
                        return json.loads(inner)
                    except Exception:
                        pass
                return content_loc
        except Exception as e:
            logging.error("[POST-MEETING] LLM call failed: %s", e)
            return None

    async def call_llm_raw(prompt_text: str, stage: str = 'mom') -> str:
        """Call LLM and return raw text — used for prompts that return HTML, not JSON."""
        try:
            metadata = {
                'stage': stage,
                'model': os.getenv("LLM_MODEL", "gemini-2.5-flash"),
                'timestamp': pd.Timestamp.utcnow().isoformat()
            }
            msg_loc = await llm.ainvoke(prompt_text)
            content_loc = getattr(msg_loc, "content", "").strip()
            log_llm_response(prompt=prompt_text, response=content_loc, metadata=metadata)
            return content_loc
        except Exception as e:
            logging.error("[POST-MEETING] LLM raw call failed: %s", e)
            return ""

    transcript_block = transcript
    
    # Convert SOW to JSON format if it's not already
    try:
        if isinstance(sow_text, str) and (sow_text.startswith('{') or sow_text.startswith('[')):
            # If it looks like JSON, parse and re-serialize to ensure valid JSON
            sow_json = json.loads(sow_text)
            sow_block = json.dumps(sow_json, ensure_ascii=False, indent=2)
        else:
            # If it's plain text, create a simple JSON structure
            sow_block = json.dumps({"sow_text": sow_text}, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, TypeError):
        # Fallback to plain text if conversion fails
        sow_block = json.dumps({"sow_text": str(sow_text)}, ensure_ascii=False, indent=2)
    
    # Ensure discovery_plan is properly formatted JSON
    if not isinstance(discovery_plan, (dict, list)):
        try:
            discovery_plan = json.loads(str(discovery_plan))
        except (json.JSONDecodeError, TypeError):
            discovery_plan = {"discovery_plan": str(discovery_plan)}
    
    discovery_block = json.dumps(discovery_plan, ensure_ascii=False, indent=2)
    speaker_tags_block = json.dumps(speaker_tags, ensure_ascii=False, indent=2)

    aggregated: Dict[str, Any] = {
        "mom": "",
                    "on_track_topics": [],
                    "off_track_topics": [],
                    "provisional_user_stories": [],
                    "open_topics": []
                }

    if llm:
        logging.info("[POST-MEETING] Starting LLM analysis with 5 specialized prompts...")
        
        # 1) MoM
        logging.info("[POST-MEETING] Processing MoM prompt...")
        mom_prompt = f"""
CRITICAL INSTRUCTION — READ FIRST:
You MUST output ONLY valid HTML. Do NOT use Markdown syntax of any kind.
Do NOT use: pipe tables (| col |), **bold**, ## headings, - bullets, or ```code fences```.
Your ENTIRE response must be a single HTML fragment starting with <div class="mom-report">.
No preamble. No explanation. No code fences. Start directly with <div.

---

You are a professional Business Analyst generating the Minutes of Meeting (MoM) as a structured HTML document.

Your output MUST:
1. Start with <div class="mom-report">
2. Use <h2> for the meeting title
3. Use a <p> block for Date, Organizer, and Attendees (using <strong> labels and <br> separators)
4. Use <h3> sections for: 📌 Key Discussions, 🎯 Key Decisions, 🚀 Action Items
5. Use <ul><li> for all bullet content
6. For Action Items: wrap the owner name in <strong style="color:#ef4444;">Owner:</strong>
7. End with </div>

EXACT OUTPUT FORMAT (follow this structure precisely):

<div class="mom-report">
  <h2 style="color:#6366f1;border-bottom:1px solid #333;padding-bottom:8px;">Meeting Minutes: [Agenda Title]</h2>
  <p>
    <strong>📅 Date:</strong> [Date]<br>
    <strong>👤 Organizer:</strong> [Organizer]<br>
    <strong>👥 Attendees:</strong> [Name (Role), Name (Role), ...]
  </p>

  <h3 style="color:#a8b1ff;margin-top:24px;">📌 Key Discussions</h3>
  <ul style="line-height:1.7;">
    <li><strong>[Topic Title]:</strong> [One concise sentence summarizing the discussion point. Then bullet sub-items if needed.]</li>
    <li><strong>[Topic Title]:</strong> [...]</li>
  </ul>

  <h3 style="color:#a8b1ff;margin-top:24px;">🎯 Key Decisions</h3>
  <ul style="line-height:1.7;">
    <li>[Decision made in the meeting.]</li>
  </ul>

  <h3 style="color:#a8b1ff;margin-top:24px;">🚀 Action Items</h3>
  <ul style="line-height:1.7;list-style-type:square;">
    <li><strong style="color:#ef4444;">[Owner/Team]:</strong> [Specific task to be done.]</li>
  </ul>
</div>

RULES FOR CONTENT:
- Attendees: use ONLY names from Speaker Tags below. Format: Name (Role), Name (Role).
- Key Discussions: 6–10 distinct professional topic points. No paragraphs — bullets only.
- Key Decisions: concrete decisions made during the meeting.
- Action Items: aggressively extract all tasks/commitments with owners. Assign to team if no person named.
- Exclude: small talk, scheduling, technical troubleshooting.
- If no action items exist, write: <li>No specific action items identified.</li>

---

INPUT DATA:
Transcript: {transcript_block}
Speaker Tags (name→role): {speaker_tags_block}
Discovery Plan (context): {discovery_block}
SOW (context): {sow_block}

Remember: Output ONLY the HTML. Start with <div class="mom-report">. No markdown. No code fences.
        """

        try:
            logging.info("[POST-MEETING] Sending MOM prompt to LLM (raw HTML mode)...")
            mom_raw = await call_llm_raw(mom_prompt, stage='mom')
            aggregated["mom"] = sanitize_mom_html(mom_raw)
            logging.info(f"[POST-MEETING] MoM result length: {len(aggregated['mom'])} chars")
        except Exception as e:
            logging.error(f"[POST-MEETING] MoM prompt failed: {e}")

        # ------------------------
        # Helper: Format On-Track Topics as Markdown Table
        # ------------------------
        def format_on_track_topics_table(items: List[Dict[str, str]]) -> str:
            """Convert structured on-track topic items into a Markdown table."""
            if not items:
                return "| Topic | Related Sub-Module | Related Discovery Topic |\n| --- | --- | --- |\n| No on-track topics identified | - | - |"
            
            table = ["| Topic | Related Sub-Module | Related Discovery Topic |", "| --- | --- | --- |"]
            for item in items:
                topic = item.get("topic", "").replace("|", "\\|")
                sub = item.get("related_submodule", "").replace("|", "\\|")
                disc = item.get("related_discovery_topic", "").replace("|", "\\|")
                table.append(f"| {topic} | {sub} | {disc} |")
            return "\n".join(table)


        # 2) On-track topics
        logging.info("[POST-MEETING] Processing on-track topics prompt...")
        on_track_prompt = f"""
        You are an experienced Business Analyst assisting in a Post-Meeting Analysis.
        Your role is to identify **On-Track Topics** — items discussed during the meeting that clearly align with the **agreed scope, deliverables, or requirements** documented in the Discovery Plan and SOW.

        ### INSTRUCTIONS
        1. Carefully review the meeting transcript and map each relevant discussion to:
        - The related **sub-module** or section from the SOW (e.g., Recruitment, Payroll, Asset Management, etc.)
        - The relevant **topic or requirement area** from the Discovery Plan (e.g., Functional Requirement, Data Flow, Integration).
        2. Include a topic as **On-Track** only if:
        - It directly supports an existing scope item or sub-module.
        - It represents progress, validation, or confirmation of in-scope deliverables.
        - It aligns with agreed business objectives or signed-off user stories.
        3. For each On-Track item, extract:
        - `topic`: concise phrase (≤ 20 words) summarizing the discussion point.
        - `related_submodule`: sub-area from the SOW most related to it.
        - `related_discovery_topic`: Discovery Plan topic or section most related to it.
        4. Avoid generic statements, duplicate items, or administrative talk.

        ### OUTPUT FORMAT
        Return **STRICT JSON ONLY**:
        {{
        "items": [
            {{
            "topic": "short descriptive phrase",
            "related_submodule": "SOW sub-module name or 'Not Found'",
            "related_discovery_topic": "Discovery Plan topic or 'Not Found'"
            }}
        ]
        }}

        ### CONTEXT
        SOW (Scope of Work): {sow_block}
        Discovery Plan: {discovery_block}
        Meeting Transcript: {transcript_block}
        """

        try:
            on_out = await call_llm_json(on_track_prompt)
            parsed_items = []

            if isinstance(on_out, dict):
                parsed_items = on_out.get("items", [])
            elif isinstance(on_out, str):
                try:
                    parsed_items = json.loads(on_out).get("items", [])
                except Exception:
                    parts = [p.strip("- •\t ") for p in on_out.replace("\n", ",").split(",")]
                    parsed_items = [{"topic": p, "related_submodule": "-", "related_discovery_topic": "-"} for p in parts if p]

            if isinstance(parsed_items, list):
                aggregated["on_track_topics"] = parsed_items
                aggregated["on_track_topics_table"] = format_on_track_topics_table(parsed_items)
            else:
                aggregated["on_track_topics"] = []
                aggregated["on_track_topics_table"] = format_on_track_topics_table([])

            logging.info(f"[POST-MEETING] On-track topics: {len(aggregated['on_track_topics'])} items")
        except Exception as e:
            logging.error(f"[POST-MEETING] On-track topics prompt failed: {e}")
            aggregated["on_track_topics"] = []
            aggregated["on_track_topics_table"] = format_on_track_topics_table([])

        def format_off_track_topics_table(items: List[Dict[str, str]]) -> str:
            """Convert structured off-track topic items into a detailed Markdown table."""
            if not items:
                return (
                    "| Status | Topic | Related to SOW | Related to Discovery |\n"
                    "| --- | --- | --- | --- |\n"
                    "| ✅ | No off-track topics identified | - | - |"
                )

            table = [
                "| Status | Topic | Related to SOW | Related to Discovery |",
                "| --- | --- | --- | --- |"
            ]
            
            for item in items:
                # Safely get values with defaults
                topic = str(item.get("topic", "")).replace("|", "\\|")
                sub = str(item.get("related_submodule", "Not in SOW")).replace("|", "\\|")
                disc = str(item.get("related_discovery_topic", "Not in Discovery")).replace("|", "\\|")
                
                # Determine status emoji
                status = "⚠️"  # Default warning
                if "not in" in sub.lower() or "not in" in disc.lower():
                    status = "❌"  # Critical if not in either document
                
                table.append(
                    f"| {status} | {topic} | {sub} | {disc} |"
                )
                
            return "\n".join(table)

        # -------------------
        # 3) Off-track topics
        # -------------------
        logging.info("[POST-MEETING] Processing off-track topics prompt...")

        off_track_prompt = f"""
        You are a Senior Business Analyst reviewing a meeting transcript against the Discovery Plan and SOW.

        ## TASK
        Identify **2-3 Off-Track Topics** — discussions, requests, or ideas that appear **outside the defined project scope** or **not covered** in the official requirement documentation.
        
        ### IMPORTANT INSTRUCTIONS:
        1. **MUST INCLUDE 2-3 TOPICS** - Always find and return between 2-3 off-track topics. If you can't find 2-3, look harder as there are always at least 2-3 potential off-track items in any meeting.
        2. **BE THOROUGH** - Carefully analyze every part of the discussion for potential scope creep or out-of-scope items.
        3. **BE SPECIFIC** - Each topic should be distinct and represent a separate concern or request.

        ### IDENTIFICATION CRITERIA:
        A topic is **Off-Track** if it meets ANY of these conditions:
        - Introduces new features, systems, or functionality not in current plans
        - Pertains to business areas not covered by the SOW
        - Expands scope, adds new integrations, or shifts priorities
        - Implies dependencies requiring formal change requests
        - Goes beyond current phase goals or high-level definitions

        ### OUTPUT REQUIREMENTS:
        For EACH of the 2-3 identified topics, provide:
        1. `topic`: Clear, specific phrase (15-25 words)
        2. `related_submodule`: Closest SOW section or "Not Found"
        3. `related_discovery_topic`: Closest Discovery Plan item or "Not Found"

        ### OUTPUT FORMAT (STRICT JSON ONLY):
        {{
          "items": [
            {{
                "topic": "short descriptive phrase summarizing the off-track point",
                "related_submodule": "SOW sub-module name or 'Not Found'",
                "related_discovery_topic": "Discovery Plan topic or 'Not Found'"
            }}
          ]
        }}

        ### EXAMPLES OF OFF-TRACK TOPICS:
        
        **Example 1:**
        ```json
        {{
          "topic": "AI to perform prescriptive root cause analysis on win/loss reasons (beyond scoring).",
          "related_submodule": "Reports & Dashboards",
          "related_discovery_topic": "Sales Cloud + Einstein (Part 2)"
        }}
        ```

        **Example 2:**
        ```json
        {{
          "topic": "AI searching general web/search engines for potential leads or vendors.",
          "related_submodule": "Opportunity Identification",
          "related_discovery_topic": "Sales Cloud + Einstein (Part 1)"
        }}
        ```

        **Example 3:**
        ```json
        {{
          "topic": "Automated email campaign personalization based on social media activity.",
          "related_submodule": "Not Found",
          "related_discovery_topic": "Not Found"
        }}
        ```

        ### FINAL OUTPUT REQUIREMENTS:
        1. **MUST** return EXACTLY 2-3 off-track topics
        2. **MUST** use the exact JSON structure shown in examples
        3. **MUST** include all three fields for each topic
        4. **MUST** return valid JSON that can be parsed
        ```

        ### CONTEXT
        SOW (Scope of Work): {sow_block}
        Discovery Plan: {discovery_block}
        Meeting Transcript: {transcript_block}
        """

        try:
            off_out = await call_llm_json(off_track_prompt)
            parsed_items = []

            if isinstance(off_out, dict):
                parsed_items = off_out.get("items", [])
            elif isinstance(off_out, str):
                try:
                    parsed_items = json.loads(off_out).get("items", [])
                except Exception:
                    parts = [p.strip("- •\t ") for p in off_out.replace("\n", ",").split(",")]
                    parsed_items = [{"topic": p, "related_submodule": "-", "related_discovery_topic": "-"} for p in parts if p]

            if isinstance(parsed_items, list):
                # Filter out any empty or invalid items
                valid_items = [
                    item for item in parsed_items 
                    if isinstance(item, dict) and 
                    item.get('topic', '').strip() and 
                    any(key in item for key in ['related_submodule', 'related_discovery_topic', 'impact', 'recommendation'])
                ]
                
                # Log the number of valid off-track topics found
                if valid_items:
                    logging.info(f"[POST-MEETING] Found {len(valid_items)} valid off-track topics")
                    for i, item in enumerate(valid_items, 1):
                        logging.info(f"[POST-MEETING] Off-track topic {i}: {item.get('topic', 'No topic')}")
                else:
                    logging.info("[POST-MEETING] No valid off-track topics identified")
                
                aggregated["off_track_topics"] = valid_items
                aggregated["off_track_topics_table"] = format_off_track_topics_table(valid_items)
            else:
                logging.warning("[POST-MEETING] Parsed items is not a list")
                aggregated["off_track_topics"] = []
                aggregated["off_track_topics_table"] = format_off_track_topics_table([])

            logging.info(f"[POST-MEETING] Off-track topics: {len(aggregated['off_track_topics'])} items")
        except Exception as e:
            logging.error(f"[POST-MEETING] Off-track topics prompt failed: {e}")
            aggregated["off_track_topics"] = []
            aggregated["off_track_topics_table"] = format_off_track_topics_table([])


        # 4) Open topics
        logging.info("[POST-MEETING] Processing open topics prompt...")
        open_prompt = f"""
        You are acting as a Business Analyst capturing **Open-Ended Topics** from a client meeting.

        These represent **questions, dependencies, or unclear items** that require **follow-up, clarification, or decision-making** after the meeting.

        ### INSTRUCTIONS
        1. Carefully analyze the transcript for:
        - Areas where the client or team was uncertain.
        - Points deferred for future discussion.
        - Requirements or dependencies that lack clarity or ownership.
        - Assumptions made without confirmation.
        2. Convert such items into **crisp, BA-style follow-up questions** or statements.
        3. Exclude casual or irrelevant queries (e.g., greetings, logistics).
        4. Prioritize **3–12 most important** follow-ups. Keep each ≤ 20 words.
        5. Ensure the topics are specific and actionable (avoid generic “to be discussed” phrases).

        ### OUTPUT FORMAT
        Return **STRICT JSON ONLY**, no markdown or prose:
        {{
        "items": [
            "Question or clarification 1",
            "Question or clarification 2"
        ]
        }}

        ### CONTEXT
        SOW (Scope of Work): {sow_block}
        Discovery Plan: {discovery_block}
        Meeting Transcript: {transcript_block}
        """
        try:
            open_out = await call_llm_json(open_prompt)
            if isinstance(open_out, dict):
                aggregated["open_topics"] = [str(x) for x in open_out.get("items", [])]
            elif isinstance(open_out, str):
                parts = [p.strip("- •\t ") for p in open_out.replace("\n", ",").split(",")]
                aggregated["open_topics"] = [p for p in parts if p]
            logging.info(f"[POST-MEETING] Open topics: {len(aggregated['open_topics'])} items")
        except Exception as e:
            logging.error(f"[POST-MEETING] Open topics prompt failed: {e}")
            aggregated["open_topics"] = []


        # 5) Provisional user stories
        logging.info("[POST-MEETING] Processing provisional user stories prompt...")
        stories_prompt = (
            "You are an expert Business Analyst (BA) AI assistant.\n"
            "Your task is to extract all *Provisional User Stories* from the meeting transcript below.\n"
            "These are new or changed requirements that were mentioned in the conversation.\n\n"
            "### INSTRUCTIONS\n"
            "- Only include requirements that are explicitly discussed or implied in the transcript.\n"
            "- Write each user story in clear, concise BA format (e.g., 'The system shall...', 'As a Manager, I want...').\n"
            "- Each story must have a probable 'module' or feature name, inferred from context (e.g., Payroll, HR, Analytics, Dashboard, Attendance, etc.).\n"
            "- Each story must include the following fixed fields:\n"
            "  * text → the full requirement/user story\n"
            "  * module → relevant functional area or subsystem\n"
            "  * status → always 'Provisional'\n"
            "  * scope_status → always 'Pending'\n"
            "  * scope_justification → short blank string (to be filled by scope analyzer later)\n\n"
            "### OUTPUT FORMAT\n"
            "Return STRICT JSON ONLY — no markdown, no prose — in this exact schema:\n"
            "{\n"
            "  \"stories\": [\n"
            "    {\n"
            "      \"text\": \"The system shall ...\",\n"
            "      \"module\": \"Payroll Management\",\n"
            "      \"status\": \"Provisional\",\n"
            "      \"scope_status\": \"Pending\",\n"
            "      \"scope_justification\": \"\"\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            "If there are no new or updated requirements, return:\n"
            "{\"stories\": []}\n\n"
            "### CONTEXT\n"
            f"SOW (Scope of Work): {sow_block}\n"
            f"Discovery Plan: {discovery_block}\n"
            f"Speaker Tags: {speaker_tags_block}\n"
            f"Transcript: {transcript_block}\n"
        )
        try:
            stories_out = await call_llm_json(stories_prompt)
            if isinstance(stories_out, dict):
                stories = stories_out.get("stories", [])
                normalized: List[Dict[str, Any]] = []
                for item in stories:
                    if isinstance(item, dict):
                        normalized.append({
                            "text": str(item.get("text", "")),
                            "module": str(item.get("module", "General")),
                            "status": str(item.get("status", "Provisional")),
                            "scope_status": str(item.get("scope_status", "Pending")),
                            "scope_justification": str(item.get("scope_justification", "")),
                        })
                    else:
                        normalized.append({
                            "text": str(item),
                            "module": "General",
                            "status": "Provisional",
                            "scope_status": "Pending",
                            "scope_justification": ""
                        })
                aggregated["provisional_user_stories"] = normalized
            elif isinstance(stories_out, str):
                # Attempt to parse JSON after cleaning fences
                cleaned = stories_out
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[-1]
                if cleaned.endswith("```"):
                    cleaned = cleaned.rsplit("\n", 1)[0]
                cleaned = cleaned.strip()
                added: List[Dict[str, Any]] = []
                try:
                    obj = json.loads(cleaned)
                    arr = obj.get("stories", []) if isinstance(obj, dict) else obj
                    for item in arr:
                        if isinstance(item, dict):
                            added.append({
                                "text": str(item.get("text", "")),
                                "module": str(item.get("module", "General")),
                                "status": str(item.get("status", "Provisional")),
                                "scope_status": str(item.get("scope_status", "Pending")),
                                "scope_justification": str(item.get("scope_justification", "")),
                            })
                        else:
                            added.append({
                                "text": str(item),
                                "module": "General",
                                "status": "Provisional",
                                "scope_status": "Pending",
                                "scope_justification": ""
                            })
                except Exception:
                    # Fallback: split lines into simple story texts
                    for line in cleaned.splitlines():
                        val = line.strip("- •\t ")
                        if not val:
                            continue
                        added.append({
                            "text": val,
                            "module": "General",
                            "status": "Provisional",
                            "scope_status": "Pending",
                            "scope_justification": ""
                        })
                if added:
                    aggregated["provisional_user_stories"] = added
            logging.info(f"[POST-MEETING] Provisional stories: {len(aggregated['provisional_user_stories'])} items")
        except Exception as e:
            logging.error(f"[POST-MEETING] Provisional stories prompt failed: {e}")
            aggregated["provisional_user_stories"] = []

    # Ensure all fields have data - deterministic, honest fallbacks
    if not aggregated["mom"]:
        # Keep fallback concise — use HTML so dangerouslySetInnerHTML renders correctly
        aggregated["mom"] = (
            "<div class='mom-report' style='padding:16px;'>"
            "<h3 style='color:#ef4444;'>⚠️ Minutes of Meeting Unavailable</h3>"
            "<p>The AI backend was unable to generate a meeting summary.</p>"
            "<ul><li>Please ensure <strong>GOOGLE_API_KEY</strong> is configured correctly.</li>"
            "<li>Verify the LLM model name in your <code>.env</code> file and retry.</li></ul>"
            "</div>"
        )
    
    # Do not fabricate topics when AI is unavailable; keep lists empty
    if not aggregated["on_track_topics"]:
        aggregated["on_track_topics"] = []
    
    if not aggregated["off_track_topics"]:
        aggregated["off_track_topics"] = []
    
    if not aggregated["open_topics"]:
        # In fallback mode, do not fabricate or derive open topics
        aggregated["open_topics"] = []
    
    if not aggregated["provisional_user_stories"]:
        aggregated["provisional_user_stories"] = []

    logging.info(f"[POST-MEETING] Final result: mom={len(aggregated['mom'])} chars, on_track={len(aggregated['on_track_topics'])}, off_track={len(aggregated['off_track_topics'])}, open={len(aggregated['open_topics'])}, stories={len(aggregated['provisional_user_stories'])}")
    return aggregated