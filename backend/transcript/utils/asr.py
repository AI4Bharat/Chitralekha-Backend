# Automatic Speech Recognition
## Utility Functions
import traceback
import requests
import logging
from config import asr_url, english_asr_url, dhruva_key
import subprocess
import json


def make_asr_api_call(url, lang, vad_level=3, chunk_size=10):
    json_data = json.dumps(
        {"url": url, "vad_level": vad_level, "chunk_size": chunk_size, "language": lang}
    )
    json_data = {
        "config": {
            "serviceId": "ai4bharat/whisper-medium-en--gpu--t4",
            "language": {"sourceLanguage": "en"},
            "transcriptionFormat": {"value": "srt"},
        },
        "audio": [{"audioUri": "https://www.youtube.com/watch?v=SCVAAumFsLQ"}],
    }
    # request_url = asr_url
    # if lang == "en":
    #    logging.info("Calling another instance for English video.%s", url)
    #    request_url = english_asr_url
    logging.info("Request to ASR API send %s")
    print("hhhhhhhhhhhhhyyyyyyyyyyy")
    response = requests.post(
        "https://api.dhruva.ai4bharat.org/services/inference/asr",
        headers={"authorization": dhruva_key},
        json=json_data,
    )
    print("rrrrrrrrr")
    print(response.json()["output"])
    return response.json()


def get_asr_supported_languages():
    request_url = "http://216.48.182.174:5000/supported_languages"
    response = requests.get(url=request_url)
    response_data = response.json()
    # response_data = {"English":"en"}
    # response_data = {"English":"en","Bengali":"bn","Gujarati":"gu","Hindi":"hi","Kannada":"kn","Malayalam":"ml","Marathi":"mr","Odia":"or","Punjabi":"pa","Sanskrit":"sa","Tamil":"ta","Telugu":"te","Urdu":"ur"}
    return response_data
