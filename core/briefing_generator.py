import os
import json
import logging
import re
from typing import List, Dict, Any, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
import docx
import pypdf
import pandas as pd
from io import BytesIO
from dotenv import load_dotenv

# Import the LLM logger
from .llm_logger import log_llm_response

# Load environment variables from a local .env file if present
load_dotenv()

# Configure basic logging once
logging.basicConfig(level=logging.INFO)

# --- Helper Function to Extract Text from Files ---
def extract_text_from_file(file_content: bytes, file_name: str) -> str:
    """Extracts text from PDF/DOCX or JSON string from XLSX/XLS files."""
    text = ""
    try:
        if file_name.lower().endswith(".pdf"):
            # Read PDF from in-memory bytes
            pdf_reader = pypdf.PdfReader(BytesIO(file_content))
            for page in pdf_reader.pages:
                text += page.extract_text() or ""
        elif file_name.lower().endswith(".docx"):
            # Read DOCX from in-memory bytes
            doc = docx.Document(BytesIO(file_content))
            for para in doc.paragraphs:
                text += para.text + "\n"
        elif file_name.lower().endswith(".xlsx") or file_name.lower().endswith(".xls"):
            # Read Excel and convert to JSON (records per sheet)
            excel_file = BytesIO(file_content)
            sheets: Dict[str, pd.DataFrame] = pd.read_excel(excel_file, sheet_name=None)
            json_payload: Dict[str, List[Dict]] = {}
            for sheet_name, df in sheets.items():
                # Replace NaNs for cleaner JSON and limit extreme sizes if necessary
                cleaned_df = df.fillna("")
                # Convert to list of records
                json_payload[sheet_name] = cleaned_df.to_dict(orient="records")
            text = json.dumps({"type": "excel", "sheets": json_payload}, ensure_ascii=False)
    except Exception as e:
        return f"Error reading {file_name}: {e}"
    return text


# --- Main Generator Function ---
async def generate_intelligence_brief(
    client_name: str,
    industry: str,
    ba_input: str,
    presales_doc_content: bytes,
    presales_doc_name: str,
    additional_docs: List[Dict[str, Any]]
) -> str:
    """
    Generates the Pre-Meeting Intelligence Brief using Google's Gemini model.
    """
    # Tunables via env
    max_output_tokens_env = os.getenv("LLM_MAX_OUTPUT_TOKENS", "8192")
    # Guard against absurd values or non-ints
    try:
        max_output_tokens = max(1024, int(max_output_tokens_env))
    except Exception:
        max_output_tokens = 8192

    # Limit total characters fed into the model to reduce context overflow
    # You can raise this via LLM_MAX_INPUT_CHARS if your model/context allows more
    max_input_chars_env = os.getenv("LLM_MAX_INPUT_CHARS", "180000")
    try:
        max_input_chars = max(20000, int(max_input_chars_env))
    except Exception:
        max_input_chars = 180000

    # 1) Initialize LLM if API key available
    api_key = os.getenv("GOOGLE_API_KEY")
    llm = None
    logging.info("[CORE] Starting brief generation for client='%s' industry='%s'", client_name, industry)
    if api_key:
        # Select stable default model; allow override via env LLM_MODEL
        model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")
        try:
            llm = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=api_key,
                temperature=0.7,
                max_output_tokens=max_output_tokens,
            )
            logging.info("[CORE] LLM initialized | model='%s'", model_name)
        except Exception as init_err:
            logging.error("[CORE] Failed to initialize LLM: %s", init_err)
            llm = None
    else:
        logging.warning("[CORE] GOOGLE_API_KEY not found; using fallback brief.")

    # 2) Extract text/JSON from all documents
    presales_text = extract_text_from_file(presales_doc_content, presales_doc_name)
    logging.info("[CORE] Extracted presales text | name='%s' size=%d chars", presales_doc_name, len(presales_text))

    additional_docs_text = ""
    for doc in additional_docs:
        content = await doc['file'].read()
        text = extract_text_from_file(content, doc['file'].filename)
        additional_docs_text += f"\n--- Content from {doc['file'].filename} ---\n"
        additional_docs_text += f"(BA's explanation: {doc['explanation']})\n"
        additional_docs_text += text
        additional_docs_text += "\n--- End of Content ---\n"
        logging.info("[CORE] Extracted additional doc | name='%s' size=%d chars", doc['file'].filename, len(text))

    # 3) Trim inputs defensively to avoid context overflow
    def _trim(text: str, limit: int, label: str) -> str:
        return text or ""

    # Reserve budget for system instructions; allocate roughly 70% to documents
    docs_budget = int(max_input_chars * 0.7)
    per_section_budget = max(20000, docs_budget // 2)
    presales_text = _trim(presales_text, per_section_budget, "Presales Document")
    additional_docs_text = _trim(additional_docs_text, per_section_budget, "Additional Documents")

    # 4) Build prompt for sections 1-4 only (discovery generated separately)
    prompt = f"""
    You are a senior Business Analyst assistant. Create a concise, actionable pre-meeting intelligence brief.

    Inputs:
    - Client Name: {client_name}
    - Industry: {industry}
    - BA Focus: {ba_input}
    - Presales Document ({presales_doc_name}):
    {presales_text}
    - Additional Documents:
    {additional_docs_text}

    Output strictly these sections and nothing else:
    1. Executive Summary
    2. Company & Industry Analysis
    3. Project Scope & Key Objectives (from documents)
    4. Potential Risks & Ambiguities

    Rules:
    - Do NOT include any discovery questions or any heading for discovery questions.
    - Do NOT add any additional sections or trailing notes.
    - Keep content concise and professional.
    """

    # 5) Generate with LLM or return deterministic fallback
    if llm is not None:
        try:
            # Optional batched discovery generation to prevent truncation for many sub-modules
            batched_mode = os.getenv("ENABLE_BATCHED_DISCOVERY", "1") != "0"

            async def call_llm(text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
                # Log the prompt being sent to the LLM
                metadata = metadata or {}
                metadata.update({
                    'client': client_name,
                    'industry': industry,
                    'model': model_name,
                    'timestamp': pd.Timestamp.utcnow().isoformat()
                })
                
                # Call the LLM
                ai_message_local = await llm.ainvoke(text)
                response_content = getattr(ai_message_local, "content", "") or ""
                
                # Log the response
                log_llm_response(
                    prompt=text,
                    response=response_content,
                    metadata=metadata
                )
                
                return response_content

            if not batched_mode:
                logging.info("[CORE] Invoking LLM in single-shot mode...")
                content_single = await call_llm(prompt)
                logging.info("[CORE] LLM returned content | length=%d", len(content_single))
                return content_single
            else:
                # a) Generate sections 1-4 in the first call to leave room for later content
                logging.info("[CORE] Generating sections 1-4 (overview-only, no discovery)...")
                metadata = {
                    'stage': 'overview_generation',
                    'model': model_name,
                    'client': client_name,
                    'industry': industry
                }
                overview_prompt = f"""
                You are a senior Business Analyst assistant. Create ONLY sections 1 to 4 of the pre-meeting intelligence brief.

                Inputs:
                - Client Name: {client_name}
                - Industry: {industry}
                - BA Focus: {ba_input}
                - Presales Document ({presales_doc_name}):
                {presales_text}
                - Additional Documents:
                {additional_docs_text}

                Output strictly these sections and nothing else. FORMATTING RULES:
                - Each section must start on its own line with exactly two newlines before it
                - Section headings must be at the start of a line with no leading spaces
                - Section headings must be in bold and end with a colon
                - Section content must start on a new line after the heading
                - Do not include any additional text before, between, or after the sections

                **1. Executive Summary:**
                [Brief overview of the client, project, and key points]

                **2. Company & Industry Analysis:**
                [Analysis of the client's business and industry context]

                **3. Project Scope & Key Objectives:**
                [Detailed scope and objectives from the provided documents]

                **4. Potential Risks & Ambiguities:**
                [Key risks and uncertainties identified]
                """
                # First, get the overview content
                overview = await call_llm(overview_prompt, metadata=metadata)
                
                # Then create a prompt to enumerate submodules
                enumerate_prompt = f"""
                You are extracting structure from documents. From the following materials, list ALL distinct business sub-modules referenced in pre-sales scope.
                Exclude generic technology/data terms (e.g., JSON, CSV, XML, list, array, object, string, number), placeholders, or punctuation-only tokens.
                Return ONLY a JSON array of strings with sub-module names, no commentary.

                Client: {client_name}
                Industry: {industry}
                BA Focus: {ba_input}
                Presales Document ({presales_doc_name}):
                {presales_text}

                Additional Documents:
                {additional_docs_text}
                """
                # Get submodules with metadata
                submodules_metadata = metadata.copy()
                submodules_metadata['stage'] = 'submodule_enumeration'
                submodules_json_text = await call_llm(enumerate_prompt, metadata=submodules_metadata)
                submodules: List[str] = []
                try:
                    submodules = json.loads(submodules_json_text)
                    if not isinstance(submodules, list):
                        submodules = []
                except Exception:
                    # Simple fallback: split lines and strip bullets/numbering
                    for line in submodules_json_text.splitlines():
                        candidate = line.strip().lstrip("-*").lstrip().split(" ", 1)
                        name = line.strip().lstrip("-*").strip()
                        if name:
                            submodules.append(name)

                # Clean names (strip quotes/backticks/extra spaces) and deduplicate while preserving order
                seen = set()
                unique_submodules: List[str] = []
                def _clean_name(name: str) -> str:
                    s = (name or "").strip()
                    # Remove common bullet/numbering prefixes like "1.", "(1)", "-", "*"
                    s = re.sub(r"^\s*\(?\d+\)?[\.)-]\s*", "", s)
                    s = s.lstrip("-*").strip()
                    # Strip surrounding quotes/backticks/brackets/braces/parentheses
                    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")) or (s.startswith("`") and s.endswith("`")):
                        s = s[1:-1].strip()
                    s = s.strip("[]{}()")
                    # Remove stray quotes/backticks and trailing punctuation like commas/semicolons
                    s = s.replace('"', '').replace("`", "")
                    s = re.sub(r"[\s]*[,;:]+$", "", s)
                    # Collapse repeated whitespace
                    s = " ".join(s.split())
                    return s

                denylist = {"json","csv","xml","yaml","yml","list","lists","array","arrays","map","object","objects","record","records","string","number","integer","boolean","true","false","null"}
                for m in submodules:
                    if isinstance(m, str):
                        key = _clean_name(m)
                        kl = key.lower()
                        # Filter out obvious junk and generic technical tokens
                        if len(key) < 3:
                            continue
                        if kl in denylist:
                            continue
                        if key in {"[", "]"}:
                            continue
                        if kl not in seen:
                            unique_submodules.append(key)
                            seen.add(kl)

                # If still empty, fallback to single-shot generation
                if not unique_submodules:
                    logging.warning("[CORE] Could not enumerate sub-modules reliably, falling back to single-shot.")
                    content_single_fallback = await call_llm(prompt)
                    if content_single_fallback.strip():
                        return content_single_fallback

                # c) Generate questions in batches to avoid token/output truncation
                batch_size_env = os.getenv("DISCOVERY_BATCH_SIZE", "8")
                try:
                    batch_size = max(3, int(batch_size_env))
                except Exception:
                    batch_size = 8

                discovery_parts: List[str] = []
                total = len(unique_submodules)
                # logging.info("[CORE] Generating discovery questions for %d sub-modules in batches of %d...", total, batch_size)
                # for start in range(0, total, batch_size):
                #     batch = unique_submodules[start:start + batch_size]
                #     start_index = start + 1
                #     # Provide pre-numbered headings to enforce consistent, continuous numbering across batches
                #     numbered_headings = "\n".join([f"({i}) {name}" for i, name in enumerate(batch, start=start_index)])
                #     batch_prompt = f"""
                #     Create discovery questions for the following sub-modules. For EACH item, copy the provided numbering and text EXACTLY into the heading.
                #     - Heading format: **({{n}}) {{Sub-Module Name}}** (bold, no quotes/backticks, no leading space after **)
                #     - After each heading, render a two-column markdown table with headers 'S.No.' and 'Discovery Question'.
                #     - Add 3-4 high-quality, open-ended questions per sub-module. Each question must be a new row.
                #     - Cover every sub-module; avoid simple yes/no questions.
                #     - Do not include any other prose outside the headings and tables.
                #     - Do NOT wrap output in code fences and do not indent the entire content; start headings at column 0.

                logging.info("[CORE] Generating discovery questions for %d sub-modules (per-module tables)...", total)
                for idx, name in enumerate(unique_submodules, start=1):
                    # Prepare metadata for this submodule
                    submodule_metadata = metadata.copy()
                    submodule_metadata.update({
                        'stage': 'discovery_questions',
                        'submodule_index': idx,
                        'submodule_name': name,
                        'total_submodules': total
                    })
                    table_prompt = f"""
                    For the sub-module below, output ONLY a two-column markdown table with headers 'S.No.' and 'Discovery Question'.
                    - Include exactly 4 rows of insightful, open-ended discovery questions focused on process, data, edge cases, and business impact.
                    - Do NOT include any heading, numbering, bullets, quotes/backticks, or extra prose before or after the table.
                    - Do NOT wrap the output in code fences (```). Start the table at column 0.

                    Sub-module: {name}
                    """
                    table_md = await call_llm(table_prompt, metadata=submodule_metadata)
                    heading = f"**({idx}) {name}**"
                    discovery_parts.append(f"{heading}\n\n{table_md.strip()}" )

                discovery_combined = "\n\n".join(discovery_parts)

                # d) Stitch the final brief
                final_markdown = f"{overview}\n\n**5. Suggested Discovery Questions**\n\n{discovery_combined}"
                logging.info("[CORE] Batched generation complete | overview=%d chars discovery=%d chars", len(overview), len(discovery_combined))
                return final_markdown

        except Exception as e:
            logging.error("[CORE] LLM generation failed: %s", e)
            return f"AI Generation Failed: {str(e)}"

    # If llm is None, it means the API key was missing or initialization failed
    if api_key:
        return "AI Initialization Failed: Check your GOOGLE_API_KEY and model settings in the .env file."
    else:
        return "GOOGLE_API_KEY missing: Please add your Gemini API key to the .env file in the root directory."