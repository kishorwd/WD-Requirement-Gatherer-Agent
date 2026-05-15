from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api import router as v1_router
from backend.meeting_api import router as meeting_router
from backend.scope_api import router as scope_router
from backend.user_story_api import router as user_story_router
from backend.models import create_db_and_tables, apply_schema_migrations

# ------------------------
# Initialize DB on startup
# ------------------------
create_db_and_tables()
apply_schema_migrations()

# ------------------------
# FastAPI App
# ------------------------
app = FastAPI(title="Requirement Agent API")

# ------------------------
# CORS Middleware (for React dev server)
# ------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core API routes
app.include_router(v1_router, prefix="/api/v1")

# Meeting-related API routes
app.include_router(meeting_router, prefix="/api/v1/meetings")

# Scope analysis API routes
app.include_router(scope_router, prefix="/api/v1/scopes")

# User story generation API routes
app.include_router(user_story_router, prefix="/api/v1")

# ------------------------
# Root Endpoint
# ------------------------
@app.get("/")
def read_root():
    return {"message": "Backend is running!"}