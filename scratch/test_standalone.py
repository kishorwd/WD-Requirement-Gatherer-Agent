import json
import asyncio
import os
import logging
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

PROMPT_TEMPLATE = """You are an expert Business Analyst. Your task is to analyze the following raw requirements and convert them into well-structured user stories.
Raw Requirements:
{requirements_text}

Return your response as ONLY valid JSON array."""

async def test_standalone():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    requirements = "1. Login with email. 2. Profile page."
    prompt = PROMPT_TEMPLATE.format(requirements_text=requirements)
    
    print("Calling DeepSeek...")
    response = await client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    print("Response received!")
    print(response.choices[0].message.content)

if __name__ == "__main__":
    asyncio.run(test_standalone())
