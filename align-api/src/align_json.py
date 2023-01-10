import json
import requests
import sys

if len(sys.argv) < 4:
    print(f"Usage: python align_json.py <youtube_url> <json_file_path> <langage_code>")
    quit()

with open(sys.argv[2]) as f:
    data = json.load(f)

url = "http://0.0.0.0:8000/align_json"

payload = json.dumps({"srt": data, "url": sys.argv[1], "language": sys.argv[3]})
headers = {"Content-Type": "application/json"}

response = requests.request("POST", url, headers=headers, data=payload)

print(response.json)
