import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import json
import os
from typing import Dict, List, Optional, Any

# Configuration
MEETING_API_BASE = "http://127.0.0.1:8000"

# Page config
st.set_page_config(
    page_title="Scope Gap Analysis",
    page_icon="📈",
    layout="wide"
)

# Set page style
st.markdown("""
    <style>
    .main .block-container {
        max-width: 95%;
        padding-top: 2rem;
    }
    .stButton>button {
        width: 100%;
    }
    .stSelectbox, .stTextInput, .stTextArea {
        margin-bottom: 1rem;
    }
    </style>
""", unsafe_allow_html=True)

def get_projects() -> List[Dict[str, Any]]:
    """Fetch all projects from the backend"""
    try:
        response = requests.get(f"{MEETING_API_BASE}/api/v1/projects")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching projects: {str(e)}")
        return []

def get_project_sessions(project_id: int) -> List[Dict[str, Any]]:
    """Fetch all sessions for a project"""
    try:
        response = requests.get(f"{MEETING_API_BASE}/api/v1/meetings/sessions?project_id={project_id}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching sessions: {str(e)}")
        return []

def analyze_project_scope(project_id: int) -> Optional[Dict[str, Any]]:
    """Trigger scope analysis for a project"""
    try:
        response = requests.post(
            f"{MEETING_API_BASE}/api/v1/scopes/projects/{project_id}/analyze-scope"
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error during analysis: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_detail = e.response.json().get('detail', 'No details provided')
                st.error(f"Error details: {error_detail}")
            except:
                st.error(f"Response: {e.response.text}")
        return None

def get_project_requirements(
    project_id: int, 
    module: Optional[str] = None,
    scope_status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Fetch all requirements for a project with scope analysis"""
    try:
        params = {}
        if module:
            params['module'] = module
        if scope_status:
            params['scope_status'] = scope_status
            
        response = requests.get(
            f"{MEETING_API_BASE}/api/v1/scopes/projects/{project_id}/requirements",
            params=params
        )
        response.raise_for_status()
        data = response.json()
        return data.get('requirements', [])
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching requirements: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_detail = e.response.json().get('detail', 'No details provided')
                st.error(f"Error details: {error_detail}")
            except:
                st.error(f"Response: {e.response.text}")
        return []

def display_scope_legend():
    """Display a legend for scope statuses"""
    st.sidebar.markdown("### Scope Status Legend")
    legend = {
        "In Scope": "✅ Requirements that are within the project's scope",
        "Out of Scope": "❌ Requirements that are outside the project's scope",
        "Needs Clarification": "❓ Requirements that need further clarification"
    }
    
    for status, description in legend.items():
        st.sidebar.markdown(f"**{status}**: {description}")

def main():
    st.title("📊 Scope Gap Analysis")
    st.markdown("""
    Analyze requirements across all meeting sessions and compare them against the project's 
    Statement of Work to identify scope gaps and potential out-of-scope items.
    """)
    
    # Initialize session state for analysis status
    if 'analysis_run' not in st.session_state:
        st.session_state.analysis_run = False
    if 'requirements' not in st.session_state:
        st.session_state.requirements = []
    if 'analysis_requested' not in st.session_state:
        st.session_state.analysis_requested = False
    
    # Display legend in sidebar
    display_scope_legend()
    
    # Get projects list
    with st.spinner("Loading projects..."):
        projects = get_projects()
    
    if not projects:
        st.warning("No projects found. Please create a project first.")
        return
    
    # Project selection - show only client names in dropdown
    project_options = {p['id']: p['client_name'] for p in projects}
    selected_project_id = st.selectbox(
        "Select Project",
        options=list(project_options.keys()),
        format_func=lambda x: project_options[x],
        key="project_selector",
        on_change=lambda: [
            setattr(st.session_state, 'analysis_run', False),
            setattr(st.session_state, 'requirements', []),
            setattr(st.session_state, 'analysis_requested', False)  # Reset analysis requested flag
        ]
    )
    
    if not selected_project_id:
        return
    
    # Get project details
    selected_project = next((p for p in projects if p['id'] == selected_project_id), None)
    
    # Project info
    st.subheader("Project Information")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Client", selected_project['client_name'])
    
    with st.spinner("Loading project sessions..."):
        sessions = get_project_sessions(selected_project_id)
        with col2:
            st.metric("Sessions", len(sessions))
    
    # Analysis section
    st.markdown("---")
    st.subheader("Scope Analysis")
    
    if not sessions:
        st.warning("No meeting sessions found for this project. Please add sessions first.")
        return
    
    # Run analysis button
    if st.button("🔍 Run Scope Gap Analysis", type="primary", key="run_analysis_btn", use_container_width=True):
        # Set flags to indicate analysis was requested for this project
        st.session_state.analysis_requested = True
        st.session_state.last_project_id = selected_project_id  # Track which project we're analyzing
        st.session_state.requirements = []
        st.session_state.analysis_run = False
        st.rerun()  # Clear any existing output and trigger a rerun
    
    # Only run analysis if the button was clicked in the current session
    # and we're not already in a loading state
    current_project = st.session_state.get('last_project_id')
    if (st.session_state.get('analysis_requested', False) and 
        not st.session_state.analysis_run and 
        not st.session_state.requirements and
        current_project == selected_project_id):
        with st.spinner("🔍 Analyzing project scope. This may take a few minutes..."):
            result = analyze_project_scope(selected_project_id)
            
            if result:
                st.session_state.analysis_run = True
                st.session_state.requirements = get_project_requirements(selected_project_id)
                st.rerun()  # Refresh to show results
    
    # Show requirements table if we have data or the analysis has been run
    requirements = st.session_state.requirements if hasattr(st.session_state, 'requirements') else []
    
    if (st.session_state.analysis_run or requirements) and requirements:
        st.markdown("---")
        st.subheader("Requirements Scope Analysis")
        
        # Convert to DataFrame for display
        df = pd.DataFrame(st.session_state.requirements)
        
        # Add emojis for status
        status_emojis = {
            "In Scope": "✅",
            "Out of Scope": "❌",
            "Needs Clarification": "❓",
            "Pending Analysis": "⏳"
        }
        
        df['status_display'] = df['scope_status'].apply(
            lambda x: f"{status_emojis.get(x, '')} {x}"
        )
        
        # Filter options in sidebar
        st.sidebar.subheader("Filters")
        
        # Module filter
        modules = ["All"] + sorted(df['module'].dropna().unique().tolist())
        selected_module = st.sidebar.selectbox(
            "Module", 
            modules,
            key="module_filter"
        )
        
        # Scope status filter
        statuses = ["All"] + sorted(df['scope_status'].dropna().unique().tolist())
        selected_status = st.sidebar.selectbox(
            "Scope Status", 
            statuses,
            key="status_filter"
        )
        
        # Apply filters
        if selected_module != "All":
            df = df[df['module'] == selected_module]
        if selected_status != "All":
            df = df[df['scope_status'] == selected_status]
        
        # Show summary stats
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Requirements", len(df))
        with col2:
            in_scope = len(df[df['scope_status'] == 'In Scope'])
            st.metric("✅ In Scope", in_scope)
        with col3:
            out_of_scope = len(df[df['scope_status'] == 'Out of Scope'])
            st.metric("❌ Out of Scope", out_of_scope)
        with col4:
            needs_clarification = len(df[df['scope_status'] == 'Needs Clarification'])
            st.metric("❓ Needs Clarification", needs_clarification)
        
        # Display table with better formatting
        st.data_editor(
            df[['status_display', 'module', 'text', 'scope_justification']],
            column_config={
                "status_display": st.column_config.TextColumn(
                    "Status",
                    help="Scope status of the requirement"
                ),
                "module": st.column_config.TextColumn(
                    "Module",
                    help="Module or category of the requirement"
                ),
                "text": st.column_config.TextColumn(
                    "Requirement",
                    help="The requirement or user story text"
                ),
                "scope_justification": st.column_config.TextColumn(
                    "Justification",
                    help="Explanation for the scope decision"
                ),
            },
            hide_index=True,
            width='stretch',
            height=500,
            disabled=True
        )
        
        # Download button
        st.download_button(
            label="📥 Download Analysis Report (CSV)",
            data=df.to_csv(index=False).encode('utf-8'),
            file_name=f"scope_analysis_{selected_project['client_name'].lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )
        
        # Visualizations section removed as per request
    
    # Show message if no analysis has been run yet
    if not st.session_state.analysis_run and not requirements:
        st.info("Click 'Run Scope Gap Analysis' to analyze the project scope")

if __name__ == "__main__":
    main()
