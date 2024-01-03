from transcript.models import Transcript
from celery import shared_task
from backend.celery import celery_app
import json
import logging
from azure.storage.blob import BlobServiceClient
import logging
from config import (
    storage_account_key,
    connection_string,
    container_name,
    app_name,
)
from json_to_ytt import *
import os
from .utils.ytt_align import *


@celery_app.task(queue="ytt")
def celery_align_json(transcript_id):
    transcript_obj = Transcript.objects.filter(id=transcript_id).first()
    if transcript_obj is not None:
        if (
            transcript_obj.payload != None
            and "payload" in transcript_obj.payload.keys()
            and len(transcript_obj.payload["payload"]) > 0
            and "ytt_azure_url" not in transcript_obj.payload.keys()
        ):
            try:
                data = align_json_api(transcript_obj)
            except:
                print("Error in calling align json API")
            time_now = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
            file_name = (
                "{}_Video_{}_{}".format(app_name, transcript_obj.video.id, time_now)
                + ".ytt"
            )
            try:
                ytt_genorator(data, file_name, prev_line_in=0, mode="data")
                upload_ytt_to_azure(transcript_obj, file_name)
            except:
                print("Error in converting ytt to json.")
            os.remove(file_name)
