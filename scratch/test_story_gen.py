import asyncio
import os
import sys
from core.story_generator import synthesize_user_stories
from dotenv import load_dotenv
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO)

async def test():
    requirements = """
    1. The system should allow users to login with email and password.
    2. The system should have a dashboard showing user profile.
    3. The system should allow users to reset their password.
    """
    print("Starting story generation...", flush=True)
    try:
        print("Calling synthesize_user_stories...", flush=True)
        stories = await synthesize_user_stories(requirements)
        print(f"DONE! Generated {len(stories)} stories:", flush=True)
        for s in stories:
            print(f"- {s['module_name']}: {s['description']}", flush=True)
    except Exception as e:
        print(f"CAUGHT ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
