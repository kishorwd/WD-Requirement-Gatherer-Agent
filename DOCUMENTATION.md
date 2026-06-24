# BA Co-Pilot — Requirement Intelligence Platform
### Complete Technical & Functional Documentation

> **Purpose of this document:** A single, self-contained reference that allows any human developer or AI agent to fully understand, run, extend, and reason about this codebase without reading the source first. It covers *what* the system does (functional), *how* it is built (technical), the *data model*, the *API surface*, the *multi-agent AI design*, and *operational concerns*.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Functional Overview — What the Product Does](#2-functional-overview--what-the-product-does)
3. [The 4-Stage Pipeline (End-to-End User Journey)](#3-the-4-stage-pipeline-end-to-end-user-journey)
4. [System Architecture](#4-system-architecture)
5. [Technology Stack](#5-technology-stack)
6. [Repository Layout](#6-repository-layout)
7. [Data Model (Database Schema)](#7-data-model-database-schema)
8. [Backend Reference (FastAPI)](#8-backend-reference-fastapi)
9. [Core AI Engine (LangGraph + DeepSeek)](#9-core-ai-engine-langgraph--deepseek)
10. [The Multi-Agent System (sub_agents/)](#10-the-multi-agent-system-sub_agents)
11. [Frontend Reference (React)](#11-frontend-reference-react)
12. [End-to-End Data Flow Walkthroughs](#12-end-to-end-data-flow-walkthroughs)
13. [Configuration & Environment Variables](#13-configuration--environment-variables)
14. [Local Setup & Running](#14-local-setup--running)
15. [Operational Notes, Limitations & Future Work](#15-operational-notes-limitations--future-work)
16. [Glossary](#16-glossary)

---

## 1. Executive Summary

**BA Co-Pilot** is an AI-driven **Requirement Intelligence Platform** that automates the Business Analysis (BA) and Presales workflow — from the first client brief through to exported, structured Agile user stories.

It replaces manual transcription, requirement categorization, and scope-gap analysis with a pipeline of **specialized Large Language Model (LLM) agents** orchestrated by **LangGraph**. The defining design pattern is **Actor–Critic**: a generator agent drafts an artifact, a reviewer agent critiques it against strict criteria, and the system loops until the critic approves (capped at 2 cycles).

- **Frontend:** React 19 + Vite + React Router 7 (Vanilla CSS, no Tailwind).
- **Backend:** Python + FastAPI + SQLAlchemy.
- **Database:** SQLite (`data/projects.db`).
- **AI Orchestration:** LangGraph + LangChain.
- **LLM Provider:** DeepSeek (OpenAI-compatible SDK), using a dual-model strategy — a "Pro" model for reasoning and a "Flash" model for fast extraction.

The system is organized around a **Project** (one client engagement), which contains **Meeting Sessions**, each producing **Requirements**, which are eventually synthesized into **User Stories** with optional **Clarification Questions** (Human-in-the-Loop).

---

## 2. Functional Overview — What the Product Does

The platform acts as a "co-pilot" for Business Analysts, Product Managers, and Solution Architects. Its core capabilities:

| Capability | Business Value |
|---|---|
| **Pre-Meeting Intelligence** | Reads presales docs (SOW / RFP / proposal) and generates a tailored *Discovery Plan*: executive summary, scope, risks, and targeted discovery questions — before the first meeting. |
| **Automated Post-Meeting Synthesis** | Ingests raw meeting transcripts and produces formal Minutes of Meeting (MoM), topic categorization (on-track / off-track / open), and extracted raw requirements. |
| **Scope Gap Analysis** | Classifies each requirement against the original SOW as *In Scope*, *Out of Scope*, or *Needs Clarification*, with citations — protecting against scope creep and unbilled effort. |
| **Structured User Story Generation** | Converts requirements into Agile user stories with Business Requirement Numbers (BRNs) and `GIVEN/WHEN/THEN` acceptance criteria, exportable to CSV. |
| **Human-in-the-Loop (HITL) Clarification** | When the AI cannot confidently generate a story, it raises a *Clarification Question* for the BA. Answers regenerate the affected stories and propagate implications across related stories. |
| **Cross-Session Conflict Detection** | Detects when a later meeting contradicts an earlier one (e.g., "AWS" → "Azure") and surfaces the conflict, always preferring the latest statement. |
| **Actor–Critic Quality Control** | Every major artifact (MoM, scope classification, user stories) is reviewed by a second "critic" agent and reworked until it passes. |

---

## 3. The 4-Stage Pipeline (End-to-End User Journey)

The product is a sequential, 4-step pipeline. Each step corresponds to a frontend page and a set of backend endpoints.

### Stage 1 — Pre-Meeting Intelligence (`/` → `PreMeeting.jsx`)
- **Input:** Client name, industry, BA focus notes, a required presales document (PDF/DOCX/XLSX), and optional additional docs.
- **Process:** The `briefing_generator` extracts SOW text, generates a structured overview (Pro model), enumerates sub-modules (Flash model), and produces discovery questions per sub-module (Flash model).
- **Output:** A markdown **Intelligence Brief / Discovery Plan**, persisted on the Project. Gives the BA a tailored agenda and probing questions.

### Stage 2 — Post-Meeting Analysis (`/post-meeting` → `PostMeeting.jsx`)
- **Input:** A meeting transcript (TXT/PDF/DOCX), a session number, and a speaker→role mapping (e.g., `{"John Doe": "Client"}`). Optionally a discovery plan (CSV/XLSX).
- **Process:** The `post_meeting_analyzer` runs a 6-step analysis: MoM (Actor–Critic loop), on-track topics, off-track topics, open topics, provisional user stories, and (if prior sessions exist) cross-session conflict detection. Each extracted requirement is then scope-classified.
- **Output:** Formal **MoM** (HTML), topic tables, extracted **Requirements** (persisted), and a **Conflicts** report. Streamed live to the UI.

### Stage 3 — Scope Gap Analysis (`/scope-gap` → `ScopeGap.jsx`)
- **Input:** All requirements across the project's sessions + the SOW.
- **Process:** `multi_session_scope_analyzer` analyzes every session transcript against the SOW, consolidates duplicate requirements across sessions, and resolves conflicting scope statuses to *Needs Review*. Individual requirements use the `scope_gap_analyzer` Actor–Critic loop.
- **Output:** A Kanban/stat board: counts and a pie chart of *In Scope / Out of Scope / Needs Clarification*, a filterable table, and CSV export.

### Stage 4 — User Story Generation (`/user-stories` → `UserStories.jsx`)
- **Input:** The project's requirements, grouped by module, plus cross-session conflict context.
- **Process:** For each module, `story_generator` runs the Story Actor–Critic loop. A module that cannot converge is **"held"**, and a *Clarification Question* is clustered from the failed batch. The BA answers; answers regenerate held stories and an *implications analyzer* identifies already-converged stories needing updates. BRNs are re-indexed.
- **Output:** Ready-to-export (CSV) **User Stories** with BRNs, modules, descriptions, and `GIVEN/WHEN/THEN` acceptance criteria. Stories are tagged `converged`, `held`, or `manual_required`.

---

## 4. System Architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│                          REACT FRONTEND (Vite)                        │
│  Pages: PreMeeting · PostMeeting · ScopeGap · UserStories             │
│  State: ProjectContext (global)   ·   API: src/api/client.js (axios)  │
└───────────────────────────────┬─────────────────────────────────────┘
                                 │  REST + SSE (Server-Sent Events)
                                 │  base: http://127.0.0.1:8000
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        FASTAPI BACKEND (main.py)                      │
│  Routers (all under /api/v1):                                         │
│    api.py          → projects + brief generation                     │
│    meeting_api.py  → /meetings transcript analysis + sessions        │
│    scope_api.py    → /scopes project scope analysis                  │
│    user_story_api.py → stories + clarifications (HITL)                │
└───────────────┬──────────────────────────────────┬──────────────────┘
                │                                    │
                ▼                                    ▼
┌──────────────────────────────┐      ┌─────────────────────────────────┐
│   SQLAlchemy ORM (models.py) │      │      CORE AI ENGINE (core/)      │
│   SQLite: data/projects.db   │      │  briefing_generator              │
│   Tables: projects,sessions, │      │  post_meeting_analyzer           │
│   requirements,user_stories, │      │  scope_gap_analyzer              │
│   clarification_questions    │      │  multi_session_scope_analyzer    │
└──────────────────────────────┘      │  story_generator                 │
                                       │  graph_workflows (LangGraph)     │
                                       │  llm_logger                      │
                                       └──────────────┬──────────────────┘
                                                      │ prompts loaded from
                                                      ▼
                                       ┌─────────────────────────────────┐
                                       │   sub_agents/*.md (19 personas)  │
                                       └──────────────┬──────────────────┘
                                                      │ await llm.ainvoke()
                                                      ▼
                                       ┌─────────────────────────────────┐
                                       │  DeepSeek API (OpenAI-compatible)│
                                       │  Pro model · Flash model         │
                                       └─────────────────────────────────┘
```

**Key architectural properties:**
- **Decoupled** frontend/backend communicating over REST + SSE.
- **Fully async** core: all LLM calls use `await llm.ainvoke(...)` to avoid blocking the FastAPI event loop.
- **Streaming-first** long operations: transcript analysis and story generation stream progress to the UI.
- **Prompt-as-config:** agent behavior lives in markdown files (`sub_agents/`), not hardcoded in Python — easy to tune without code changes.

---

## 5. Technology Stack

### Backend (`requirements.txt`)
| Package | Role |
|---|---|
| `fastapi` | Web framework / API |
| `uvicorn[standard]` | ASGI server |
| `sqlalchemy` | ORM / database access |
| `langchain`, `langchain-openai` | LLM abstraction (`ChatOpenAI` against DeepSeek) |
| `langgraph` | Stateful Actor–Critic graph orchestration |
| `openai` | OpenAI-compatible client used for DeepSeek |
| `python-dotenv` | `.env` loading |
| `python-multipart` | File uploads |
| `pypdf`, `python-docx` | Read PDF / DOCX transcripts & docs |
| `pandas`, `openpyxl`, `xlrd` | Read Excel / CSV discovery plans |

### Frontend (`react-frontend/package.json`)
| Package | Version | Role |
|---|---|---|
| `react`, `react-dom` | ^19.2.x | UI framework |
| `vite` | ^8.x | Build tool / dev server |
| `react-router-dom` | ^7.x | Client-side routing |
| `axios` | ^1.x | HTTP client |
| `recharts` | ^3.x | Pie charts (scope analysis) |
| `react-markdown` + `remark-gfm` | ^10.x / ^4.x | Render markdown (briefs, tables) |
| `eslint` + plugins | ^9.x | Linting |

---

## 6. Repository Layout

```text
Requirement-Gatherer-Agent-main - LG/
├── .env                          # Secrets & config (DeepSeek key, model names) — NOT committed
├── requirements.txt              # Python dependencies
├── PROJECT_DOCUMENTATION.md      # Original high-level doc
├── DOCUMENTATION.md              # ← THIS FILE (complete reference)
│
├── backend/                      # FastAPI application
│   ├── main.py                   # App entry: CORS, DB init, router mounting
│   ├── models.py                 # SQLAlchemy models + DB engine (ACTIVE config)
│   ├── database.py               # Legacy/fallback DB config (NOT used by main.py)
│   ├── api.py                    # Projects + brief generation endpoints
│   ├── meeting_api.py            # Transcript analysis + sessions endpoints
│   ├── scope_api.py              # Project scope analysis endpoints
│   └── user_story_api.py         # Story generation + clarification (HITL) endpoints
│
├── core/                         # AI engine
│   ├── graph_workflows.py        # 3 LangGraph Actor–Critic graphs (MoM, Story, Scope)
│   ├── briefing_generator.py     # Stage 1: pre-meeting brief (non-graph)
│   ├── post_meeting_analyzer.py  # Stage 2: transcript → MoM, topics, requirements
│   ├── scope_gap_analyzer.py     # Stage 3: single-requirement scope classification
│   ├── multi_session_scope_analyzer.py # Stage 3: cross-session aggregation
│   ├── story_generator.py        # Stage 4: stories, clustering, implications
│   └── llm_logger.py             # Appends every LLM response to current_llm_response.txt
│
├── sub_agents/                   # 19 markdown prompt files (agent "personas")
│   ├── brief_overview.md  submodule_enumeration.md  discovery_questions.md
│   ├── speaker_extraction.md  mom_generator.md  mom_reviewer.md
│   ├── on_track_topics.md  off_track_topics.md  open_topics.md
│   ├── conflicting_topics.md  provisional_stories.md
│   ├── transcript_scope_analyzer.md  requirement_scope_analyzer.md  scope_reviewer.md
│   ├── story_generator.md  story_reviewer.md
│   ├── story_clarification_clusterer.md  story_implications_analyzer.md
│   └── memory_manager.md
│
├── react-frontend/               # React SPA
│   └── src/
│       ├── main.jsx  App.jsx     # Entry + router/layout
│       ├── api/client.js         # Axios instance + all endpoint wrappers
│       ├── context/ProjectContext.jsx  # Global project state
│       ├── components/           # Sidebar, LoadingOverlay, FileDropzone,
│       │                         #   MarkdownViewer, CreateProjectModal
│       ├── pages/                # PreMeeting, PostMeeting, ScopeGap, UserStories
│       └── styles/               # index.css, components.css
│
├── data/
│   └── projects.db               # SQLite database (the active store)
│
├── migrate_add_project_fields.py # One-off migration scripts
├── run_migration.py
├── list_models.py / save_models.py  # DeepSeek model listing utilities
└── scratch/ , Testing Files/     # Experimental / test scripts
```

---

## 7. Data Model (Database Schema)

**Engine:** SQLite at `data/projects.db` (configured in `backend/models.py`, `check_same_thread=False`).
**Tables:** `projects`, `sessions`, `requirements`, `user_stories`, `clarification_questions` (+ `alembic_version` legacy marker).

Schema is created on startup via `create_db_and_tables()` and `apply_schema_migrations()` (idempotent `ALTER TABLE ... ADD COLUMN`).

### Entity-Relationship Overview
```text
Project (1) ──< (N) MeetingSession (1) ──< (N) Requirement
   │
   ├──< (N) UserStory
   └──< (N) ClarificationQuestion
```
All child relationships use **cascade delete** — deleting a Project removes its sessions, requirements, stories, and clarifications.

### `projects`
| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | auto-increment |
| `client_name` | String, **unique**, indexed | engagement identifier |
| `industry` | String, nullable | |
| `sow_text` | Text, nullable | Statement of Work (extracted from presales doc) |
| `discovery_plan_json` | Text, nullable | discovery plan as JSON string |
| `pre_meeting_brief` | Text, nullable | generated Stage-1 brief (markdown) |

Relationships: `sessions`, `user_stories`, `clarification_questions` (all cascade delete).

### `sessions` (MeetingSession)
| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `project_id` | Integer FK → `projects.id` | |
| `session_number` | Integer | meeting ordinal (1, 2, 3…) |
| `transcript_text` | Text | raw transcript |
| `mom` | Text | Minutes of Meeting (HTML) |
| `analysis_json` | Text | full Stage-2 analysis as JSON string |

Relationships: `requirements` (cascade delete).

### `requirements`
| Column | Type | Default | Notes |
|---|---|---|---|
| `id` | Integer PK | | |
| `session_id` | Integer FK → `sessions.id` | | |
| `text` | Text, NOT NULL | | requirement statement |
| `module` | String | | functional area |
| `status` | String | `Provisional` | `Provisional` \| `Confirmed` |
| `scope_status` | String | `Pending` | `In Scope` \| `Out of Scope` \| `Needs Clarification` \| `Pending` |
| `scope_justification` | Text | | reasoning / SOW citation |
| `is_tentative` | Boolean | `False` | true if requirement used hedging language (might/maybe/could) — *added by migration* |

### `user_stories`
| Column | Type | Default | Notes |
|---|---|---|---|
| `id` | Integer PK | | |
| `project_id` | Integer FK → `projects.id` | | |
| `brn` | String | | Business Requirement Number, e.g. `BRN-001` |
| `sub_brn` | String | | e.g. `BRN-001.1` |
| `module_name` | String | | |
| `sub_module_name` | String | | |
| `description` | Text | | "As a…, I want…, so that…" |
| `acceptance_criteria_json` | Text | | JSON array of GIVEN/WHEN/THEN strings |
| `generation_status` | String | `converged` | `converged` \| `held` \| `manual_required` — *migration* |
| `assumption_text` | Text, nullable | | non-obvious product decisions — *migration* |
| `coach_feedback` | Text, nullable | | reviewer feedback when not converged — *migration* |

### `clarification_questions` (HITL)
| Column | Type | Default | Notes |
|---|---|---|---|
| `id` | Integer PK | | |
| `project_id` | Integer FK → `projects.id` | | |
| `module_name` | String | | |
| `question_text` | Text | | the question for the BA |
| `context_text` | Text | | why the generator got stuck |
| `affected_brns_json` | Text | | JSON array of affected BRN strings |
| `requirements_context_json` | Text | | original requirements, kept for regeneration |
| `answer_text` | Text, nullable | | the BA's answer |
| `status` | String | `pending` | `pending` \| `answered` \| `resolved` |

---

## 8. Backend Reference (FastAPI)

**Entry point:** `backend/main.py`
- `app = FastAPI(title="Requirement Agent API")`
- On import: `create_db_and_tables()` then `apply_schema_migrations()`.
- **CORS:** `allow_origins=["*"]`, `allow_methods=["*"]`, `allow_headers=["*"]`, `allow_credentials=False` (permissive — dev-oriented).
- **Router mounts:**

| Router file | Prefix |
|---|---|
| `api.py` | `/api/v1` |
| `meeting_api.py` | `/api/v1/meetings` |
| `scope_api.py` | `/api/v1/scopes` |
| `user_story_api.py` | `/api/v1` |

- `GET /` → `{"message": "Backend is running!"}` (health check).

> **Note on `database.py`:** It exists as a legacy/fallback DB config (reads `DATABASE_URL` env, defaults to `sqlite:///./requirements.db`) but is **not** wired into `main.py`. The active source of truth is `backend/models.py`, which points at `data/projects.db`.

### 8.1 `api.py` — Projects & Brief Generation (prefix `/api/v1`)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/generate-brief` | Generate Stage-1 intelligence brief from uploaded docs. Multipart: `client_name`, `industry`, `ba_input`, `presales_doc` (file), `additional_docs[]`, `additional_explanations[]`. Creates/updates Project, persists `pre_meeting_brief` + `sow_text`. Returns `{status, brief, project_id}`. |
| `POST` | `/projects/create` | Create a project (form: `client_name`, `industry?`, `sow_text?`). 400 on duplicate `client_name`. Returns full detail. |
| `GET` | `/projects` | List all projects (lightweight summary incl. `has_brief`, `session_count`, `requirement_count`). |
| `GET` | `/projects/{project_id}` | Full project detail. 404 if missing. |
| `DELETE` | `/projects/{project_id}` | Delete project (cascades). |

Serializers: `serialize_project_summary()` (list view) and `serialize_project_detail()` (detail view).

### 8.2 `meeting_api.py` — Transcript Analysis & Sessions (prefix `/api/v1/meetings`)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/project/{project_id}/upload-plan` | Upload discovery plan (CSV/XLSX) → stored as `discovery_plan_json` via pandas. |
| `POST` | `/analyze-transcript` | **Synchronous** analysis. Multipart: `project_id`, `session_number`, `speaker_tags_json`, `transcript_file`. Runs full Stage-2 pipeline, scope-classifies each requirement, persists a `MeetingSession` + `Requirement` rows. Returns `{session_id, requirements_added, analysis_result}`. |
| `POST` | `/analyze-transcript-stream` | **Streaming (SSE)** version. Yields `{status:"progress", message, step}` events, then `{status:"complete", session_id, analysis_result}`. Stages with `db.flush()`, single atomic `db.commit()` at the end — cancellation before commit rolls back cleanly. |
| `POST` | `/extract-speakers` | Multipart `transcript_file` → `{speakers:[...]}` via Flash model. |
| `GET` | `/sessions?project_id=` | List sessions for a project (ordered by `session_number`). |
| `GET` | `/session/{session_id}/requirements` | Requirements for a session. |

### 8.3 `scope_api.py` — Scope Analysis (prefix `/api/v1/scopes`)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/projects/{project_id}/analyze-scope` | Analyze all session transcripts against the SOW, consolidate duplicates. Returns `{sessions_analyzed, requirements_identified, results[]}`. |
| `GET` | `/projects/{project_id}/requirements` | Consolidated requirements (deduped by lowercased text+module). Optional filters: `module`, `scope_status`. Returns `{count, requirements[]}` each with `session_ids[]` and `occurrences`. |

### 8.4 `user_story_api.py` — Stories & Clarifications / HITL (prefix `/api/v1`)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/stories/projects` | List projects (story view). |
| `GET` | `/stories/project/{project_id}/requirements` | All requirements for a project. |
| `GET` | `/stories/project/{project_id}` | All user stories for a project. |
| `GET` | `/stories/project/{project_id}/clarifications` | Pending clarification questions. |
| `POST` | `/stories/generate-stories/{project_id}` | **Synchronous** generation. Groups requirements by module, runs the Story graph per module. Modules that don't converge become `held` and generate clarification questions via clustering. Assigns BRNs, persists. |
| `GET` | `/stories/generate-stories-stream/{project_id}` | **Streaming (SSE)** generation — same logic with progress events. |
| `POST` | `/stories/project/{project_id}/clarifications/answer` | **HITL submit.** Body `{answers:[{question_id, answer_text}]}`. (1) Regenerates held stories with the answer context; (2) runs implications analysis to update affected converged stories; (3) re-indexes all BRNs. Returns updated `stories[]` + remaining `clarification_count`. |

Serializer `_serialize_story()` exposes `acceptance_criteria` (parsed list), `generation_status`, `assumption_text`, `coach_feedback`.

---

## 9. Core AI Engine (LangGraph + DeepSeek)

### 9.1 Dual-Model Strategy

Both models are DeepSeek, accessed through LangChain's `ChatOpenAI` pointed at `https://api.deepseek.com` with `DEEPSEEK_API_KEY`. Temperature `0.0` for deterministic graph nodes.

| Model | Env var | Used for |
|---|---|---|
| **Pro** (default) | `LLM_MODEL_PRO` | Reasoning-heavy: MoM, reviews, scope analysis, story generation, topic analysis |
| **Flash** | `LLM_MODEL_FLASH` | Fast extraction: speaker names, sub-module enumeration, discovery questions |

`_init_llm(use_flash=False)` returns a `ChatOpenAI` or `None` if the API key is missing (callers then fall back to heuristics where defined).

### 9.2 The Actor–Critic Pattern (`graph_workflows.py`)

Three compiled LangGraph singletons share an identical shape:

```text
        ┌──────────────┐      ┌────────────┐
START ─► │  generate    │ ───► │  review    │ ──► conditional edge
        │  (Actor)     │      │  (Critic)  │       │
        └──────▲───────┘      └────────────┘       │
               │                                   │
               └────────── "rework" ◄──────────────┤
                                                    │
                                  "done" ──────────►END
```

- `MAX_REVIEW_CYCLES = 2` — the conditional edge loops back to `generate` only if `review_status == "REWORK"` **and** `review_cycle < 2`; otherwise it ends.
- On rework, the generator prompt is augmented with the previous draft **and** the critic's feedback.
- Prompts are loaded with `_load_prompt(filename)` from `sub_agents/`.
- JSON is parsed robustly with `_parse_json()` (handles code fences and nested objects).

| Graph | State (TypedDict) | Actor prompt | Critic prompt | Output |
|---|---|---|---|---|
| **MoM** (`mom_review_graph`) | `MomState` (transcript, speaker/discovery/SOW blocks, draft_mom, review_*) | `mom_generator.md` | `mom_reviewer.md` | HTML MoM |
| **Story** (`story_review_graph`) | `StoryState` (requirements_text, draft_stories, validated_stories, review_*) | `story_generator.md` | `story_reviewer.md` | validated story list |
| **Scope** (`scope_review_graph`) | `ScopeState` (formatted_sow, requirement_text, draft_scope, scope_result, review_*) | `requirement_scope_analyzer.md` | `scope_reviewer.md` | scope classification |

### 9.3 Module-by-Module

**`briefing_generator.py` (Stage 1, non-graph).**
`generate_intelligence_brief(client_name, industry, ba_input, presales_doc_content, presales_doc_name, additional_docs)` (async):
1. Overview (sections 1–4) with **Pro** (`brief_overview.md`).
2. Sub-module enumeration with **Flash** (`submodule_enumeration.md`).
3. Per-sub-module discovery questions with **Flash** (`discovery_questions.md`), optionally batched (`ENABLE_BATCHED_DISCOVERY`, `DISCOVERY_BATCH_SIZE`).
4. Stitch into final markdown.
File extraction: PDF (`pypdf`), DOCX (`python-docx`), Excel (`pandas`). Input budgeted by `LLM_MAX_INPUT_CHARS`.

**`post_meeting_analyzer.py` (Stage 2).**
`analyze_transcript_text(...)` and `analyze_transcript_text_stream(...)` run 6 steps:
1. **MoM** via `mom_review_graph` (Actor–Critic), sanitized to HTML.
2. **On-track topics** (`on_track_topics.md`).
3. **Off-track topics** (`off_track_topics.md`).
4. **Open topics** (`open_topics.md`).
5. **Provisional user stories** (`provisional_stories.md`).
6. **Conflict detection** (`conflicting_topics.md`) — only if `prior_sessions` provided.
Helpers: `read_transcript_bytes()` (TXT/PDF/DOCX), `extract_speakers_llm()` (Flash, `speaker_extraction.md`), `sanitize_mom_html()`.

**`scope_gap_analyzer.py` (Stage 3, per-requirement).**
`analyze_requirement_scope(sow_text, requirement_text)` (async):
1. Try the `scope_review_graph` (Actor–Critic).
2. Fall back to single-shot LLM (`requirement_scope_analyzer.md`).
3. Fall back to a **token-overlap heuristic** if no LLM (≥35% overlap & ≥3 matches → In Scope; ≤5% & ≥8 tokens → Out of Scope; else Needs Clarification; negative phrases like "third-party", "excluded" considered).
`analyze_transcript_against_sow()` does batch extraction with `transcript_scope_analyzer.md`.

**`multi_session_scope_analyzer.py` (Stage 3, cross-session).**
- `analyze_project_scope(sow_text, session_transcripts)` → per-session extraction, flattened with session metadata.
- `consolidate_requirements(...)` → group by lowercased (text, module); conflicting statuses collapse to **"Needs Review"**; counts `occurrences`.

**`story_generator.py` (Stage 4).**
- `run_story_graph(requirements_text, conflict_context="", clarification_context="")` → wraps `story_review_graph`; returns `{stories, review_status, review_cycle, coach_feedback, needs_clarification}`.
- `synthesize_user_stories_stream(...)` → streaming variant.
- `cluster_held_batches(held_batches)` → turns failed batches into BA questions (`story_clarification_clusterer.md`).
- `analyze_implications(clarification_qa, converged_stories)` → returns affected BRNs (`story_implications_analyzer.md`).
- `build_conflict_context(sessions)` → aggregates conflicts across sessions, **latest statement wins**.

**`llm_logger.py`.**
`log_llm_response(prompt, response, metadata)` prepends each LLM response (newest first) to `current_llm_response.txt` at the repo root, with timestamp (UTC), calling function (via stack introspection), and stage/model metadata. This file is a debugging/audit log, not application state.

---

## 10. The Multi-Agent System (sub_agents/)

19 markdown prompt files define agent "personas". Behavior is tuned by editing these files — no code change required. Each agent is an **Actor** (generator) or **Critic** (reviewer); a few are utilities.

### Pre-Meeting (Stage 1)
| File | Type | Role / Output |
|---|---|---|
| `brief_overview.md` | Actor | Senior BA → brief sections 1–4 (summary, industry, scope, risks) in markdown. |
| `submodule_enumeration.md` | Actor | Extract JSON array of business sub-modules. |
| `discovery_questions.md` | Actor | 4 open-ended discovery questions per sub-module (markdown table). |

### Post-Meeting (Stage 2)
| File | Type | Role / Output |
|---|---|---|
| `speaker_extraction.md` | Actor | `{"speakers":[...]}` — full names only. |
| `mom_generator.md` | Actor | HTML MoM fragment (`<div class="mom-report">`): discussions, decisions, action items. |
| `mom_reviewer.md` | Critic | `{status: PASS\|REWORK, feedback}` — accuracy/completeness/tone. |
| `on_track_topics.md` | Actor | Topics aligned to SOW/discovery (JSON items). |
| `off_track_topics.md` | Actor | Scope-creep / out-of-scope topics (JSON items). |
| `open_topics.md` | Actor | Unresolved questions / deferred decisions (JSON list). |
| `provisional_stories.md` | Actor | Raw requirements as provisional stories; flags `is_tentative` on hedging language. |
| `conflicting_topics.md` | Critic | Genuine cross-session contradictions only; empty if none. |

### Scope Gap (Stage 3)
| File | Type | Role / Output |
|---|---|---|
| `transcript_scope_analyzer.md` | Actor | Batch: requirements w/ `scope_status` + `sow_citation`. |
| `requirement_scope_analyzer.md` | Actor | Single requirement → `{scope_status, justification, sow_citation}`. |
| `scope_reviewer.md` | Critic | Legal/compliance review; flags borderline as "Needs Clarification". |

### User Stories (Stage 4)
| File | Type | Role / Output |
|---|---|---|
| `story_generator.md` | Actor | Stories: `{module_name, sub_module_name, description, acceptance_criteria[], assumption}`. |
| `story_reviewer.md` | Critic | Agile Coach: enforces GIVEN/WHEN/THEN, testability, story sizing. |
| `story_clarification_clusterer.md` | Critic | Cluster held batches → BA questions w/ context + `held_batch_indices`. |
| `story_implications_analyzer.md` | Critic | Given Q&A + converged stories → `{affected_brns[], reason}`. |

### Utility
| File | Type | Role |
|---|---|---|
| `memory_manager.md` | Utility | Merge new session output into project state JSON; overwrite contradicted decisions, update open action items & scope-change log. |

**Output discipline:** Most agents must emit **strict JSON** (no prose/code fences); the MoM agent emits **HTML**; discovery questions emit a **markdown table**. The Python layer defensively strips fences and extracts nested JSON.

---

## 11. Frontend Reference (React)

**Stack:** React 19 + Vite + React Router 7, axios, recharts, react-markdown. Dev server typically on Vite's port; **backend base URL is hardcoded** to `http://127.0.0.1:8000`.

### 11.1 Routing & Layout (`App.jsx`)
Two-column layout: persistent **Sidebar** + routed main content.

| Route | Page | Stage |
|---|---|---|
| `/` | `PreMeeting.jsx` | 1 — Pre-Meeting Intelligence |
| `/post-meeting` | `PostMeeting.jsx` | 2 — Post-Meeting Analysis |
| `/scope-gap` | `ScopeGap.jsx` | 3 — Scope Gap Analysis |
| `/user-stories` | `UserStories.jsx` | 4 — User Story Generation |

### 11.2 API Client (`src/api/client.js`)
- `axios.create({ baseURL: 'http://127.0.0.1:8000' })`.
- **Long operations use `timeout: 0`** (story generation, clarifications can take 15–30 min).
- **Cancellation:** `AbortController` signals on brief, scope, and clarification calls.
- **Two streaming mechanisms:**
  1. **EventSource (SSE, GET):** `generate-stories-stream`.
  2. **Fetch + ReadableStream (POST):** `analyze-transcript-stream` (needs POST + file upload). Events arrive as `data: {JSON}` lines: `{status:"progress"|"complete"|"error", ...}`.

### 11.3 Global State (`context/ProjectContext.jsx`)
Holds `projects`, `selectedProjectId` (persisted in `localStorage`), `projectDetail`, `loading`. Methods: `refreshProjects`, `selectProject`, `refreshProjectDetail`, `createAndSelectProject`, `deleteProject`. Consumed via the `useProject()` hook. `projectDetail` carries pipeline flags `has_brief`, `has_discovery_plan`, `session_count`, `requirement_count` that drive the Sidebar progress indicator.

### 11.4 Pages (key behaviors)
- **PreMeeting:** collapsible form → `POST /generate-brief` (multipart) → renders brief via `MarkdownViewer`; copy/download; refreshes project detail.
- **PostMeeting:** upload discovery plan → upload transcript (auto `extract-speakers`) → tag speaker roles → `analyzeTranscriptStream` → 5 tabs: **Summary** (MoM HTML), **Conversation** (on/off/open topics), **Requirements** (provisional stories w/ scope badges), **History** (past sessions), **Conflicts** (prior vs current). Session selector switches between sessions.
- **ScopeGap:** `analyze-scope` then `getProjectRequirements`; shows stat cards, recharts **pie chart**, filterable table (module/status), CSV export.
- **UserStories:** `generateStories` (timeout 0) with simulated multi-agent progress messages → loads clarifications. **Clarifications tab:** answer questions (persisted to `localStorage` as `hitl_answers_{projectId}`), submit → regenerates. **Stories tab:** cards with BRN, module, description, GIVEN/WHEN/THEN, assumption; separate section for `manual_required`; CSV export (excludes held).

### 11.5 Reusable Components
- **Sidebar** — project selector, pipeline progress, nav links, backend health poll (~60s), create/delete project.
- **LoadingOverlay** — full-screen spinner, step checklist, cancel button.
- **FileDropzone** — drag-and-drop upload with preview & size formatting.
- **MarkdownViewer** — `react-markdown` + GFM (tables).
- **CreateProjectModal** — new-project dialog with validation.

---

## 12. End-to-End Data Flow Walkthroughs

### A) Generating a Pre-Meeting Brief
1. `PreMeeting.jsx` posts multipart to `POST /api/v1/generate-brief`.
2. `api.py` calls `briefing_generator.generate_intelligence_brief()`.
3. Pro model writes the overview; Flash model enumerates sub-modules and writes discovery questions.
4. SOW text is extracted from the presales doc; both `pre_meeting_brief` and `sow_text` are saved on the **Project**.
5. Response returns the brief + `project_id`; UI renders it and refreshes the sidebar.

### B) Analyzing a Meeting Transcript (streaming)
1. `PostMeeting.jsx` opens a streaming POST to `/api/v1/meetings/analyze-transcript-stream`.
2. `meeting_api.py` reads the transcript, loads the project's discovery plan + SOW + prior-session summaries.
3. `post_meeting_analyzer` runs 6 steps (MoM Actor–Critic, on/off/open topics, provisional stories, conflicts), emitting progress events.
4. Each requirement is scope-classified via `scope_gap_analyzer.analyze_requirement_scope()`.
5. A `MeetingSession` + `Requirement` rows are staged (`flush`) and committed atomically; final `complete` event carries the full `analysis_result`.

### C) Scope Gap Analysis
1. `ScopeGap.jsx` calls `POST /api/v1/scopes/projects/{id}/analyze-scope`.
2. `multi_session_scope_analyzer.analyze_project_scope()` analyzes every session transcript against the SOW.
3. `consolidate_requirements()` dedups across sessions; conflicting statuses → "Needs Review".
4. UI fetches results and renders stats, pie chart, and a filterable table.

### D) User Story Generation + HITL
1. `UserStories.jsx` calls `POST /api/v1/stories/generate-stories/{id}`.
2. `user_story_api.py` groups requirements by module, builds conflict context, and runs the **Story graph** per module.
3. Converged modules → stories saved as `converged`; non-converging modules → `held`, and `cluster_held_batches()` creates **ClarificationQuestions**.
4. BRNs assigned; stories + questions persisted.
5. BA answers via `POST /stories/project/{id}/clarifications/answer`: held stories regenerate with answer context; `analyze_implications()` updates affected converged stories; **all BRNs re-indexed**; updated stories returned.

---

## 13. Configuration & Environment Variables

Create a `.env` in the repo root. (Actual keys present in this repo; **never commit real secrets**.)

```env
# DeepSeek API
DEEPSEEK_API_KEY=your_api_key_here

# Models (dual strategy)
LLM_MODEL_PRO=deepseek-...      # reasoning: MoM, reviews, scope, stories, briefing overview
LLM_MODEL_FLASH=deepseek-...    # fast extraction: speakers, discovery questions, submodules

# LLM limits
LLM_MAX_OUTPUT_TOKENS=8192
LLM_MAX_INPUT_CHARS=180000

# Feature toggles (briefing discovery batching)
ENABLE_BATCHED_DISCOVERY=1
DISCOVERY_BATCH_SIZE=8

# Backend
DATABASE_URL=sqlite:///./requirements.db   # used only by legacy database.py; models.py uses data/projects.db
PORT=8000
HOST=127.0.0.1
```

| Variable | Default (code) | Effect |
|---|---|---|
| `DEEPSEEK_API_KEY` | (required) | Auth for all LLM calls; if absent, scope falls back to heuristics, other steps degrade. |
| `LLM_MODEL_PRO` | `deepseek-v4-pro` | Reasoning model. |
| `LLM_MODEL_FLASH` | `deepseek-v4-flash` | Extraction model. |
| `LLM_MAX_OUTPUT_TOKENS` | `8192` | Max tokens per response. |
| `LLM_MAX_INPUT_CHARS` | `180000` | Input budget for briefing. |
| `ENABLE_BATCHED_DISCOVERY` | enabled | Batch discovery-question generation. |
| `DISCOVERY_BATCH_SIZE` | `8` | Modules per discovery batch. |

---

## 14. Local Setup & Running

**Prerequisites:** Node.js 18+, Python 3.10+, a valid DeepSeek API key.

### Backend
```bash
# from repo root
pip install -r requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```
- DB schema + migrations apply automatically on startup.
- API base: `http://127.0.0.1:8000` (interactive docs at `/docs`).

### Frontend
```bash
cd react-frontend
npm install
npm run dev
```
- Open the Vite URL it prints. The client talks to the backend at the hardcoded `http://127.0.0.1:8000`.

> If the frontend can't reach the backend, confirm the backend is on port 8000 (the base URL in `src/api/client.js` is hardcoded).

---

## 15. Operational Notes, Limitations & Future Work

**Operational characteristics**
- **Long-running AI calls:** Story generation / clarifications can take many minutes; the client disables timeouts (`timeout: 0`) and supports cancellation via `AbortController`.
- **Streaming atomicity:** The streaming transcript endpoint stages writes with `flush()` and commits once at the end — cancelling mid-stream leaves the DB clean.
- **Determinism:** Graph nodes use temperature 0.0; briefing uses slightly higher temperatures for prose.
- **Audit log:** Every LLM response is appended (newest-first) to `current_llm_response.txt` — useful for debugging prompt behavior.

**Known limitations**
- CORS is fully open (`*`) — fine for dev, must be tightened for production.
- Backend base URL is hardcoded in the frontend (no env-based config).
- `database.py` is dead/legacy code; `models.py` is authoritative (`data/projects.db`).
- Errors surface via `window.alert()`; no toast/notification system.
- No automated test suite is configured (only ad-hoc scripts in `scratch/` and `Testing Files/`).
- Actor–Critic loops are capped at 2 cycles — a hard quality/cost trade-off.

**Future work (from original docs)**
- Jira / Azure DevOps push of generated stories.
- Full SSE character-streaming UI.
- Vector DB for semantic retrieval of past requirements across projects.

---

## 16. Glossary

| Term | Meaning |
|---|---|
| **BA** | Business Analyst — primary user. |
| **SOW** | Statement of Work — the contractual scope baseline. |
| **MoM** | Minutes of Meeting — formal HTML meeting summary. |
| **BRN** | Business Requirement Number — story identifier, e.g. `BRN-001`, sub `BRN-001.1`. |
| **Actor–Critic** | A generator agent paired with a reviewer agent that loops until approval (≤2 cycles). |
| **Pro / Flash** | The two DeepSeek models — reasoning vs fast extraction. |
| **Held story** | A story batch the AI couldn't confidently generate; triggers a clarification question. |
| **HITL** | Human-in-the-Loop — BA answers clarification questions to unblock generation. |
| **Provisional requirement** | A raw requirement extracted from a transcript before scope classification. |
| **is_tentative** | Flag for requirements expressed with hedging language (might/maybe/could). |
| **Needs Review** | Consolidated scope status when the same requirement got conflicting statuses across sessions. |

---

*Document generated from a full read of the backend (`backend/`), core AI engine (`core/`), agent prompts (`sub_agents/`), and React frontend (`react-frontend/`). For the canonical behavior of any agent, read its markdown file in `sub_agents/`; for endpoint contracts, read the corresponding router in `backend/`.*
