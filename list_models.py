import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("DEEPSEEK_API_KEY")

url = "https://api.deepseek.com/models"
headers = {"Authorization": f"Bearer {api_key}"}
response = requests.get(url, headers=headers)

if response.status_code == 200:
    models = response.json().get("data", [])
    for m in models:
        print(f"ID: {m['id']}")
        print(f"Owned by: {m.get('owned_by')}")
        print("---")
else:
    print(f"Error: {response.status_code}")
    print(response.text)
