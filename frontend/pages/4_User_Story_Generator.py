import streamlit as st
import pandas as pd
import requests
import json
from typing import List, Dict, Any
import os
from datetime import datetime

# Page config
st.set_page_config(
    page_title="User Story Generator",
    page_icon="📝",
    layout="wide"
)

# Constants
API_BASE_URL = "http://localhost:8000"

# Custom CSS for better styling
st.markdown("""
<style>
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    .stButton>button {
        background-color: #4CAF50;
        color: white;
        font-weight: bold;
    }
    .stButton>button:hover {
        background-color: #45a049;
    }
    .story-card {
        padding: 1.5rem;
        border-radius: 0.5rem;
        background-color: #f8f9fa;
        margin-bottom: 1rem;
        border-left: 5px solid #4CAF50;
    }
    .story-card h4 {
        margin-top: 0;
        color: #2c3e50;
    }
    .criteria-list {
        margin-top: 0.5rem;
        padding-left: 1.2rem;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data
def convert_df_to_csv(df: pd.DataFrame) -> bytes:
    """Convert a pandas DataFrame to CSV for download."""
    return df.to_csv(index=False).encode('utf-8')

def format_acceptance_criteria(criteria: List[str]) -> str:
    """Format acceptance criteria as a bulleted list."""
    return "\n".join(f"• {item}" for item in criteria)

def fetch_projects():
    """Fetch projects from the backend API."""
    try:
        response = requests.get(f"{API_BASE_URL}/api/v1/stories/projects")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to fetch projects: {str(e)}")
        return []

def main():
    st.title("📝 User Story Generator")
    st.markdown("""
    Generate structured user stories from your project requirements. 
    Select a project and click 'Generate User Stories' to begin.
    """)
    
    # Project selection
    projects = fetch_projects()
    
    if not projects:
        st.warning("No projects found. Please create a project first.")
        return
    
    project_options = {p['name']: p['id'] for p in projects}
    selected_project_name = st.selectbox(
        "Select Project",
        options=list(project_options.keys()),
        index=0,
        help="Choose a project to generate user stories for"
    )
    
    project_id = project_options[selected_project_name]
    
    # Generate button
    if st.button("🚀 Generate User Stories", width='stretch'):
        with st.spinner("Generating user stories. This may take a minute..."):
            try:
                # First, check if the project has requirements
                requirements_response = requests.get(
                    f"{API_BASE_URL}/api/v1/stories/project/{project_id}/requirements"
                )
                
                if requirements_response.status_code != 200:
                    error_msg = requirements_response.json().get("detail", "Unknown error")
                    st.error(f"Failed to fetch requirements: {error_msg}")
                    return
                    
                requirements = requirements_response.json()
                if not requirements:
                    st.warning("No requirements found for this project. Please add requirements first.")
                    return
                
                # Call the API to generate stories
                with st.spinner("Generating user stories. This may take a minute..."):
                    response = requests.post(
                        f"{API_BASE_URL}/api/v1/stories/generate-stories/{project_id}",
                        headers={"Content-Type": "application/json"}
                    )
                
                if response.status_code == 200:
                    stories = response.json()
                    
                    if not stories:
                        st.warning("No user stories were generated. Please check if there are requirements for this project.")
                        return
                    
                    # Store stories in session state
                    st.session_state.stories = stories
                    st.session_state.project_name = selected_project_name
                    
                    # Show success message
                    st.success(f"✅ Successfully generated {len(stories)} user stories!")
                    
                else:
                    error_msg = response.json().get("detail", "Unknown error occurred")
                    st.error(f"Failed to generate stories: {error_msg}")
            
            except requests.exceptions.RequestException as e:
                st.error(f"Failed to connect to the API: {str(e)}")
            except json.JSONDecodeError:
                st.error("Failed to parse the response from the server.")
    
    # Display generated stories if available
    if 'stories' in st.session_state and st.session_state.stories:
        stories = st.session_state.stories
        
        # Convert to DataFrame for display and download
        df_data = []
        for story in stories:
            df_data.append({
                "BRN": story.get("brn", ""),
                "Module": story.get("module_name", ""),
                "Sub-BRN": story.get("sub_brn", ""),
                "Sub Modules": story.get("sub_module_name", ""),
                "Description": story.get("description", ""),
                "User Acceptance Criteria": "\n".join(story.get("acceptance_criteria", []))
            })
        
        df = pd.DataFrame(df_data)
        
        # Download button
        csv = convert_df_to_csv(df)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{st.session_state.project_name.replace(' ', '_')}_User_Stories_{timestamp}.csv"
        
        st.download_button(
            label="💾 Download as CSV",
            data=csv,
            file_name=filename,
            mime="text/csv",
            width='stretch'
        )
        
        # Display stories in an expandable section
        with st.expander("📋 View Generated User Stories", expanded=True):
            st.dataframe(
                df,
                width='stretch',
                hide_index=True,
                column_config={
                    "BRN": "BRN",
                    "Module": "Module",
                    "Sub-BRN": "Sub-BRN",
                    "Sub Modules": "Sub Module",
                    "Description": "Description",
                    "User Acceptance Criteria": "Acceptance Criteria"
                }
            )
        
        # Display stories in a more readable format
        st.subheader("📄 User Stories Preview")
        for idx, story in enumerate(stories, 1):
            with st.container():
                st.markdown(f"""
                <div class="story-card">
                    <h4>📌 {story.get('module_name', 'Uncategorized')} - {story.get('sub_module_name', 'General')}</h4>
                    <p><strong>BRN:</strong> {story.get('brn', '')} | <strong>Sub-BRN:</strong> {story.get('sub_brn', '')}</p>
                    <p><strong>Description:</strong> {story.get('description', '')}</p>
                    <p><strong>Acceptance Criteria:</strong></p>
                    <div class="criteria-list">
                        {"".join([f"<p>• {crit}</p>" for crit in story.get('acceptance_criteria', [])])}
                    </div>
                </div>
                """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
