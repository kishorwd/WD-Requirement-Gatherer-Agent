import streamlit as st
import requests

# --- Page Configuration ---
# This must be the first Streamlit command in your script.
st.set_page_config(
    page_title="BA Co-Pilot - Pre-Meeting Intelligence",
    page_icon="🧠",
    layout="wide"
)

# --- Global Styles (Formatting only) ---
st.markdown(
    """
    <style>
    /* Card-like sections */
    .app-section { 
        padding: 16px; 
        border: 1px solid #e6e6e6; 
        border-radius: 10px; 
        background: #ffffff; 
        box-shadow: 0 1px 2px rgba(0,0,0,.04); 
        margin-bottom: 16px; 
    }
    /* Subtle helper text */
    .app-subtle { color: #5f6368; font-size: 0.9rem; }
    /* Badge styling for inline metadata */
    .app-badge { 
        display: inline-block; 
        padding: 4px 10px; 
        border-radius: 999px; 
        background: #dcf5da; 
        color: #334155; 
        border: 1px solid #c7d2fe; 
        margin-right: 8px; 
        margin-bottom: 4px;
        font-weight: 600;
    }
    /* Buttons */
    .stButton>button { 
        border-radius: 8px; 
        height: 42px; 
        font-weight: 600; 
    }
    /* File uploader */
    div[data-testid="stFileUploader"] { 
        border: 1px dashed #cbd5e1; 
        border-radius: 10px; 
        padding: 8px; 
        background: #fafafa;
    }
    /* Textareas */
    textarea { border-radius: 8px !important; }
    /* Headings spacing */
    .stMarkdown h1, .stMarkdown h2 { margin-bottom: 0.5rem; }
    .section-title { margin-bottom: 8px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Initialize Session State ---
# We use session_state to keep track of how many additional document slots to show.
# This state persists across reruns of the script (which happens on every user interaction).
if 'additional_doc_count' not in st.session_state:
    st.session_state.additional_doc_count = 0

if 'intelligence_brief' not in st.session_state:
    st.session_state.intelligence_brief = None

# --- Helper Functions ---
def add_document_slot():
    """Increments the counter in session state to add more document upload slots."""
    st.session_state.additional_doc_count += 1

# --- Sidebar for Core Inputs ---
# Using a sidebar helps to keep the main interface clean.
with st.sidebar:
    st.header("Project Setup")
    client_name = st.text_input("Client Name", placeholder="e.g., Tata Motors")
    industry = st.text_input("Industry", placeholder="e.g., Automotive Manufacturing")
    st.markdown("---")
    st.info("Provide core project details here. Upload documents and add specific instructions in the main area.")

# --- Main Page Area ---
st.title("🎯 Pre-Meeting Intelligence")
# Inline metadata badges (formatting only)
st.markdown(
    f"<span class='app-badge'>Client: { (client_name or '—') }</span>"
    f"<span class='app-badge'>Industry: { (industry or '—') }</span>",
    unsafe_allow_html=True,
)
st.markdown("---")

# --- Document Upload Section ---
st.header("1. Document Ingestion")

# Primary Presales Document
presales_doc = st.file_uploader(
    "Upload the main Presales or Scope of Work (SOW) Document",
    type=['pdf', 'docx', 'xlsx', 'xls'],
    accept_multiple_files=False # This is the single, primary document
)

st.subheader("Additional Documents")

# This button calls the helper function to add a new upload slot
st.button("Add More Documents", on_click=add_document_slot)

# We will store the data from the dynamically created fields in this list
additional_docs = []

# Dynamically create upload slots based on the count in session state
for i in range(st.session_state.additional_doc_count):
    st.markdown(f"**Additional Document #{i+1}**")
    doc_explanation = st.text_area(
        f"Explanation for Document #{i+1}",
        key=f"doc_exp_{i}", # A unique key is essential for every Streamlit widget
        placeholder="e.g., This document contains the technical architecture from a previous project."
    )
    additional_file = st.file_uploader(
        f"Upload Additional Document #{i+1}",
        type=['pdf', 'docx', 'xlsx', 'xls'],
        key=f"doc_upload_{i}" # Unique key
    )
    # Only add the document to our list if a file has actually been uploaded
    if additional_file:
        additional_docs.append({"explanation": doc_explanation, "file": additional_file})

# --- BA Input Section ---
st.markdown("---")
st.header("2. Business Analyst Input")
ba_input = st.text_area(
    "Provide specific research focus or context",
    placeholder="e.g., 'Focus on their supply chain logistics and recent challenges in the European market. Also, find their key competitors in the electric vehicle space.'"
)

st.markdown("---")

# --- Action Button & Backend Communication ---
if st.button("Generate Intelligence Brief", type="primary", width='stretch'):
    # 1. Validate that essential inputs are provided with explicit checks
    missing_fields = []
    if not client_name or not client_name.strip():
        missing_fields.append("Client Name")
    if not industry or not industry.strip():
        missing_fields.append("Industry")
    if not presales_doc:
        missing_fields.append("Presales Document")

    if missing_fields:
        st.warning("Missing: " + ", ".join(missing_fields) + ". Please provide the required fields.")
    else:
        # 2. Prepare data and files for the API call
        with st.spinner("Connecting to the backend and generating the brief... This may take a moment."):
            backend_url = "http://127.0.0.1:8000/api/v1/generate-brief"

            # Prepare the text fields payload using a list of tuples so
            # repeated keys like 'additional_explanations' are sent correctly
            data_payload = [
                ('client_name', client_name),
                ('industry', industry),
                ('ba_input', ba_input),
            ]

            # Prepare the files payload in the format requests expects for 'multipart/form-data'
            # Format: ('field_name', (filename, file_content, content_type))
            files_payload = [
                ('presales_doc', (presales_doc.name, presales_doc.getvalue(), presales_doc.type or 'application/octet-stream'))
            ]

            # Add additional docs and their explanations to the payloads
            additional_explanations_list = []
            for doc in additional_docs:
                additional_explanations_list.append(doc["explanation"])
                files_payload.append(
                    ('additional_docs', (doc['file'].name, doc['file'].getvalue(), doc['file'].type or 'application/octet-stream'))
                )
            
            # Append each explanation as a separate field with the same name
            for exp in additional_explanations_list:
                data_payload.append(('additional_explanations', exp))

            # 3. Make the API call to the FastAPI backend
            try:
                response = requests.post(url=backend_url, data=data_payload, files=files_payload, timeout=500)
                response.raise_for_status()

                # Get the response from the backend
                backend_response = response.json()
                st.success(backend_response.get("message"))

                # Store the actual brief in the session state
                st.session_state.intelligence_brief = backend_response.get("brief")

            except requests.exceptions.Timeout:
                st.error("Request timed out while waiting for the backend. Please try again or check the logs.")
            except requests.exceptions.RequestException as e:
                st.error(f"Failed to connect to the backend. Please ensure it is running. Error: {e}")
            except Exception as e:
                st.error(f"An unexpected error occurred: {e}")

# --- Display Result ---
# Checks if the intelligence brief exists in the session state and displays it.
if st.session_state.intelligence_brief:
    st.header("Your Generated Intelligence Brief")
    # Use an expander with a larger container to ensure long content renders fully
    with st.expander("Show/Hide Brief", expanded=True):
        st.markdown(st.session_state.intelligence_brief)