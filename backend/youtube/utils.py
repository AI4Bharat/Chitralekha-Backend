import requests
from uuid import UUID
import json
from azure.storage.blob import BlobServiceClient
import logging
from config import (
    connection_string,
    container_name,
)
from pydub import AudioSegment
from datetime import datetime, date, timedelta
import os
import wave
import base64
from datetime import timedelta
import webvtt
from io import StringIO
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError
from yt_dlp.extractor import get_info_extractor
from django.http import HttpRequest
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_audioclips
from mutagen.wave import WAVE
import numpy
import sys
from mutagen.mp3 import MP3
import numpy as np
from pympler.asizeof import asizeof
from rest_framework import status
import math
from pydub.effects import speedup
from pydub import AudioSegment
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def uploadToBlobStorage(file_name, payload):
    file_temp_name = os.path.join(BASE_DIR / "temporary_video_audio_storage", file_name)

    with open(file_temp_name, "w") as outfile:
        outfile.write(payload)

    blob_service_client = BlobServiceClient.from_connection_string(connection_string)

    blob_client_json = blob_service_client.get_blob_client(
        container=container_name, blob=file_temp_name.split("/")[-1]
    )
    with open(file_temp_name, "rb") as data:
        try:
            blob_client_json.delete_blob()
            logging.info("Old srt payload deleted successfully!")
            blob_client_json.upload_blob(data)
            logging.info("New srt payload successfully!")
            blob_url = blob_client_json.url
            return blob_url

        except Exception as e:
            logging.info("This srt payload can't be uploaded")


def deleteFromBlobStorage(file_name):
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)

    blob_client_json = blob_service_client.get_blob_client(
        container=container_name, blob=file_name
    )

    try:
        blob_client_json.delete_blob()
        logging.info("Old srt payload deleted successfully!")
        return True

    except Exception as e:
        logging.info("This srt payload can't be deleted")
        return False
