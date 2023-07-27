## Utility Functions
import traceback
import requests
import logging
import subprocess
import json
from config import align_json_url
from azure.storage.blob import BlobServiceClient
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
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    blob_client = blob_service_client.get_blob_client(
        container=container_name, blob=file_name
    )
    with open(file=file_name, mode="wb") as sample_blob:
        download_stream = blob_client.download_blob()
        sample_blob.write(download_stream.readall())


def upload_ytt_to_azure(transcript_obj, file_name):
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    blob_client_json = blob_service_client.get_blob_client(
        container=container_name, blob=file_name
    )
    with open(file_name, "rb") as data:
        if not blob_client_json.exists():
            blob_client_json.upload_blob(data)
            logging.info(blob_client_json.url)
            transcript_obj.payload["ytt_azure_url"] = blob_client_json.url
            transcript_obj.save()
        else:
            blob_client_json.delete_blob()
            blob_client_json.upload_blob(data)
            logging.info(blob_client_json.url)
