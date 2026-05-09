import json
import asyncio
import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

async def test_standalone():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    requirements = "1. Login with email. 2. Profile page."
    # Use the pro model
    model = os.getenv("LLM_MODEL_PRO", "deepseek-v4-pro")
    
    print(f"Calling DeepSeek ({model})...")
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Return a JSON array with two user stories for: " + requirements}],
            temperature=0.2,
        )
        print("Response received!")
        print(response.choices[0].message.content)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_standalone())
