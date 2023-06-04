from transcript.models import Transcript
from celery import shared_task
import json
import logging
from azure.storage.blob import BlobServiceClient
import logging
from config import (
    storage_account_key,
    connection_string,
    container_name,
)
from json_to_ytt import *
import os
from .utils.ytt_align import *


@shared_task()
def celery_align_json(transcript_id):
    transcript_obj = Transcript.objects.filter(id=transcript_id).first()
    if transcript_obj is not None:
        if (
            transcript_obj.payload != None
            and "payload" in transcript_obj.payload.keys()
            and len(transcript_obj.payload["payload"]) > 0
            and "ytt_azure_url" not in transcript_obj.payload.keys()
        ):
            data = align_json_api(transcript_obj)
            time_now = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
            file_name = (
                "Chitralekha_Video_{}_{}".format(transcript_obj.video.id, time_now)
                + ".ytt"
            )
            ytt_genorator(data, file_name, prev_line_in=0, mode="data")
            upload_ytt_to_azure(transcript_obj, file_name)
