# BA Co-Pilot: Requirement Intelligence Platform

## 1. Introduction & Functional Overview

**BA Co-Pilot** is an AI-driven Requirement Intelligence Platform designed to streamline and automate the entire Business Analysis (BA) and Presales workflow. From initial client briefs to the final extraction of structured user stories, the system acts as a "co-pilot" for Business Analysts, Product Managers, and Solution Architects.

The core premise of the platform is to leverage advanced Large Language Models (LLMs) and Multi-Agent Orchestration (LangGraph) to eliminate manual transcription, requirement categorization, and scope gap analysis, thereby drastically reducing the time required to translate client meetings into actionable engineering deliverables.

## 2. Key Features & Business Value

- **Pre-Meeting Intelligence:** Automatically generates a comprehensive Discovery Plan (including expected objectives, potential risks, and targeted questions) from initial presales documents (like Statements of Work or RFP responses) before the first client meeting even begins.
- **Automated Post-Meeting Synthesis:** Ingests raw meeting transcripts and automatically extracts Minutes of Meeting (MoM), categorizes topics (On-Track vs. Off-Track), and extracts raw functional requirements.
- **Scope Gap Analysis:** Automatically compares extracted requirements against the original Statement of Work (SOW) to flag "In-Scope", "Out-of-Scope", and "Needs Clarification" items, protecting the project from scope creep and unbilled effort.
- **Structured User Story Generation:** Transforms raw requirements into structured Agile User Stories with Business Requirement Numbering (BRNs) and standardized `GIVEN/WHEN/THEN` Acceptance Criteria.
- **Multi-Agent "Actor-Critic" Accuracy:** Uses a swarm of specialized AI agents (e.g., "Story Drafter" and "Agile Coach") that review and refine each other's work before presenting it to the user, ensuring extremely high quality and compliance.

## 3. Functional Workflow (The Pipeline)

The platform follows a logical, sequential 4-step pipeline:

### Step 1: Pre-Meeting Intelligence
* **Input:** User uploads an initial SOW, Technical Proposal, or high-level brief.
* **Process:** The AI analyzes the document to understand the project context.
* **Output:** A structured Discovery Plan. This gives the BA a tailored agenda and a list of probing questions to ask during the upcoming requirement gathering sessions.

### Step 2: Post-Meeting Analysis
* **Input:** The BA conducts the meeting and uploads the raw audio transcript, along with a mapping of speaker names (e.g., "Speaker 1" = "John Doe (Client)").
* **Process:** The AI contextually reads the transcript, cross-referencing it with the Discovery Plan from Step 1.
* **Output:** 
  - Formal Minutes of Meeting (MoM).
  - Categorization of topics discussed.
  - Extraction of raw, unstructured functional requirements.

### Step 3: Scope Gap Analysis
* **Input:** The raw requirements extracted in Step 2.
* **Process:** A Compliance AI Agent reviews each requirement against the original SOW from Step 1. An independent "Reviewer Agent" verifies the classification.
* **Output:** A Kanban-style board categorizing each requirement as In-Scope, Out-of-Scope, or Needs Clarification, along with specific citations from the SOW.

### Step 4: User Story Generator
* **Input:** The verified In-Scope requirements.
* **Process:** A specialized Story Agent drafts Agile user stories grouped by module. An "Agile Coach" agent reviews them for formatting and clarity. The system cycles until the coach approves.
* **Output:** Ready-to-export (CSV) User Stories containing BRNs, sub-modules, descriptions, and GIVEN/WHEN/THEN acceptance criteria.

---

## 4. Technical Architecture

The platform is built on a modern, decoupled architecture:

- **Frontend:** React (Vite) + Vanilla CSS (No Tailwind).
- **Backend:** Python + FastAPI.
- **Database:** SQLite (via SQLAlchemy ORM).
- **AI Orchestration:** LangGraph + LangChain.
- **LLM Provider:** DeepSeek API (using dual models: V4-Pro for reasoning and V4-Flash for fast extraction).

### Architecture Diagram
```text
[ React Frontend ]  <-- REST API -->  [ FastAPI Backend ]
        |                                     |
        |                                     v
  [ UI Components ]                 [ SQLAlchemy SQLite DB ]
        |                                     |
  [ Axios Client ]                  [ LangGraph Workflows ]
                                              |
                                              v
                                     [ DeepSeek API ]
```

## 5. Component Details

### Frontend (React)
- **`ProjectContext`:** Manages the global state of the active project and pipeline step validation.
- **`client.js`:** Centralized Axios API client. Handles all backend communication, including auto-recovery mechanisms and long-running AI request configurations (`timeout: 0`).
- **`LoadingOverlay`:** A dynamic component that provides real-time, agent-themed progress updates to keep users informed during multi-minute LLM operations.
- **Pages:** Modular views mapped directly to the functional workflow (`PreMeeting.jsx`, `PostMeeting.jsx`, `ScopeGap.jsx`, `UserStories.jsx`).

### Backend (FastAPI)
- **`main.py`:** Application entry point, configures CORS, initializes the DB, and mounts API routers.
- **Routers:** Distinct controllers for `meeting_api.py`, `scope_api.py`, and `user_story_api.py`.
- **`models.py`:** Relational schema storing `Project`, `MeetingSession`, `Requirement`, and `UserStory` entities.
- **`graph_workflows.py`:** The core AI engine. Contains stateful LangGraph workflows that implement the **Actor-Critic** design pattern. It defines distinct graphs for MoM Generation, Story Generation, and Scope Analysis using fully asynchronous `ainvoke` calls to prevent blocking the FastAPI event loop.

### AI / LangGraph Sub-Agents
The AI logic is separated into specific "personas" defined by markdown prompts in the `sub_agents/` directory:
- **Actor Nodes:** Generate the initial drafts (e.g., `story_generator.md`).
- **Critic Nodes:** Review the drafts against strict criteria (e.g., `story_reviewer.md`).
- **Conditional Edges:** If the critic returns "REWORK", the graph loops back to the Actor. If "PASS", it proceeds to the database.

## 6. Getting Started / Local Setup

### Prerequisites
- Node.js (v18+)
- Python (3.10+)
- A valid DeepSeek API Key.

### Environment Configuration
Create a `.env` file in the project root:
```env
DEEPSEEK_API_KEY="your_api_key_here"
LLM_MODEL_PRO="deepseek-v4-pro"
LLM_MODEL_FLASH="deepseek-v4-flash"
LLM_MAX_OUTPUT_TOKENS="8192"
LLM_MAX_INPUT_CHARS="500000"
DATABASE_URL="sqlite:///./requirements.db"
```

### Running the Backend
1. Open a terminal in the project root.
2. Install dependencies: `pip install -r requirements.txt`
3. Run FastAPI: `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload`

### Running the Frontend
1. Open a second terminal in `react-frontend/`.
2. Install dependencies: `npm install`
3. Start the Vite dev server: `npm run dev`
4. Access the UI at `http://localhost:5173`.

## 7. Future Extensibility
- **Jira/Azure DevOps Integration:** Direct push of generated User Stories via REST APIs.
- **Streaming UI:** Full Server-Sent Events (SSE) integration for character-by-character text streaming.
- **Vector Database:** Indexing past project requirements for semantic search and context retrieval for new, similar projects.
