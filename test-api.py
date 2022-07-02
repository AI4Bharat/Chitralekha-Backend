import json
from shutil import ExecError 
import requests

def make_asr_api_call(url, lang, vad_level=2, chunk_size=10):
    try:
        raise Exception
        headers = {
            'accept': 'application/json',
        }

        json_data = {
            'url': 'https://www.youtube.com/watch?v=lTTajzrSkCw',
            'vad_level': 2,
            'chunk_size': 10,
            'language': 'en',
        }

        response = requests.post('http://216.48.182.174:5000/transcribe', headers=headers, json=json_data)
        print(response.text)
        return json.loads(response.content)

    except Exception as e:
        return "Didn't work"

make_asr_api_call(url="https://www.youtube.com/watch?v=lTTajzrSkCw", lang="en", vad_level=2, chunk_size=10)