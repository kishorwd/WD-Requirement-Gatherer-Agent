You extract ONLY human speaker names from meeting transcripts.
Return STRICT JSON with a single key 'speakers' containing an array of distinct names.
Guidelines: Names are 1-3 words, capitalized properly. Exclude roles/titles (e.g., 'Manager'), exclude generic words, timestamps, and acronyms. If unsure, omit.
CRITICAL: If a speaker is referred to with both first and last name, return the FULL multi-word name (e.g., 'Priya Sharma'), not split parts.

Transcript:
{transcript}

Output JSON schema (no prose, no code fences): {{"speakers": ["Name", ...]}}
