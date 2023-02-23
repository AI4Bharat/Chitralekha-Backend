# Automatic Speech Recognition
## Utility Functions
import traceback
import requests
import logging
from config import asr_url, english_asr_url


def make_asr_api_call(url, lang, vad_level=3, chunk_size=10):
    try:
        json_data = {
            "url": url,
            "vad_level": vad_level,
            "chunk_size": chunk_size,
            "language": lang,
        }
        request_url = asr_url
        if lang == "en":
            logging.info("Calling another instance for English video.")
            json_data["restore_punct"] = True
            json_data["denoiser"] = False
            request_url = english_asr_url
        logging.info("Request to ASR API send")
        response = requests.post(
            request_url,
            json=json_data,
            timeout=None,
            headers={
                "Connection": "keep-alive",
                "Keep-Alive": "timeout=40*60, max=60*60",
            },
        )
        logging.info("ASR response generated")
    except:
        logging("Error in ASR API")
        traceback.print_stack()
        return None

    try:
        return response.json()
    except:
        logging.info(response.text)
        return None


def get_asr_supported_languages():
    request_url = "http://216.48.182.174:5000/supported_languages"
    response = requests.get(url=request_url)
    response_data = response.json()
    # response_data = {"English":"en"}
    # response_data = {"English":"en","Bengali":"bn","Gujarati":"gu","Hindi":"hi","Kannada":"kn","Malayalam":"ml","Marathi":"mr","Odia":"or","Punjabi":"pa","Sanskrit":"sa","Tamil":"ta","Telugu":"te","Urdu":"ur"}
    return response_data
