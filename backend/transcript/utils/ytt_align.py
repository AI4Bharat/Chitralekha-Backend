## Utility Functions
import traceback
import requests
import logging
import subprocess
import json
from config import align_json_url
from utils.storage_factory import get_storage_provider
import logging
from config import (
    storage_account_key,
    connection_string,
    container_name,
)
import datetime
import os
import subprocess


def align_json_api(transcript_obj):
    final_payload = []
    payload = transcript_obj.payload
    for index in range(len(transcript_obj.payload["payload"])):
        if "text" in transcript_obj.payload["payload"][index]:
            final_payload.append(transcript_obj.payload["payload"][index])
    json_data = {
        "srt": {"payload": final_payload},
        "url": transcript_obj.video.url,
        "language": transcript_obj.video.language,
    }
    try:
        logging.info("Sending Request to ALign Json API")
        curl_request = subprocess.run(
            [
                "curl",
                "-X",
                "POST",
                "-d",
                json.dumps(json_data),
                "-H",
                "Keep-Alive: timeout=40*60,max=60*60",
                "-H",
                "Content-Type: application/json",
                align_json_url,
            ],
            capture_output=True,
        )
        output = curl_request.stdout.decode()
        logging.info("Response received from Align Json API")
        return json.loads(output)
    except:
        logging.info("Error in Align Json API %s", transcript_obj.video.url)
        return None


def download_ytt_from_azure(file_name):
    storage = get_storage_provider()

    remote_object_name = file_name
    local_destination_path = file_name

    storage.download(remote_object_name, local_destination_path)


def upload_ytt_to_azure(transcript_obj, file_name):
    storage = get_storage_provider()

    local_file = file_name
    remote_file = file_name
    
    file_exists = storage.exists(remote_file)
    
    url = storage.upload(local_file, remote_file)
    
    if not file_exists:
        logging.info(url)
        transcript_obj.payload["ytt_azure_url"] = url
        transcript_obj.save()
    else:
        logging.info(url)