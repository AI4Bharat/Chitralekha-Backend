# Automatic Speech Recognition
## Utility Functions
import traceback
import requests
import logging
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
        logging.info("Calling another instance for English video.%s", url)
        logging.info("Request to ASR API sent %s", request_url)
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
            logging.info("Error in ASR API")
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
            },
            "audio": [{"audioUri": url}],
        }
        logging.info("Sending request to indic model.")
        try:
            response = requests.post(
                indic_asr_url,
                headers={"authorization": dhruva_key},
                json=json_data,
            )
            logging.info("Response Received")
            return response.json()["output"][0]["source"]
        except:
            logging.info("Error in Indic ASR API")


def get_asr_supported_languages():
    request_url = "http://216.48.182.174:5000/supported_languages"
    response = requests.get(url=request_url)
    response_data = response.json()
    # response_data = {"English":"en"}
    # response_data = {"English":"en","Bengali":"bn","Gujarati":"gu","Hindi":"hi","Kannada":"kn","Malayalam":"ml","Marathi":"mr","Odia":"or","Punjabi":"pa","Sanskrit":"sa","Tamil":"ta","Telugu":"te","Urdu":"ur"}
    return response_data
