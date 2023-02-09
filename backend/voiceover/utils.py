import requests
from uuid import UUID
import json
from azure.storage.blob import BlobServiceClient
import logging


### Utility Functions ###
def validate_uuid4(val):
    try:
        UUID(str(val))
        return True
    except ValueError:
        return False


storage_account_key = "+8RJ9apUdZII//sIXG8Y7Y4FvS5nkC3g8fS/AAEHICreptAdUTnHsPHC9vWYvtuIzXZwh1vo2n+0+ASt9Ew17w=="
connection_string = "DefaultEndpointsProtocol=https;AccountName=chitralekhadev;AccountKey=+8RJ9apUdZII//sIXG8Y7Y4FvS5nkC3g8fS/AAEHICreptAdUTnHsPHC9vWYvtuIzXZwh1vo2n+0+ASt9Ew17w==;EndpointSuffix=core.windows.net"
container_name = "multimedia"


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


def get_tts_output(translation, gender, target_language):
    json_data = {
        "input": [{"source": translation.payload["payload"]}],
        "config": {"language": {"sourceLanguage": target_language}, "gender": gender},
    }

    try:
        response = requests.post(
            "https://tts-api.ai4bharat.org/",
            json=json_data,
        )

        tts_output = response.json()["audio"]

        # Collect the translated sentences
        return tts_output

    except Exception as e:
        return str(e)


def generate_voiceover_payload(translation, target_language, list_compare_sources):
    payloads = {}
    translation_output = ""
    for translation in translation["payload"]:
        translation_output.join(translation["target_text"])
    if "MACHINE_GENERATED" in list_compare_sources:
        voiceover_machine_generated = get_tts_output(
            translation_output, gender, target_language
        )
        payloads["MACHINE_GENERATED"] = {"payload": voiceover_machine_generated}

    if "MANUALLY_CREATED" in list_compare_sources:
        payload = []
        for voice_over in translation.payload["payload"]:
            voice_over["voice_over"] = ""
            payload.append(voice_over)
        payloads["MANUALLY_CREATED"] = {"payload": payload}
    return payloads
