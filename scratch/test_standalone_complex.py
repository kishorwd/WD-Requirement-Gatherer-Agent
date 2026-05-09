import json
import asyncio
import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

PROMPT_TEMPLATE = """You are an expert Business Analyst. Your task is to analyze the following raw requirements and convert them into well-structured user stories with clear acceptance criteria.

Instructions:
1. Group related requirements by modules and sub-modules
2. Remove any duplicates
3. Format each requirement as a user story following this structure:
   - Module Name
   - Sub-module Name
   - Description (As a [User], I want [Action], so that [Benefit])
   - User Acceptance Criteria (3-5 bullet points, each starting with 'GIVEN/WHEN/THEN')

Raw Requirements:
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
        ]
    }}
]"""

async def test_standalone_complex():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    requirements = "1. Login with email. 2. Profile page. 3. Password reset."
    model = os.getenv("LLM_MODEL_PRO", "deepseek-v4-pro")
    
    print(f"Calling DeepSeek ({model}) with complex prompt...")
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": PROMPT_TEMPLATE.format(requirements_text=requirements)}],
            temperature=0.2,
        )
        print("Response received!")
        print(response.choices[0].message.content)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_standalone_complex())
