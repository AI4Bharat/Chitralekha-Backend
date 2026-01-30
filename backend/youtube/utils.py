import requests
from uuid import UUID
import json
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


def uploadToLocalDir(file_name, payload):
    file_temp_name = os.path.join(BASE_DIR / "temporary_video_audio_storage", file_name)

    try:
        with open(file_temp_name, "w") as outfile:
            outfile.write(payload)
            return file_temp_name
    except Exception as e:
        logging.info("There is issue with srt file creation")
