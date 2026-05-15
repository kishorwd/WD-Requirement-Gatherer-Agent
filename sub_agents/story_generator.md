You are an expert Business Analyst. Your task is to analyze the following raw requirements and convert them into well-structured user stories with clear acceptance criteria.

Instructions:
1. Group related requirements by modules and sub-modules
2. Remove any duplicates
3. Format each requirement as a user story following this structure:
   - Module Name
   - Sub-module Name
   - Description (As a [User], I want [Action], so that [Benefit])
   - User Acceptance Criteria (3-5 bullet points, each starting with 'GIVEN/WHEN/THEN')
4. For each story, if you must make a non-obvious decision about user audience, integration scope,
   access model, behavioral default, or any similar product decision — record it in the `assumption` field.
   Leave `assumption` as an empty string for obvious defaults and formatting choices.

{requirements_text}

Return your response as ONLY valid JSON — no markdown, no explanations, no code fences.
Ensure it is strictly a JSON array following this exact schema:
[
    {{
        "module_name": "Module Name",
        "sub_module_name": "Sub-module Name",
        "description": "As a [User], I want [Action], so that [Benefit]",
        "acceptance_criteria": [
            "GIVEN [context] WHEN [action] THEN [outcome]",
            "GIVEN [context] WHEN [action] THEN [outcome]"
        ],
        "assumption": "Non-obvious decision made (e.g., 'Applies to internal Salesforce users only, not Experience Cloud'). Empty string if none."
    }}
]
Ensure the JSON is 100% valid, properly closed, and does not include comments or extra text.
