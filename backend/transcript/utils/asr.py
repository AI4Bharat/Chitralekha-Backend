# Automatic Speech Recognition
## Utility Functions
import requests


def make_asr_api_call(url, lang, vad_level=3, chunk_size=10):
    try:
        json_data = {
            "url": url,
            "vad_level": vad_level,
            "chunk_size": chunk_size,
            "language": lang,
        }
        request_url = "http://216.48.182.174:5000/transcribe"
        response = requests.post(request_url, json=json_data)
    except:
        traceback.print_stack()
        return None

    try:
        return response.json()
    except:
        print(response.text)
        return None


def get_asr_supported_languages():
    request_url = "http://216.48.182.174:5000/supported_languages"
    response = requests.get(url=request_url)
    response_data = response.json()
    # response_data = {"English":"en"}
    # response_data = {"English":"en","Bengali":"bn","Gujarati":"gu","Hindi":"hi","Kannada":"kn","Malayalam":"ml","Marathi":"mr","Odia":"or","Punjabi":"pa","Sanskrit":"sa","Tamil":"ta","Telugu":"te","Urdu":"ur"}
    return response_data
