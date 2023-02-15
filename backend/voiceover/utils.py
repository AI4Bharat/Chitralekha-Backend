import requests
from uuid import UUID
import json
from azure.storage.blob import BlobServiceClient
import logging
from config import (
    tts_url,
    storage_account_key,
    connection_string,
    container_name,
    voice_over_payload_offset_size,
)

### Utility Functions ###
def validate_uuid4(val):
    try:
        UUID(str(val))
        return True
    except ValueError:
        return False


def uploadToBlobStorage(file_path):
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    blob_client = blob_service_client.get_blob_client(
        container=container_name, blob=file_path.split("/")[-1]
    )
    with open(file_path, "rb") as data:
        try:
            blob_client.upload_blob(data)
        except Exception as e:
            logging.info("This file already exists")
            blob_data = blob_client.download_blob()
            data = blob_data.readall()
            # print(data)


def get_tts_output(tts_input, target_language, gender="male"):
    json_data = {
        "input": tts_input,
        "config": {"language": {"sourceLanguage": target_language}, "gender": gender},
    }

    logging.info("Calling TTS API")
    try:
        response = requests.post(
            tts_url,
            json=json_data,
        )
        tts_output = response.json()

        # Collect the translated sentences
        return tts_output

    except Exception as e:
        logging.info("Error in TTS API %s", str(e))
        return str(e)


def generate_voiceover_payload(translation_payload, target_language):
    tts_input = []
    output = [0] * voice_over_payload_offset_size
    pre_generated_audio_indices = []
    post_generated_audio_indices = []
    post_generated_audio_indices = []

    for index, (translation_text, audio, call_tts) in enumerate(translation_payload):
        if call_tts:
            if len(translation_text) > 1 or translation_text != " ":
                tts_input.append({"source": translation_text})
                post_generated_audio_indices.append(index)
            else:
                output[index] = ""
        else:
            pre_generated_audio_indices.append(index)
            output[index] = (translation_text, audio)

    if len(tts_input) > 0:
        voiceover_machine_generated = get_tts_output(tts_input, target_language)
        for voice_over in voiceover_machine_generated["audio"]:
            ind = post_generated_audio_indices.pop(0)
            output[ind] = (translation_payload[ind][0], voice_over)
    return output
