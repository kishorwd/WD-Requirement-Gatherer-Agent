import streamlit as st
import pandas as pd
import json
import requests
from io import BytesIO
import re
from docx import Document  # python-docx must be installed

# ------------------------
# Page Config
# ------------------------
st.set_page_config(layout="wide", page_icon="📝", page_title="Post-Meeting Analysis")
st.title("🔍 Post-Meeting Analysis")

# --- FIX START: Define separate API bases for clarity and correctness ---
# General project routes (list, create) are under /api/v1/
PROJECT_API_BASE = "http://localhost:8000/api/v1" 
# Meeting specific routes (analyze, upload-plan, sessions) are under /api/v1/meetings
MEETING_API_BASE = "http://localhost:8000/api/v1/meetings" 
# --- FIX END ---

# ------------------------
# 1. Fetch Projects from backend
# ------------------------
st.subheader("1. Select Project")
try:
    # Use the correct PROJECT_API_BASE for listing projects
    projects_resp = requests.get(f"{PROJECT_API_BASE}/projects") 
    projects_resp.raise_for_status()
    projects = projects_resp.json()
    project_map = {p["client_name"]: p["id"] for p in projects}
    project_names = list(project_map.keys())
except Exception as e:
    st.error(f"Unable to fetch projects: {e}")
    # fallback
    project_map = {}
    project_names = []

selected_project_name = st.selectbox("Choose active project", project_names)
selected_project_id = project_map.get(selected_project_name)

# ------------------------
# 2. Discovery Plan Upload
# ------------------------
st.subheader("2. Upload Discovery Plan (CSV / Excel)")
discovery_file = st.file_uploader("Upload Discovery Plan (CSV/Excel)", type=["csv", "xlsx"])
if discovery_file:
    try:
        if discovery_file.name.endswith(".csv"):
            df_plan = pd.read_csv(discovery_file)
        else:
            df_plan = pd.read_excel(discovery_file)
            
        # Reset the index to start from 1 and keep it as a column
        df_plan = df_plan.reset_index(drop=True)
        df_plan.index = df_plan.index + 1
        
        # Add minimal CSS for table borders with rounded corners
        st.markdown("""
        <style>
        /* Main table container */
        div[data-testid='stDataFrame'] {
            border: 1px solid black !important;
            border-radius: 8px !important;
            overflow: hidden !important;
        }
        
        /* Table element */
        .stDataFrame table {
            border-collapse: separate !important;
            border-spacing: 0 !important;
            width: 100% !important;
        }
        
        /* Table cells */
        .stDataFrame th, .stDataFrame td {
            border: 1px solid black !important;
            padding: 4px 8px !important;
        }
        
        /* Rounded corners for the first and last cells in the first row */
        .stDataFrame thead tr:first-child th:first-child {
            border-top-left-radius: 7px !important;
        }
        .stDataFrame thead tr:first-child th:last-child {
            border-top-right-radius: 7px !important;
        }
        
        /* Rounded corners for the first and last cells in the last row */
        .stDataFrame tbody tr:last-child td:first-child {
            border-bottom-left-radius: 7px !important;
        }
        .stDataFrame tbody tr:last-child td:last-child {
            border-bottom-right-radius: 7px !important;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Display the dataframe with minimal styling
        st.dataframe(
            df_plan,
            width='stretch',
            hide_index=False
        )
        if st.button("Upload Discovery Plan to Backend"):
            if not selected_project_id:
                st.error("Please select a project in Section 1 before uploading the discovery plan.")
            else:
                files = {"file": (discovery_file.name, discovery_file.getvalue())}
                # Use MEETING_API_BASE for meeting-related uploads
                resp = requests.post(f"{MEETING_API_BASE}/project/{selected_project_id}/upload-plan", files=files) 
                if resp.status_code == 200:
                    st.success("✅ Discovery Plan uploaded to server.")
                    st.session_state["discovery_uploaded"] = True
                    st.session_state["discovery_uploaded_project_id"] = selected_project_id
                else:
                    st.error(f"Upload failed: {resp.text}")
    except Exception as e:
        st.error(f"Error reading file: {e}")

# ------------------------
# 3. Session Analysis Section
# ------------------------
st.subheader("3. Analyze Session")

session_number = st.number_input("Session Number", min_value=1, step=1)
transcript_file = st.file_uploader("Upload Transcript (.txt or .docx)", type=["txt", "docx"])

speaker_tags = {}

def extract_names_from_transcript(transcript_text):
    """
    Deprecated local heuristic. Keeping for fallback only.
    """
    # Capture up to 3 consecutive capitalized words as a single name
    name_pattern = re.compile(r'\b([A-Z][a-z]+(?:\s[A-Z][a-z]+){0,2})\b')
    matches = name_pattern.findall(transcript_text)
    names = set()
    for word in matches:
        if word.isupper() or any(c.isdigit() for c in word):
            continue
        names.add(word)
    return list(names)

# Keep only plausible human names: 1-3 words, letters with optional '-' or '\''
STOPWORDS = {
    "json","speaker","speakers","name","names","output","item","items","list",
    "topic","topics","open","on","off","track","schema","transcript","sow",
    "discovery","plan","role","client","developer","ba","other","minutes","meeting"
}

def normalize_speaker_names(items):
    pattern = re.compile(r"^[A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+){0,2}$")
    cleaned = []
    seen = set()
    for s in items or []:
        if not isinstance(s, str):
            continue
        # remove JSON/markdown artifacts and compress spaces
        s2 = re.sub(r"[^A-Za-z'\-\s]", " ", s)
        s2 = re.sub(r"\s+", " ", s2).strip()
        if not s2 or s2.lower() in STOPWORDS:
            continue
        # Title-case words for matching consistency
        s2 = " ".join(w[:1].upper() + w[1:] for w in s2.split())
        if pattern.fullmatch(s2) and s2.lower() not in STOPWORDS and s2 not in seen:
            seen.add(s2)
            cleaned.append(s2)
    return cleaned

# Parse possible JSON MoM or wrap plaintext into a structured dict
def _maybe_parse_json_mom(mom_text: str) -> dict:
    try:
        obj = json.loads(mom_text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return {
        "date": "",
        "agenda": "",
        "attendees": [],
        "organizer": "",
        "key": (mom_text or "").strip(),
        "action_items": []
    }

# Format MoM in the requested layout using bold labels and bullet items
def _format_mom_display(m: dict, speaker_tags: dict) -> str:
    attendees_list = list(speaker_tags.keys()) if speaker_tags else (m.get("attendees") or [])
    attendees_str = ", ".join([str(a).strip() for a in attendees_list if str(a).strip()])
    def _s(v):
        return str(v or "").strip()
    lines = []
    lines.append(f"**Date**: {_s(m.get('date'))}")
    lines.append(f"**Agenda**: {_s(m.get('agenda'))}")
    lines.append(f"**Attendees**: {attendees_str}")
    lines.append(f"**Organizer**: {_s(m.get('organizer'))}")
    lines.append("**Key**:")
    key_text = _s(m.get('key'))
    if key_text:
        lines.append(key_text)
    lines.append("**Action Items:**")
    for it in (m.get("action_items") or []):
        s = _s(it)
        if not s:
            continue
        if not s.startswith("-"):
            s = f"- {s}"
        lines.append(s)
    return "\n".join(lines)

# Read uploaded transcript as plain text, supporting .txt and .docx
def _read_uploaded_text(uploaded_file) -> str:
    if uploaded_file is None:
        return ""
    name = (uploaded_file.name or "").lower()
    data = uploaded_file.getvalue()

    # .docx handling
    if name.endswith(".docx"):
        try:
            doc = Document(BytesIO(data))
            parts = []
            for p in doc.paragraphs:
                if p.text:
                    parts.append(p.text)
            # include simple table text as lines
            for t in getattr(doc, "tables", []):
                for row in t.rows:
                    parts.append("\t".join(cell.text for cell in row.cells))
            return "\n".join(parts)
        except Exception as e:
            st.error(f"Failed to read .docx: {e}")
            return ""

    # default: treat as text
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return ""

if transcript_file:
    transcript_text = _read_uploaded_text(transcript_file)
    # Add CSS for transcript preview styling
    st.markdown("""
    <style>
    /* Style for the transcript preview container */
    div[data-testid='stTextArea'] > div {
        border: 1px solid black !important;
        border-radius: 8px !important;
        padding: 10px !important;
    }
    /* Style for the textarea itself */
    .stTextArea textarea {
        border: none !important;
        box-shadow: none !important;
    }
    /* Style for the label */
    .stTextArea label {
        font-weight: 600 !important;
        padding: 4px 0 !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Show full document (scrollable) with styling
    st.text_area("Transcript Preview", transcript_text, height=400, key="transcript_preview")

    # Prefer LLM-based extraction via backend; fallback to local heuristic
    possible_speakers = []
    try:
        # If a .docx is uploaded, convert to text locally and send as .txt to backend
        if transcript_file.name.lower().endswith(".docx"):
            txt_bytes = transcript_text.encode("utf-8")
            txt_name = transcript_file.name.rsplit(".", 1)[0] + ".txt"
            files = {"transcript_file": (txt_name, txt_bytes, "text/plain")}
        else:
            files = {"transcript_file": (transcript_file.name, transcript_file.getvalue(), "text/plain")}
        resp = requests.post(f"{MEETING_API_BASE}/extract-speakers", files=files, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            possible_speakers = normalize_speaker_names(data.get("speakers", []))
    except Exception:
        pass
    # Do NOT attempt local heuristic fallback; in fallback mode we intentionally
    # do not auto-generate speakers from the transcript.

    if possible_speakers:
        st.markdown("### Tag Speakers")

        for name in possible_speakers:
            # Checkbox: unchecked by default
            include_speaker = st.checkbox(f"Include {name}?", value=False, key=f"chk_{name}")
            
            # Show role dropdown only if checkbox is selected
            if include_speaker:
                role = st.selectbox(
                    f"Role for {name}", ["Client", "BA", "TS", "SA", "Other"], key=f"role_{name}"
                )
                speaker_tags[name] = role
            else:
                if name in speaker_tags:
                    del speaker_tags[name]
    else:
        st.info("No speakers automatically detected. You can still proceed.")

# ---- Validation for required inputs before enabling Analyze ----
project_ready = bool(selected_project_id)
# Analyze enabled ONLY if discovery plan has been uploaded to backend for
# the currently selected project (i.e., button was clicked successfully).
discovery_ready = (
    bool(st.session_state.get("discovery_uploaded"))
    and st.session_state.get("discovery_uploaded_project_id") == selected_project_id
)
transcript_ready = bool(transcript_file)
session_ready = bool(session_number and session_number >= 1)

can_analyze = project_ready and discovery_ready and transcript_ready and session_ready
analyze_clicked = st.button("🚀 Analyze Session", disabled=not can_analyze)
if analyze_clicked:
    with st.spinner("Analyzing transcript..."):
        try:
            # Convert .docx to text locally for compatibility with existing backend
            if transcript_file.name.lower().endswith(".docx"):
                txt_bytes = transcript_text.encode("utf-8")
                txt_name = transcript_file.name.rsplit(".", 1)[0] + ".txt"
                files = {"transcript_file": (txt_name, txt_bytes, "text/plain")}
            else:
                files = {"transcript_file": (transcript_file.name, transcript_file.getvalue(), "text/plain")}
            data = {
                "project_id": str(selected_project_id),
                "session_number": str(session_number),
                "speaker_tags_json": json.dumps(speaker_tags),
            }
            response = requests.post(
                f"{MEETING_API_BASE}/analyze-transcript", data=data, files=files, timeout=300
            )
            if response.status_code == 200:
                result = response.json()
                st.session_state["analysis_result"] = result.get("analysis_result", result)
                st.session_state["session_id"] = result.get("session_id")
                st.success("✅ Analysis complete.")
            else:
                st.error(f"Backend error: {response.status_code} — {response.text}")
        except Exception as e:
            st.error(f"Request failed: {e}")

# ------------------------
# 4. Display Results Section (MoM with selected attendees)
# ------------------------
if "analysis_result" in st.session_state:
    result = st.session_state["analysis_result"]

    st.subheader("4. Analysis Dashboard")
    tab1, tab2, tab3, tab4 = st.tabs(
        ["📋 Meeting Summary", "💬 Conversation Analysis", "📝 New Requirements", "📜 Project History"]
    )

    # ------------------------
    # Tab 1: Minutes of Meeting (MoM)
    # ------------------------
    with tab1:
        # --- Attendees with Roles ---
        if speaker_tags:
            attendees_list = ", ".join([f"{name} ({role})" for name, role in speaker_tags.items()])
            st.markdown(f"### Minutes of Meeting\n**Attendees:** {attendees_list}\n")
        else:
            st.markdown("### Minutes of Meeting\nNo attendees selected.\n")

        # --- MoM Content (from LLM JSON) ---
        mom_text = result.get("mom", "")
        # remove boilerplate like "Okay, I'm ready..."
        mom_text = re.sub(r"^Okay.*?(?=\n)", "", mom_text, flags=re.IGNORECASE | re.DOTALL).strip()
        fallback_flag = "AI backend unavailable or failed to generate summary." in mom_text
        if fallback_flag:
            st.error("AI backend unavailable or failed to generate summary. Please configure GOOGLE_API_KEY and retry.")
        else:
            if mom_text:
                st.markdown(mom_text)
                # Download the exact MoM text rendered above
                st.download_button(
                    label="⬇️ Download MoM (.txt)",
                    data=mom_text,
                    file_name="mom.txt",
                    mime="text/plain",
                    key="download_mom_txt",
                )
            else:
                st.error("No Minutes of Meeting generated.")

    # ------------------------
    # Tab 2: Conversation Analysis
    # ------------------------
    with tab2:
        st.markdown("### Conversation Analysis")

        st.markdown("**On-Track Topics**")
        on_track = result.get("on_track_topics", [])
        on_track_table = result.get("on_track_topics_table", "")
        mom_text_ca = result.get("mom", "")
        fallback_flag_ca = "AI backend unavailable or failed to generate summary." in mom_text_ca

        # Prefer Markdown table if available
        if on_track_table and "|" in on_track_table:
            st.markdown(on_track_table, unsafe_allow_html=True)
        elif on_track:
            # fallback: bullet points if only list is available
            st.markdown("\n".join([f"- {item}" for item in on_track]))
        else:
            if fallback_flag_ca:
                st.error("No on-track topics generated.")
            else:
                st.write("No on-track topics identified.")

        # ------------------------
        # Off-Track Topics
        # ------------------------
        st.markdown("**Off-Track Topics**")
        
        # Safely get and process off-track topics
        try:
            off_track = result.get("off_track_topics", [])
            off_track_table = result.get("off_track_topics_table", "")
            
            # Ensure we have a list of strings
            if off_track and isinstance(off_track, list):
                off_track = [str(item) if not isinstance(item, (str, int, float, bool)) else item 
                            for item in off_track]
            else:
                off_track = []
            
            # Display the table if available and properly formatted
            if off_track_table and isinstance(off_track_table, str) and "|" in off_track_table:
                st.markdown(off_track_table, unsafe_allow_html=True)
            # Fallback to list display if table isn't available
            elif off_track:
                st.markdown("\n".join([f"- {item}" for item in off_track]))
            else:
                if fallback_flag_ca:
                    st.error("No off-track topics generated.")
                else:
                    st.write("No off-track topics identified.")
                    
        except Exception as e:
            st.error(f"Error displaying off-track topics: {str(e)}")
            if 'off_track' in locals():
                st.json(off_track)  # Debug: Show the raw data if available

        st.markdown("**Open-Ended Topics**")
        try:
            open_topics = result.get("open_topics", [])
            # Ensure we have a list of strings
            if open_topics and isinstance(open_topics, list):
                open_topics = [str(item) if not isinstance(item, (str, int, float, bool)) else item 
                             for item in open_topics]
                st.markdown("\n".join([f"- {item}" for item in open_topics]))
            else:
                if fallback_flag_ca:
                    st.error("No open-ended topics generated.")
                else:
                    st.write("No open-ended topics identified.")
        except Exception as e:
            st.error(f"Error displaying open-ended topics: {str(e)}")
            if 'open_topics' in locals():
                st.json(open_topics)  # Debug: Show the raw data if available

    # ------------------------
    # Tab 3: New Requirements
    # ------------------------
    with tab3:
        st.markdown("### Provisional User Stories")

        # Initialize session state if not exists
        if 'provisional_data' not in st.session_state:
            st.session_state.provisional_data = result.get("provisional_user_stories", []).copy()
            st.session_state.last_updated = {}
            # Store original LLM values for each requirement
            st.session_state.original_values = {
                idx: {
                    'scope_status': req.get('scope_status', ''),
                    'scope_justification': req.get('scope_justification', '')
                }
                for idx, req in enumerate(st.session_state.provisional_data)
            }

        provisional = st.session_state.provisional_data

        if provisional:
            # Add filter dropdown
            filter_choice = st.selectbox(
                "Filter by Scope Status:",
                ["All", "In Scope", "Out of Scope", "Needs Clarification"],
                index=0
            )

            # Apply filter
            filtered_data = [req for req in provisional 
                          if filter_choice == "All" or req.get("scope_status") == filter_choice]
            
            # Create a copy for editing
            df = pd.DataFrame(filtered_data)
            
            # Check if we need to update any statuses
            if 'last_updated' in st.session_state and st.session_state.last_updated:
                for idx, update in st.session_state.last_updated.items():
                    if idx < len(provisional):
                        provisional[idx].update(update)
                st.session_state.last_updated = {}
                st.rerun()
            
            # Define editable columns
            editable_cols = {
                'status': st.column_config.SelectboxColumn(
                    'Status',
                    options=["Provisional", "Confirmed", "Rejected"],
                    required=True,
                    width="small"
                )
            }
            
            # Create a display-friendly copy of the dataframe
            display_df = df.copy()
            
            # Convert all columns to strings to ensure Arrow compatibility
            for col in display_df.columns:
                # Handle nested structures by converting to JSON strings
                if display_df[col].apply(lambda x: isinstance(x, (dict, list))).any():
                    display_df[col] = display_df[col].apply(
                        lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else str(x)
                    )
                else:
                    display_df[col] = display_df[col].astype(str)
            
            # Reset index and add 1 to start from 1 instead of 0
            display_df = display_df.reset_index(drop=True)
            display_df.index = display_df.index + 1
            
            # Store the current state for comparison
            if 'df_previous' not in st.session_state:
                st.session_state.df_previous = display_df.copy()
            
            # Add CSS to ensure table controls are visible
            st.markdown("""
            <style>
            div[data-testid="stDataFrame"] {
                overflow: visible !important;
            }
            </style>
            """, unsafe_allow_html=True)
            
            # Display the styled dataframe with index as S.No.
            try:
                # Get the column configuration
                column_config = {
                    "text": st.column_config.TextColumn(
                        "Requirement",
                        disabled=True
                    ),
                    "module": st.column_config.TextColumn(
                        "Module",
                        disabled=True
                    ),
                    "status": st.column_config.SelectboxColumn(
                        "Status",
                        options=["Provisional", "Confirmed", "Rejected"],
                        required=True,
                        width="small"
                    ),
                    "scope_status": st.column_config.TextColumn(
                        "Scope Status",
                        disabled=True
                    ),
                    "scope_justification": st.column_config.TextColumn(
                        "Justification",
                        disabled=True
                    )
                }
                
                # Add any additional columns that might be present
                for col in display_df.columns:
                    if col not in column_config and col != 'index':
                        column_config[col] = st.column_config.TextColumn(
                            col.replace('_', ' ').title(),
                            disabled=True
                        )
                
                # Display the data editor
                edited_df = st.data_editor(
                    display_df,
                    column_config=column_config,
                    width='stretch',
                    hide_index=False,
                    key="provisional_editor"
                )
                
            except Exception as e:
                st.error(f"Error displaying the table: {str(e)}")
                st.json(display_df.to_dict(orient='records'))  # Debug: Show the raw data
            
            # Check for changes by comparing with the previous state
            if 'df_previous' in st.session_state:
                # Get the indices where status has changed
                changed_indices = []
                for idx in edited_df.index:
                    if idx in st.session_state.df_previous.index:
                        if edited_df.loc[idx, 'status'] != st.session_state.df_previous.loc[idx, 'status']:
                            changed_indices.append(idx)
                
                if changed_indices:
                    updates = {}
                    for idx in changed_indices:
                        # Get the original index (subtract 1 because we added 1 earlier)
                        original_idx = idx - 1
                        old_status = st.session_state.df_previous.loc[idx, 'status']
                        new_status = edited_df.loc[idx, 'status']
                        updates[original_idx] = {'status': new_status}
                        
                        if new_status == 'Confirmed' and old_status != 'Confirmed':
                            # When confirming, update scope status and justification
                            updates[original_idx].update({
                                'scope_status': 'In Scope',
                                'scope_justification': 'Manually confirmed by BA'
                            })
                        elif new_status == 'Provisional' and old_status == 'Confirmed':
                            # When reverting from Confirmed to Provisional, restore original values
                            if 'original_values' in st.session_state and original_idx in st.session_state.original_values:
                                updates[original_idx].update({
                                    'scope_status': st.session_state.original_values[original_idx]['scope_status'],
                                    'scope_justification': st.session_state.original_values[original_idx]['scope_justification']
                                })
                    
                    # Apply updates to the original dataframe
                    for idx, update in updates.items():
                        if idx in df.index:  # Ensure the index exists in the original df
                            for col, val in update.items():
                                df.at[idx, col] = val
                    
                    # Update the display dataframe in session state
                    st.session_state.df_previous = display_df.copy()
                    st.session_state.last_updated = updates
                    st.rerun()

        else:
            st.error("No provisional user stories found.")

    # ------------------------
    # Tab 4: Project History
    # ------------------------
    with tab4:
        st.markdown("### Project History")
        try:
            sessions_resp = requests.get(
                f"{MEETING_API_BASE}/sessions",
                params={"project_id": selected_project_id}
            )
            sessions_resp.raise_for_status()
            sessions = sessions_resp.json()
            if sessions:
                df_sess = pd.DataFrame(sessions)
                
                # Format the DataFrame for better display
                if not df_sess.empty:
                    # Convert datetime columns if they exist
                    datetime_cols = ['created_at', 'updated_at', 'meeting_date']
                    for col in datetime_cols:
                        if col in df_sess.columns:
                            try:
                                df_sess[col] = pd.to_datetime(df_sess[col]).dt.strftime('%Y-%m-%d %H:%M')
                            except:
                                pass
                    
                    # Display the data in a clean format
                    st.dataframe(
                        df_sess,
                        column_config={
                            col: st.column_config.TextColumn(
                                col.replace('_', ' ').title(),
                                help=f"View {col.replace('_', ' ').lower()}"
                            )
                            for col in df_sess.columns
                        },
                        hide_index=True,
                        width='stretch',
                        height=min(400, 35 * (len(df_sess) + 1)),
                        column_order=[col for col in ['meeting_date', 'name', 'status'] if col in df_sess.columns] + 
                                    [col for col in df_sess.columns if col not in ['meeting_date', 'name', 'status']]
                    )
                    
                    # Add download button
                    csv = df_sess.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="Download as CSV",
                        data=csv,
                        file_name=f'project_history_{selected_project_id}.csv',
                        mime='text/csv',
                    )
                else:
                    st.info("No session data available to display.")
            else:
                st.info("No saved sessions for this project yet.")
        except Exception as e:
            st.error(f"Could not fetch project history: {e}")
            st.exception(e)  # This will show the full traceback for debugging

