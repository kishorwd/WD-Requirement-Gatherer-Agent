import os
import asyncio
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

async def test_raw():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    
    print("Calling OpenAI directly...")
    try:
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "user", "content": "Hi, return a simple JSON array with one object: [{'test': 1}]"}
            ],
            temperature=0,
            max_tokens=100
        )
        print("Response received!")
        print(response.choices[0].message.content)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_raw())
