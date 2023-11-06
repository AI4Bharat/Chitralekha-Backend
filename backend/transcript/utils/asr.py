# Automatic Speech Recognition
## Utility Functions
import traceback
import requests
from config import (
    english_asr_url,
    indic_asr_url,
    dhruva_key,
    service_id_hindi,
    service_id_indo_aryan,
    service_id_dravidian,
)
import subprocess
import json


def make_asr_api_call(url, lang, vad_level=3, chunk_size=10):
    json_data = json.dumps(
        {"url": url, "vad_level": vad_level, "chunk_size": chunk_size, "language": lang}
    )
    if lang == "en":
        request_url = english_asr_url
        try:
            curl_request = subprocess.run(
                [
                    "curl",
                    "-X",
                    "POST",
                    "-d",
                    json_data,
                    "-H",
                    "Keep-Alive: timeout=40*60,max=60*60",
                    "-H",
                    "Content-Type: application/json",
                    request_url,
                ],
                capture_output=True,
            )
            output = curl_request.stdout.decode()
            return eval(output)
        except:
            traceback.print_stack()
            return None
    else:
        if lang == "hi":
            service_id = service_id_hindi
        elif lang in ["bn", "gu", "mr", "or", "pa", "sa", "ur"]:
            service_id = service_id_indo_aryan
        elif lang in ["kn", "ml", "ta", "te"]:
            service_id = service_id_dravidian
        else:
            return None

        json_data = {
            "config": {
                "serviceId": service_id,
                "language": {"sourceLanguage": lang},
                "transcriptionFormat": {"value": "srt"},
                "postProcessors": ["itn", "punctuation"],
            },
            "audio": [{"audioUri": url}],
        }
        try:
            response = requests.post(
                indic_asr_url,
                headers={"authorization": dhruva_key},
                json=json_data,
            )
            return response.json()["output"][0]["source"]
        except:
            print("No response received")
