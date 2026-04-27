import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
response = requests.get(url)

if response.status_code == 200:
    models = response.json().get("models", [])
    result = []
    for m in models:
        result.append(m['name'])
    
    with open("valid_models.json", "w") as f:
        json.dump(result, f, indent=2)
else:
    print(f"Error: {response.status_code}")
