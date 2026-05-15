import os
import json
import logging
from typing import Dict, Any, List, Optional
from io import BytesIO
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import re
import pandas as pd

from docx import Document  # python-docx must be installed

# Import the LLM logger
from .llm_logger import log_llm_response

# Load .env and configure logging
load_dotenv()
logging.basicConfig(level=logging.INFO)

def load_prompt(filename: str) -> str:
    path = os.path.join(os.path.dirname(__file__), "..", "sub_agents", filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# ------------------------
# Helper: Initialize LLM
# ------------------------
def init_llm(use_flash: bool = False):
    """Initialize LLM. use_flash=True selects the fast Flash model for simple extraction tasks."""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        logging.warning("[POST-MEETING] DEEPSEEK_API_KEY not found. Using fallback output.")
        return None
    if use_flash:
        model_name = os.getenv("LLM_MODEL_FLASH", "deepseek-v4-flash")
    else:
        model_name = os.getenv("LLM_MODEL_PRO", "deepseek-v4-pro")
    try:
        llm = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url="https://api.deepseek.com",
            temperature=0.0
        )
        variant = "Flash — fast extraction" if use_flash else "Pro — reasoning"
        logging.info("[POST-MEETING] LLM initialized | model='%s' (%s)", model_name, variant)
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
    # Speaker extraction is a simple task → use Flash for speed
    llm = init_llm(use_flash=True)
    if not llm:
        return []
        
    # Prepare metadata for logging
    flash_model = os.getenv("LLM_MODEL_FLASH", "deepseek-v4-flash")
    metadata = {
        'stage': 'speaker_extraction',
        'model': flash_model,
        'transcript_length': len(transcript),
        'timestamp': pd.Timestamp.utcnow().isoformat()
    }

    prompt_template = load_prompt("speaker_extraction.md")
    full_prompt = prompt_template.format(transcript=transcript)

    try:
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
# Module-level table formatters (also used inside analyze_transcript_text)
# ------------------------

def format_on_track_topics_table(items: List[Dict[str, str]]) -> str:
    if not items:
        return "| Topic | Related Sub-Module | Related Discovery Topic |\n| --- | --- | --- |\n| No on-track topics identified | - | - |"
    table = ["| Topic | Related Sub-Module | Related Discovery Topic |", "| --- | --- | --- |"]
    for item in items:
        topic = item.get("topic", "").replace("|", "\\|")
        sub   = item.get("related_submodule", "").replace("|", "\\|")
        disc  = item.get("related_discovery_topic", "").replace("|", "\\|")
        table.append(f"| {topic} | {sub} | {disc} |")
    return "\n".join(table)


def format_off_track_topics_table(items: List[Dict[str, str]]) -> str:
    if not items:
        return (
            "| Status | Topic | Related to SOW | Related to Discovery |\n"
            "| --- | --- | --- | --- |\n"
            "| ✅ | No off-track topics identified | - | - |"
        )
    table = [
        "| Status | Topic | Related to SOW | Related to Discovery |",
        "| --- | --- | --- | --- |",
    ]
    for item in items:
        topic  = str(item.get("topic", "")).replace("|", "\\|")
        sub    = str(item.get("related_submodule", "Not in SOW")).replace("|", "\\|")
        disc   = str(item.get("related_discovery_topic", "Not in Discovery")).replace("|", "\\|")
        status = "❌" if ("not in" in sub.lower() or "not in" in disc.lower()) else "⚠️"
        table.append(f"| {status} | {topic} | {sub} | {disc} |")
    return "\n".join(table)


# ------------------------
# Shared LLM JSON helper (used by both stream and non-stream paths)
# ------------------------

async def _call_llm_json(llm, prompt_text: str) -> Any:
    try:
        msg = await llm.ainvoke(prompt_text)
        content = getattr(msg, "content", "").strip()
        if not content:
            return None
        try:
            return json.loads(content)
        except Exception:
            pass
        cleaned = content
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("\n", 1)[0]
        cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except Exception:
            start = cleaned.find("{")
            end   = cleaned.rfind("}")
            if start != -1 and end > start:
                try:
                    return json.loads(cleaned[start:end + 1])
                except Exception:
                    pass
            return content
    except Exception as e:
        logging.error("[LLM-JSON] call failed: %s", e)
        return None


# ------------------------
# Core Analyzer — Full Streaming Version
# ------------------------

async def analyze_transcript_text_stream(
    transcript: str,
    speaker_tags: Dict[str, str],
    discovery_plan: Dict[str, Any],
    sow_text: str,
    prior_sessions: Optional[List[Dict[str, Any]]] = None,
    current_session_number: int = 1,
):
    """
    Fully-streaming transcript analysis.

    Yields {"status": "progress", "message": str, "step": int} for every meaningful
    AI event, then {"status": "complete", "analysis_result": dict} when done.

    Steps map:
      0 — setup / context prep
      1 — Minutes of Meeting (Actor-Critic loop)
      2 — On-track topics
      3 — Off-track topics
      4 — Open topics
      5 — Provisional requirements
      6 — Cross-meeting conflict detection
      (scope analysis and DB save happen in the API layer, step 7)
    """
    llm = init_llm()
    if not llm:
        yield {"status": "error", "message": "LLM unavailable — check DEEPSEEK_API_KEY"}
        return

    # ── Context prep ──
    yield {"status": "progress", "message": "🔧 Preparing analysis context…", "step": 0}

    transcript_block = transcript
    try:
        if isinstance(sow_text, str) and (sow_text.startswith('{') or sow_text.startswith('[')):
            sow_block = json.dumps(json.loads(sow_text), ensure_ascii=False, indent=2)
        else:
            sow_block = json.dumps({"sow_text": sow_text}, ensure_ascii=False, indent=2)
    except Exception:
        sow_block = json.dumps({"sow_text": str(sow_text)}, ensure_ascii=False, indent=2)

    if not isinstance(discovery_plan, (dict, list)):
        try:
            discovery_plan = json.loads(str(discovery_plan))
        except Exception:
            discovery_plan = {}

    discovery_block    = json.dumps(discovery_plan, ensure_ascii=False, indent=2)
    speaker_tags_block = json.dumps(speaker_tags,   ensure_ascii=False, indent=2)

    aggregated: Dict[str, Any] = {
        "mom": "",
        "on_track_topics": [],
        "off_track_topics": [],
        "provisional_user_stories": [],
        "open_topics": [],
        "conflicting_topics": [],
    }

    # ── 1. Minutes of Meeting — LangGraph Actor-Critic loop ──
    yield {"status": "progress", "message": "🤖 MoM Agent starting Actor-Critic review loop…", "step": 1}
    try:
        from .graph_workflows import mom_review_graph
        mom_initial = {
            "transcript": transcript_block,
            "speaker_tags_block": speaker_tags_block,
            "discovery_block": discovery_block,
            "sow_block": sow_block,
            "draft_mom": "",
            "review_status": "PENDING",
            "review_feedback": "",
            "review_cycle": 0,
        }
        async for event in mom_review_graph.astream(mom_initial, stream_mode="updates"):
            for node_name, output in event.items():
                if node_name == "generate":
                    cycle = output.get("review_cycle", 1)
                    yield {
                        "status": "progress",
                        "message": f"✍️ MoM Agent drafting Minutes of Meeting (Cycle {cycle})…",
                        "step": 1,
                    }
                elif node_name == "review":
                    rv_status   = output.get("review_status", "")
                    rv_feedback = output.get("review_feedback", "")
                    if rv_status == "REWORK":
                        snippet = (rv_feedback[:70] + "…") if len(rv_feedback) > 70 else rv_feedback
                        yield {
                            "status": "progress",
                            "message": f"🔍 MoM Reviewer requested changes — {snippet}",
                            "step": 1,
                        }
                    else:
                        yield {"status": "progress", "message": "✅ MoM Reviewer approved the draft!", "step": 1}

        final_mom = await mom_review_graph.ainvoke(mom_initial)
        aggregated["mom"] = sanitize_mom_html(final_mom.get("draft_mom", ""))
        cycles = final_mom.get("review_cycle", 1)
        yield {
            "status": "progress",
            "message": f"📋 Minutes of Meeting finalized ({cycles} review cycle{'s' if cycles > 1 else ''}).",
            "step": 1,
        }
    except Exception as e:
        logging.error("[STREAM] MoM failed: %s", e)
        yield {"status": "progress", "message": "⚠️ MoM generation hit an issue — using fallback.", "step": 1}
        try:
            fb_prompt = load_prompt("mom_generator.md").format(
                transcript_block=transcript_block, speaker_tags_block=speaker_tags_block,
                discovery_block=discovery_block, sow_block=sow_block,
            )
            msg = await llm.ainvoke(fb_prompt)
            aggregated["mom"] = sanitize_mom_html(getattr(msg, "content", ""))
        except Exception:
            pass

    # ── 2. On-track topics ──
    yield {"status": "progress", "message": "📊 Extracting on-track topics (aligned with SOW & discovery plan)…", "step": 2}
    try:
        on_prompt = load_prompt("on_track_topics.md").format(
            sow_block=sow_block, discovery_block=discovery_block, transcript_block=transcript_block
        )
        on_out = await _call_llm_json(llm, on_prompt)
        parsed = []
        if isinstance(on_out, dict):
            parsed = on_out.get("items", [])
        elif isinstance(on_out, str):
            try:
                parsed = json.loads(on_out).get("items", [])
            except Exception:
                parts  = [p.strip("- •\t ") for p in on_out.replace("\n", ",").split(",")]
                parsed = [{"topic": p, "related_submodule": "-", "related_discovery_topic": "-"} for p in parts if p]
        if isinstance(parsed, list):
            aggregated["on_track_topics"]       = parsed
            aggregated["on_track_topics_table"] = format_on_track_topics_table(parsed)
        n = len(aggregated["on_track_topics"])
        yield {"status": "progress", "message": f"✅ Found {n} on-track topic{'s' if n != 1 else ''}.", "step": 2}
    except Exception as e:
        logging.error("[STREAM] On-track topics failed: %s", e)
        aggregated["on_track_topics"]       = []
        aggregated["on_track_topics_table"] = format_on_track_topics_table([])
        yield {"status": "progress", "message": "⚠️ Could not extract on-track topics.", "step": 2}

    # ── 3. Off-track topics ──
    yield {"status": "progress", "message": "⚠️ Identifying off-track discussions (outside SOW scope)…", "step": 3}
    try:
        off_prompt = load_prompt("off_track_topics.md").format(
            sow_block=sow_block, discovery_block=discovery_block, transcript_block=transcript_block
        )
        off_out = await _call_llm_json(llm, off_prompt)
        parsed  = []
        if isinstance(off_out, dict):
            parsed = off_out.get("items", [])
        elif isinstance(off_out, str):
            try:
                parsed = json.loads(off_out).get("items", [])
            except Exception:
                parts  = [p.strip("- •\t ") for p in off_out.replace("\n", ",").split(",")]
                parsed = [{"topic": p, "related_submodule": "-", "related_discovery_topic": "-"} for p in parts if p]
        if isinstance(parsed, list):
            valid = [
                item for item in parsed
                if isinstance(item, dict) and item.get("topic", "").strip()
                and any(k in item for k in ["related_submodule", "related_discovery_topic", "impact", "recommendation"])
            ]
            aggregated["off_track_topics"]       = valid
            aggregated["off_track_topics_table"] = format_off_track_topics_table(valid)
        n = len(aggregated["off_track_topics"])
        yield {"status": "progress", "message": f"✅ Found {n} off-track discussion{'s' if n != 1 else ''}.", "step": 3}
    except Exception as e:
        logging.error("[STREAM] Off-track topics failed: %s", e)
        aggregated["off_track_topics"]       = []
        aggregated["off_track_topics_table"] = format_off_track_topics_table([])
        yield {"status": "progress", "message": "⚠️ Could not extract off-track topics.", "step": 3}

    # ── 4. Open topics ──
    yield {"status": "progress", "message": "❓ Extracting open-ended questions and unresolved topics…", "step": 4}
    try:
        open_prompt = load_prompt("open_topics.md").format(
            sow_block=sow_block, discovery_block=discovery_block, transcript_block=transcript_block
        )
        open_out = await _call_llm_json(llm, open_prompt)
        if isinstance(open_out, dict):
            aggregated["open_topics"] = [str(x) for x in open_out.get("items", [])]
        elif isinstance(open_out, str):
            parts = [p.strip("- •\t ") for p in open_out.replace("\n", ",").split(",")]
            aggregated["open_topics"] = [p for p in parts if p]
        n = len(aggregated["open_topics"])
        yield {"status": "progress", "message": f"✅ Found {n} open question{'s' if n != 1 else ''}.", "step": 4}
    except Exception as e:
        logging.error("[STREAM] Open topics failed: %s", e)
        aggregated["open_topics"] = []
        yield {"status": "progress", "message": "⚠️ Could not extract open topics.", "step": 4}

    # ── 5. Provisional requirements ──
    yield {"status": "progress", "message": "📝 Extracting provisional requirements from transcript…", "step": 5}
    try:
        stories_prompt = load_prompt("provisional_stories.md").format(
            sow_block=sow_block, discovery_block=discovery_block,
            speaker_tags_block=speaker_tags_block, transcript_block=transcript_block,
        )
        stories_out = await _call_llm_json(llm, stories_prompt)
        normalized: List[Dict[str, Any]] = []
        items_raw = []
        if isinstance(stories_out, dict):
            items_raw = stories_out.get("stories", [])
        elif isinstance(stories_out, str):
            try:
                cleaned = stories_out
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[-1]
                if cleaned.endswith("```"):
                    cleaned = cleaned.rsplit("\n", 1)[0]
                obj = json.loads(cleaned.strip())
                items_raw = obj.get("stories", []) if isinstance(obj, dict) else obj
            except Exception:
                for line in stories_out.splitlines():
                    val = line.strip("- •\t ")
                    if val:
                        items_raw.append(val)
        for item in items_raw:
            if isinstance(item, dict):
                normalized.append({
                    "text":               str(item.get("text", "")),
                    "module":             str(item.get("module", "General")),
                    "status":             "Provisional",
                    "scope_status":       "Pending",
                    "scope_justification": "",
                    "is_tentative":       bool(item.get("is_tentative", False)),
                })
            else:
                normalized.append({"text": str(item), "module": "General", "status": "Provisional",
                                    "scope_status": "Pending", "scope_justification": "", "is_tentative": False})
        aggregated["provisional_user_stories"] = normalized
        n          = len(normalized)
        n_tent     = sum(1 for r in normalized if r.get("is_tentative"))
        tent_note  = f" ({n_tent} tentative)" if n_tent else ""
        yield {"status": "progress", "message": f"✅ Extracted {n} requirement{'s' if n != 1 else ''}{tent_note}.", "step": 5}
    except Exception as e:
        logging.error("[STREAM] Provisional stories failed: %s", e)
        aggregated["provisional_user_stories"] = []
        yield {"status": "progress", "message": "⚠️ Could not extract requirements.", "step": 5}

    # ── 6. Cross-meeting conflict detection ──
    if prior_sessions:
        n_prior = len(prior_sessions)
        yield {
            "status": "progress",
            "message": f"⚡ Checking for contradictions across {n_prior} prior session{'s' if n_prior > 1 else ''}…",
            "step": 6,
        }
        try:
            sorted_prior = sorted(prior_sessions, key=lambda s: s.get("session_number", 0))
            prior_blocks = []
            for ps in sorted_prior:
                reqs      = ps.get("provisional_user_stories", [])
                req_texts = [f"  - [{r.get('module', 'General')}] {r.get('text', '')}" for r in reqs[:30]]
                prior_blocks.append(f"Session {ps.get('session_number', '?')}:\n" + "\n".join(req_texts))
            prior_sessions_block = "\n\n".join(prior_blocks)

            current_reqs      = aggregated.get("provisional_user_stories", [])
            current_req_texts = "\n".join(
                f"- [{r.get('module', 'General')}] {r.get('text', '')}" for r in current_reqs
            )
            conflict_prompt = load_prompt("conflicting_topics.md").format(
                prior_sessions_block=prior_sessions_block,
                current_requirements_block=current_req_texts,
                current_session_number=current_session_number,
            )
            conflict_out = await _call_llm_json(llm, conflict_prompt)
            if isinstance(conflict_out, dict):
                aggregated["conflicting_topics"] = conflict_out.get("items", [])
            n_c = len(aggregated["conflicting_topics"])
            if n_c:
                yield {"status": "progress", "message": f"⚡ Detected {n_c} conflict{'s' if n_c > 1 else ''} with prior sessions.", "step": 6}
            else:
                yield {"status": "progress", "message": "✅ No contradictions detected with prior sessions.", "step": 6}
        except Exception as e:
            logging.error("[STREAM] Conflict detection failed: %s", e)
            aggregated["conflicting_topics"] = []
            yield {"status": "progress", "message": "⚠️ Conflict detection hit an issue.", "step": 6}

    # ── Fallbacks ──
    if not aggregated["mom"]:
        aggregated["mom"] = (
            "<div class='mom-report' style='padding:16px;'>"
            "<h3 style='color:#ef4444;'>⚠️ Minutes of Meeting Unavailable</h3>"
            "<p>Check DEEPSEEK_API_KEY and retry.</p></div>"
        )

    yield {"status": "complete", "analysis_result": aggregated}

async def analyze_transcript_text(
    transcript: str,
    speaker_tags: Dict[str, str],
    discovery_plan: Dict[str, Any],
    sow_text: str,
    prior_sessions: Optional[List[Dict[str, Any]]] = None,
    current_session_number: int = 1,
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
                'model': os.getenv("LLM_MODEL_PRO", "deepseek-v4-pro"),
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
                'model': os.getenv("LLM_MODEL_PRO", "deepseek-v4-pro"),
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
        "open_topics": [],
        "conflicting_topics": [],
    }

    if llm:
        logging.info("[POST-MEETING] Starting LLM analysis with 5 specialized prompts...")
        
        # 1) MoM — via LangGraph review loop
        logging.info("[POST-MEETING] Processing MoM via LangGraph review loop...")
        try:
            from .graph_workflows import mom_review_graph
            mom_graph_result = await mom_review_graph.ainvoke({
                "transcript": transcript_block,
                "speaker_tags_block": speaker_tags_block,
                "discovery_block": discovery_block,
                "sow_block": sow_block,
                "draft_mom": "",
                "review_status": "PENDING",
                "review_feedback": "",
                "review_cycle": 0,
            })
            raw_mom = mom_graph_result.get("draft_mom", "")
            cycles_used = mom_graph_result.get("review_cycle", 1)
            review_verdict = mom_graph_result.get("review_status", "PASS")
            aggregated["mom"] = sanitize_mom_html(raw_mom)
            logging.info(
                "[POST-MEETING] MoM review loop done | cycles=%d verdict=%s length=%d",
                cycles_used, review_verdict, len(aggregated["mom"])
            )
        except Exception as e:
            logging.error(f"[POST-MEETING] MoM review loop failed: {e}")
            # Fallback: try single-shot generation without review
            try:
                mom_prompt_template = load_prompt("mom_generator.md")
                mom_prompt = mom_prompt_template.format(
                    transcript_block=transcript_block,
                    speaker_tags_block=speaker_tags_block,
                    discovery_block=discovery_block,
                    sow_block=sow_block
                )
                mom_raw = await call_llm_raw(mom_prompt, stage='mom')
                aggregated["mom"] = sanitize_mom_html(mom_raw)
            except Exception as e2:
                logging.error(f"[POST-MEETING] MoM fallback also failed: {e2}")

        # 2) On-track topics
        logging.info("[POST-MEETING] Processing on-track topics prompt...")
        on_track_prompt_template = load_prompt("on_track_topics.md")
        on_track_prompt = on_track_prompt_template.format(
            sow_block=sow_block,
            discovery_block=discovery_block,
            transcript_block=transcript_block
        )

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

        # -------------------
        # 3) Off-track topics
        # -------------------
        logging.info("[POST-MEETING] Processing off-track topics prompt...")

        off_track_prompt_template = load_prompt("off_track_topics.md")
        off_track_prompt = off_track_prompt_template.format(
            sow_block=sow_block,
            discovery_block=discovery_block,
            transcript_block=transcript_block
        )

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
        open_prompt_template = load_prompt("open_topics.md")
        open_prompt = open_prompt_template.format(
            sow_block=sow_block,
            discovery_block=discovery_block,
            transcript_block=transcript_block
        )
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
        stories_prompt_template = load_prompt("provisional_stories.md")
        stories_prompt = stories_prompt_template.format(
            sow_block=sow_block,
            discovery_block=discovery_block,
            speaker_tags_block=speaker_tags_block,
            transcript_block=transcript_block
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
                            "is_tentative": bool(item.get("is_tentative", False)),
                        })
                    else:
                        normalized.append({
                            "text": str(item),
                            "module": "General",
                            "status": "Provisional",
                            "scope_status": "Pending",
                            "scope_justification": "",
                            "is_tentative": False,
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
                                "is_tentative": bool(item.get("is_tentative", False)),
                            })
                        else:
                            added.append({
                                "text": str(item),
                                "module": "General",
                                "status": "Provisional",
                                "scope_status": "Pending",
                                "scope_justification": "",
                                "is_tentative": False,
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

        # 6) Conflicting topics — only when prior sessions exist
        if prior_sessions:
            logging.info("[POST-MEETING] Detecting cross-meeting conflicts (%d prior sessions)...", len(prior_sessions))
            try:
                # Build prior sessions summary (all sessions, oldest first)
                sorted_prior = sorted(prior_sessions, key=lambda s: s.get("session_number", 0))
                prior_blocks = []
                for ps in sorted_prior:
                    reqs = ps.get("provisional_user_stories", [])
                    req_texts = [
                        f"  - [{r.get('module', 'General')}] {r.get('text', '')}"
                        for r in reqs[:30]  # cap per-session to keep token cost manageable
                    ]
                    prior_blocks.append(
                        f"Session {ps.get('session_number', '?')}:\n" + "\n".join(req_texts)
                    )
                prior_sessions_block = "\n\n".join(prior_blocks)

                current_reqs = aggregated.get("provisional_user_stories", [])
                current_req_texts = "\n".join(
                    f"- [{r.get('module', 'General')}] {r.get('text', '')}"
                    for r in current_reqs
                )

                conflict_prompt_template = load_prompt("conflicting_topics.md")
                conflict_prompt = conflict_prompt_template.format(
                    prior_sessions_block=prior_sessions_block,
                    current_requirements_block=current_req_texts,
                    current_session_number=current_session_number,
                )

                conflict_out = await call_llm_json(conflict_prompt)
                if isinstance(conflict_out, dict):
                    aggregated["conflicting_topics"] = conflict_out.get("items", [])
                logging.info(
                    "[POST-MEETING] Conflicting topics: %d items",
                    len(aggregated["conflicting_topics"]),
                )
            except Exception as e:
                logging.error("[POST-MEETING] Conflict detection failed: %s", e)
                aggregated["conflicting_topics"] = []

    # Ensure all fields have data - deterministic, honest fallbacks
    if not aggregated["mom"]:
        # Keep fallback concise — use HTML so dangerouslySetInnerHTML renders correctly
        aggregated["mom"] = (
            "<div class='mom-report' style='padding:16px;'>"
            "<h3 style='color:#ef4444;'>⚠️ Minutes of Meeting Unavailable</h3>"
            "<p>The AI backend was unable to generate a meeting summary.</p>"
            "<ul><li>Please ensure <strong>DEEPSEEK_API_KEY</strong> is configured correctly.</li>"
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

    if not aggregated.get("conflicting_topics"):
        aggregated["conflicting_topics"] = []

    logging.info(
        "[POST-MEETING] Final result: mom=%d chars, on_track=%d, off_track=%d, open=%d, stories=%d, conflicts=%d",
        len(aggregated["mom"]),
        len(aggregated["on_track_topics"]),
        len(aggregated["off_track_topics"]),
        len(aggregated["open_topics"]),
        len(aggregated["provisional_user_stories"]),
        len(aggregated["conflicting_topics"]),
    )
    return aggregated