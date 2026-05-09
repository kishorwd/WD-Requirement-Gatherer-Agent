import os
import sys

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.story_generator import load_prompt as load_story_prompt
from core.post_meeting_analyzer import load_prompt as load_post_meeting_prompt
from core.briefing_generator import load_prompt as load_briefing_prompt
from core.scope_gap_analyzer import load_prompt as load_scope_prompt

def test_prompts():
    print("--- Testing Prompt Loading ---")
    
    prompts_to_test = [
        ("Story Generator", "story_generator.md", load_story_prompt),
        ("MoM Generator", "mom_generator.md", load_post_meeting_prompt),
        ("Speaker Extraction", "speaker_extraction.md", load_post_meeting_prompt),
        ("Brief Overview", "brief_overview.md", load_briefing_prompt),
        ("Scope Analyzer", "requirement_scope_analyzer.md", load_scope_prompt),
    ]
    
    success_count = 0
    for name, filename, loader in prompts_to_test:
        try:
            content = loader(filename)
            print(f"[SUCCESS] {name}: Loaded {len(content)} characters.")
            success_count += 1
        except Exception as e:
            print(f"[FAILED] {name} ({filename}): {str(e)}")
            
    print(f"\nSummary: {success_count}/{len(prompts_to_test)} prompts loaded successfully.")

if __name__ == "__main__":
    test_prompts()
