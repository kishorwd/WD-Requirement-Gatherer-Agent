import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("DEEPSEEK_API_KEY")

url = "https://api.deepseek.com/models"
headers = {"Authorization": f"Bearer {api_key}"}
response = requests.get(url, headers=headers)

if response.status_code == 200:
    models = response.json().get("data", [])
    result = []
    for m in models:
        result.append(m['id'])
    
    with open("valid_models.json", "w") as f:
        json.dump(result, f, indent=2)
else:
    print(f"Error: {response.status_code}")
