import requests
from uuid import UUID
import uuid
import json
from azure.storage.blob import BlobServiceClient
import logging
from config import (
    storage_account_key,
    connection_string,
    container_name,
    voice_over_payload_offset_size,
    dhruva_key,
    misc_tts_url,
    indo_aryan_tts_url,
    dravidian_tts_url,
    DEFAULT_SPEAKER,
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
from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_subclip
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
from django.conf import settings
from django.core.mail import send_mail, EmailMultiAlternatives
import operator
import urllib.parse
import shutil
from utils.email_template import send_email_template
import subprocess

def get_tts_url(language):
    if language in ["brx", "en", "mni"]:
        return misc_tts_url
    elif language in ["as", "gu", "hi", "mr", "or", "pa", "bn"]:
        return indo_aryan_tts_url
    elif language in ["kn", "ml", "ta", "te"]:
        return dravidian_tts_url
    else:
        return None


### Utility Functions ###
def validate_uuid4(val):
    try:
        UUID(str(val))
        return True
    except ValueError:
        return False


def download_from_azure_blob(file_path):
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    encoded_file_path = file_path.split("/")[-1]
    encoded_url_path = urllib.parse.unquote(encoded_file_path)
    blob_client = blob_service_client.get_blob_client(
        container=container_name, blob=encoded_url_path
    )
    with open(file=file_path.split("/")[-1], mode="wb") as sample_blob:
        download_stream = blob_client.download_blob()
        sample_blob.write(download_stream.readall())


def upload_video(file_path):
    full_path = file_path + ".mp4"
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    blob_client = blob_service_client.get_blob_client(
        container=container_name, blob=file_path.split("/")[-1] + ".mp4"
    )
    with open(full_path, "rb") as data:
        try:
            if not blob_client.exists():
                blob_client.upload_blob(data)
                logging.info("Video uploaded successfully!")
                logging.info(blob_client.url)
            else:
                blob_client.delete_blob()
                logging.info("Old Video deleted successfully!")
                blob_client.upload_blob(data)
                logging.info("New video uploaded successfully!")
        except Exception as e:
            logging.info("This video can't be uploaded")
    return blob_client.url


def upload_json(file_path, voice_over_obj):
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    voice_over_payload = voice_over_obj.payload
    json_object = json.dumps(voice_over_payload)

    with open(file_path.split("/")[-1] + ".json", "w") as outfile:
        outfile.write(json_object)

    blob_client_json = blob_service_client.get_blob_client(
        container=container_name, blob=file_path.split("/")[-1] + ".json"
    )

    with open(file_path.split("/")[-1] + ".json", "rb") as data:
        try:
            if not blob_client_json.exists():
                blob_client_json.upload_blob(data)
                logging.info("Voice Over payload uploaded successfully!")
                logging.info(blob_client_json.url)
            else:
                blob_client_json.delete_blob()
                logging.info("Old Voice Over payload deleted successfully!")
                blob_client_json.upload_blob(data)
                logging.info("New Voice Over payload successfully!")
        except Exception as e:
            logging.info("This Voice Over payload can't be uploaded")


def uploadToBlobStorage(file_path, voice_over_obj):
    blob_client_url = None
    if voice_over_obj.video.project_id.video_integration == True:
        blob_client_url = upload_video(file_path)
        os.remove(file_path + ".mp4")
    upload_json(file_path, voice_over_obj)
    blob_client_audio_url = upload_audio_to_azure_blob(file_path, "", export=False)
    try:
        os.remove(file_path + "final.ogg")
        os.remove(file_path + "final.wav")
        os.remove(file_path + "final.flac")
    except:
        logging.info("Audios dont exists.")
    os.remove(file_path.split("/")[-1] + ".json")
    return blob_client_url, blob_client_audio_url


def upload_audio_to_azure_blob(file_path, export_type, export):
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    if export == False:
        AudioSegment.from_wav(file_path + "final.wav").export(
            file_path + "final.flac", format="flac"
        )
        full_path_audio = file_path + "final.flac"
        blob_client_audio = blob_service_client.get_blob_client(
            container=container_name, blob=file_path.split("/")[-1] + ".flac"
        )
    else:
        full_path_audio = file_path.replace(".flac", "") + "." + export_type
        blob_client_audio = blob_service_client.get_blob_client(
            container=container_name,
            blob=file_path.split("/")[-1].replace(".flac", "") + "." + export_type,
        )
    with open(full_path_audio, "rb") as data:
        try:
            if not blob_client_audio.exists():
                blob_client_audio.upload_blob(data)
                logging.info("Audio uploaded successfully!")
                logging.info(blob_client_audio.url)
            else:
                blob_client_audio.delete_blob()
                logging.info("Old Audio deleted successfully!")
                blob_client_audio.upload_blob(data)
                logging.info("New audio uploaded successfully!")
        except Exception as e:
            logging.info("This audio can't be uploaded")
    return blob_client_audio.url


def upload_zip_to_azure(zip_file_path):
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    blob_client_zip = blob_service_client.get_blob_client(
        container=container_name, blob=zip_file_path
    )
    with open(zip_file_path, "rb") as f:
        try:
            blob_client_zip.upload_blob(f)
            logging.info("Audio zip uploaded successfully!")
            logging.info(blob_client_zip.url)
        except Exception as e:
            logging.info("This audio_zip can't be uploaded")
    return blob_client_zip.url


def get_tts_output(tts_input, target_language, multiple_speaker, gender):
    logging.info("Calling TTS API")
    tts_url = get_tts_url(target_language)
    if tts_url is None:
        return {
            "message": "Error in TTS API. Target Language is not supported.",
            "status": status.HTTP_400_BAD_REQUEST,
        }
    tts_output = {}
    tts_output["audio"] = []
    count_errors = 0
    for sentence in tts_input:
        sentence_json_data = {
            "input": [sentence],
            "config": {
                "language": {"sourceLanguage": target_language},
                "gender": gender.lower(),
            },
        }
        sentence_response = requests.post(
            tts_url,
            headers={"authorization": dhruva_key},
            json=sentence_json_data,
        )
        if sentence_response.status_code != 200:
            logging.info("Error in TTS API %s", str(sentence_response.status_code))
            sentence_tts_output = {"audioContent": "", "audioUri": None}
            count_errors += 1
            tts_output["audio"].append(sentence_tts_output)
        else:
            sentence_tts_output = sentence_response.json()
            tts_output["audio"].append(sentence_tts_output["audio"][0])
    if count_errors == len(tts_input):
        return {
            "message": "Error in TTS API.",
            "status": status.HTTP_400_BAD_REQUEST,
        }
    return tts_output


def generate_tts_output(
    tts_input,
    target_language,
    translation,
    translation_obj,
    empty_sentences,
    generate_audio=True,
):
    if translation_obj.video.gender is None:
        gender = "MALE"
    else:
        gender = translation_obj.video.gender

    if not translation_obj.video.multiple_speaker and (
        translation_obj.video.speaker_info is None
        or len(translation_obj.video.speaker_info) == 0
    ):
        if generate_audio:
            tts_output = get_tts_output(
                tts_input,
                target_language,
                translation_obj.video.multiple_speaker,
                gender.lower(),
            )
            logging.info("output generated")
        else:
            tts_output = {"audio": [{"audioContent": ""} for _ in tts_input]}
    else:
        speakers_tts_input = group_speakers(tts_input)
        speaker_info = {
            speaker_info["id"]: speaker_info["gender"]
            for speaker_info in translation_obj.video.speaker_info
        }
        merged_tts_output = {"audio": []}
        list_indices = []
        for speaker_id, speaker_tts_input in speakers_tts_input.items():
            for ind in speaker_tts_input:
                list_indices.append(ind["index"])
            if generate_audio:
                speaker_tts_output = get_tts_output(
                    speaker_tts_input,
                    target_language,
                    translation_obj.video.multiple_speaker,
                    speaker_info[speaker_id],
                )
                if (
                    type(speaker_tts_output) != dict
                    or "audio" not in speaker_tts_output.keys()
                ):
                    return speaker_tts_output
                merged_tts_output["audio"].extend(speaker_tts_output["audio"])
            else:
                merged_tts_output["audio"].extend(
                    [{"audioContent": ""} for _ in speaker_tts_input]
                )

        if generate_audio:
            merged_tts_output["config"] = speaker_tts_output["config"]
            for input, output in zip(list_indices, merged_tts_output["audio"]):
                output["index"] = input
            tts_output = {
                "audio": sorted(
                    merged_tts_output["audio"], key=operator.itemgetter("index")
                )
            }
        else:
            tts_output = {
                "audio": [{"audioContent": "", "index": idx} for idx in list_indices]
            }

    if type(tts_output) != dict or "audio" not in tts_output.keys():
        return tts_output
    logging.info("Size of TTS output %s", str(asizeof(tts_output)))
    logging.info("Output from TTS generated")

    voiceover_payload = {"payload": {}}
    count = 0
    audio_not_generated = []

    for ind, text in enumerate(translation["payload"]):
        start_time = text["start_time"]
        end_time = text["end_time"]
        transcription_text = text["text"]
        logging.info("Starting time of this sentence %s", start_time)
        logging.info("Ending time of this sentence %s", end_time)
        logging.info("Sentence %s", text["target_text"])

        time_difference = (
            datetime.strptime(end_time, "%H:%M:%S.%f")
            - timedelta(
                hours=float(start_time.split(":")[0]),
                minutes=float(start_time.split(":")[1]),
                seconds=float(start_time.split(":")[-1]),
            )
        ).strftime("%H:%M:%S.%f")
        t_d = (
            float(time_difference.split(":")[0]) * 3600
            + float(time_difference.split(":")[1]) * 60
            + float(time_difference.split(":")[2])
        )

        if ind == len(translation["payload"]) - 1:
            original_video_duration = translation_obj.video.duration
            if not compare_time(str(original_video_duration) + str(".000"), end_time)[
                0
            ]:
                time_difference = (
                    datetime.strptime(
                        str(original_video_duration) + str(".000"), "%H:%M:%S.%f"
                    )
                    - timedelta(
                        hours=float(start_time.split(":")[0]),
                        minutes=float(start_time.split(":")[1]),
                        seconds=float(start_time.split(":")[-1]),
                    )
                ).strftime("%H:%M:%S.%f")
                t_d = (
                    float(time_difference.split(":")[0]) * 3600
                    + float(time_difference.split(":")[1]) * 60
                    + float(time_difference.split(":")[2])
                )

        if ind not in empty_sentences:
            logging.info("Count of audios saved %s", str(count))

            if generate_audio:
                wave_audio = "temp_" + str(ind) + ".wav"
                audio_decoded = base64.b64decode(
                    tts_output["audio"][count]["audioContent"]
                )
                if len(tts_output["audio"][count]["audioContent"]) > 100:
                    with open(wave_audio, "wb") as output_f:
                        output_f.write(audio_decoded)
                    logging.info(
                        "Length of received content %s",
                        str(len(tts_output["audio"][count]["audioContent"])),
                    )
                    audio = AudioFileClip(wave_audio)
                    wav_seconds = audio.duration
                    ogg_audio = "temp_" + str(ind) + ".ogg"
                    AudioSegment.from_wav(wave_audio).export(ogg_audio, format="ogg")
                    logging.info("Seconds of wave audio %s", str(wav_seconds))
                    audio = AudioFileClip(ogg_audio)
                    seconds = audio.duration
                    logging.info("Seconds of ogg audio %s", str(seconds))
                    adjust_audio(ogg_audio, t_d, -1)
                    encoded_audio = base64.b64encode(open(ogg_audio, "rb").read())
                    decoded_audio = encoded_audio.decode()
                    os.remove(ogg_audio)
                    os.remove(wave_audio)
                    voiceover_payload["payload"][str(count)] = {
                        "time_difference": t_d,
                        "start_time": start_time,
                        "end_time": end_time,
                        "text": text["target_text"],
                        "audio": {"audioContent": decoded_audio},
                        "audio_speed": 1,
                        "audio_generated": True,
                        "index": tts_output["audio"][count].get("index", 0),
                        "transcription_text": text["text"],
                    }
                    count += 1
                else:
                    audio_not_generated.append(
                        {
                            "page_number": ind,
                            "index": ind + 1,
                            "sentence": text["target_text"],
                            "reason": "TTS API Failed.",
                        }
                    )
                    voiceover_payload["payload"][str(count)] = {
                        "time_difference": t_d,
                        "start_time": start_time,
                        "end_time": end_time,
                        "text": text["target_text"],
                        "audio": {"audioContent": ""},
                        "audio_speed": 1,
                        "audio_generated": False,
                        "index": tts_output["audio"][count].get("index", 0),
                        "transcription_text": text["text"],
                    }
                    count += 1
            else:
                voiceover_payload["payload"][str(count)] = {
                    "time_difference": t_d,
                    "start_time": start_time,
                    "end_time": end_time,
                    "text": text["target_text"],
                    "audio": {"audioContent": ""},
                    "audio_speed": 1,
                    "audio_generated": False,
                    "index": ind,
                    "transcription_text": text["text"],
                }
                count += 1
        else:
            pass

    logging.info("Size of voiceover payload %s", str(asizeof(voiceover_payload)))
    logging.info("Size of combined audios %s", str(asizeof(voiceover_payload)))
    voiceover_payload["audio_not_generated"] = audio_not_generated
    voiceover_payload["empty_sentences"] = empty_sentences

    return voiceover_payload


# def generate_tts_output(
#     tts_input, target_language, translation, translation_obj, empty_sentences
# ):
# if translation_obj.video.gender == None:
#     gender = "MALE"
# else:
#     gender = translation_obj.video.gender
# if translation_obj.video.multiple_speaker == False and (
#     translation_obj.video.speaker_info == None
#     or len(translation_obj.video.speaker_info) == 0
# ):
#     tts_output = get_tts_output(
#         tts_input,
#         target_language,
#         translation_obj.video.multiple_speaker,
#         gender.lower(),
#     )
#     logging.info("output generated")
# else:
#     speakers_tts_input = group_speakers(tts_input)
#     speaker_info = {
#         speaker_info["id"]: speaker_info["gender"]
#         for speaker_info in translation_obj.video.speaker_info
#     }
#     merged_tts_output = {"audio": []}
#     list_indices = []
#     for speaker_id, speaker_tts_input in speakers_tts_input.items():
#         for ind in speaker_tts_input:
#             list_indices.append(ind["index"])
#         speaker_tts_output = get_tts_output(
#             speaker_tts_input,
#             target_language,
#             translation_obj.video.multiple_speaker,
#             speaker_info[speaker_id],
#         )
#         if (
#             type(speaker_tts_output) != dict
#             or "audio" not in speaker_tts_output.keys()
#         ):
#             return speaker_tts_output
#         merged_tts_output["audio"].extend(speaker_tts_output["audio"])
#     merged_tts_output["config"] = speaker_tts_output["config"]
#     for input, output in zip(list_indices, merged_tts_output["audio"]):
#         output["index"] = input
#     tts_output = {}
#     tts_output["audio"] = sorted(
#         merged_tts_output["audio"], key=operator.itemgetter("index")
#     )
# if type(tts_output) != dict or "audio" not in tts_output.keys():
#     return tts_output
# logging.info("Size of TTS output %s", str(asizeof(tts_output)))
# logging.info("Output from TTS generated")
# voiceover_payload = {"payload": {}}
# count = 0
# payload_size = 0
# payload_size_encoded = 0
# audio_not_generated = []
# for ind, text in enumerate(translation["payload"]):
#     start_time = text["start_time"]
#     end_time = text["end_time"]
#     logging.info("Starting time of this sentence %s", start_time)
#     logging.info("Ending time of this sentence %s", end_time)
#     logging.info("Sentence %s", text["target_text"])
#     time_difference = (
#         datetime.strptime(end_time, "%H:%M:%S.%f")
#         - timedelta(
#             hours=float(start_time.split(":")[0]),
#             minutes=float(start_time.split(":")[1]),
#             seconds=float(start_time.split(":")[-1]),
#         )
#     ).strftime("%H:%M:%S.%f")
#     t_d = (
#         float(time_difference.split(":")[0]) * 3600
#         + float(time_difference.split(":")[1]) * 60
#         + float(time_difference.split(":")[2])
#     )
#     if ind == len(translation["payload"]) - 1:
#         original_video_duration = translation_obj.video.duration
#         if not compare_time(str(original_video_duration) + str(".000"), end_time)[
#             0
#         ]:
#             time_difference = (
#                 datetime.strptime(
#                     str(original_video_duration) + str(".000"), "%H:%M:%S.%f"
#                 )
#                 - timedelta(
#                     hours=float(start_time.split(":")[0]),
#                     minutes=float(start_time.split(":")[1]),
#                     seconds=float(start_time.split(":")[-1]),
#                 )
#             ).strftime("%H:%M:%S.%f")
#             t_d = (
#                 float(time_difference.split(":")[0]) * 3600
#                 + float(time_difference.split(":")[1]) * 60
#                 + float(time_difference.split(":")[2])
#             )

#     if ind not in empty_sentences:
#         logging.info("Count of audios saved %s", str(count))
#         wave_audio = "temp_" + str(ind) + ".wav"

#         audio_decoded = base64.b64decode(tts_output["audio"][count]["audioContent"])
#         if len(tts_output["audio"][count]["audioContent"]) > 100:
#             with open(wave_audio, "wb") as output_f:
#                 output_f.write(audio_decoded)
#             logging.info(
#                 "Length of received content %s",
#                 str(len(tts_output["audio"][count]["audioContent"])),
#             )
#             audio = AudioFileClip(wave_audio)
#             wav_seconds = audio.duration
#             ogg_audio = "temp_" + str(ind) + ".ogg"
#             AudioSegment.from_wav(wave_audio).export(ogg_audio, format="ogg")
#             logging.info("Seconds of wave audio %s", str(wav_seconds))
#             audio = AudioFileClip(ogg_audio)
#             seconds = audio.duration
#             logging.info("Seconds of ogg audio %s", str(seconds))
#             adjust_audio(ogg_audio, t_d, -1)
#             encoded_audio = base64.b64encode(open(ogg_audio, "rb").read())
#             decoded_audio = encoded_audio.decode()
#             os.remove(ogg_audio)
#             os.remove(wave_audio)
#             payload_size = payload_size + asizeof(decoded_audio)
#             logging.info("Payload size %s", str(asizeof(decoded_audio)))
#             logging.info("Index %s", str(ind))
#             voiceover_payload["payload"][str(count)] = {
#                 "time_difference": t_d,
#                 "start_time": start_time,
#                 "end_time": end_time,
#                 "text": text["target_text"],
#                 "audio": {"audioContent": decoded_audio},
#                 "audio_speed": 1,
#                 "audio_generated": True,
#                 "index": tts_output["audio"][count].get("index", 0),
#             }
#             count = count + 1
#         else:
#             audio_not_generated.append(
#                 {
#                     "page_number": ind,
#                     "index": ind + 1,
#                     "sentence": text["target_text"],
#                     "reason": "TTS API Failed.",
#                 }
#             )
#             voiceover_payload["payload"][str(count)] = {
#                 "time_difference": t_d,
#                 "start_time": start_time,
#                 "end_time": end_time,
#                 "text": text["target_text"],
#                 "audio": {"audioContent": ""},
#                 "audio_speed": 1,
#                 "audio_generated": False,
#                 "index": tts_output["audio"][count].get("index", 0),
#             }
#             count += 1
#     else:
#         pass
# logging.info("Size of voiceover payload %s", str(asizeof(voiceover_payload)))
# logging.info("Size of combined audios %s", str(payload_size))
# voiceover_payload["audio_not_generated"] = audio_not_generated
# voiceover_payload["empty_sentences"] = empty_sentences
# return voiceover_payload


def equal_sentences(ind, previous_sentence, current_sentence, delete_indices):
    if "text" not in current_sentence:
        delete_indices.append(ind)
    elif "text" not in previous_sentence:
        pass
    elif (
        get_original_duration(
            previous_sentence["start_time"], current_sentence["start_time"]
        )
        == 0
        and get_original_duration(
            previous_sentence["end_time"], current_sentence["end_time"]
        )
        == 0
    ):
        delete_indices.append(ind)
    else:
        pass


def get_bad_sentences(translation_obj, target_language):
    tts_input = []
    empty_sentences = []
    delete_indices = []
    translation = translation_obj.payload
    for ind, text in enumerate(translation["payload"]):
        if ind != 0:
            equal_sentences(ind, translation["payload"][ind - 1], text, delete_indices)

    problem_sentences = []
    delete_indices.reverse()
    for index in delete_indices:
        translation["payload"].pop(index)
    logging.info("delete_indices %s", str(delete_indices))
    translation_obj.save()
    for ind, text in enumerate(translation["payload"]):
        if not compare_time(text["end_time"], text["start_time"])[0]:
            problem_sentences.append(
                {
                    "index": (ind % 50) + 1,
                    "page_number": (ind // 50) + 1,
                    "start_time": text["start_time"],
                    "end_time": text["end_time"],
                    "text": text["text"],
                    "target_text": text["target_text"],
                }
            )
        if (
            ind != 0
            and ind < len(translation["payload"])
            and compare_time(
                translation["payload"][ind - 1]["end_time"], text["start_time"]
            )[0]
        ):
            problem_sentences.append(
                {
                    "index": (ind % 50) + 1,
                    "page_number": (ind // 50) + 1,
                    "start_time": text["start_time"],
                    "end_time": text["end_time"],
                    "text": text["text"],
                    "target_text": text["target_text"],
                }
            )
    return problem_sentences


def get_bad_sentences_in_progress(translation_obj, target_language):
    problem_sentences = []
    translation = translation_obj.payload
    compare_with_index = -1
    last_valid_index = -1
    for ind, text in enumerate(translation["payload"]):
        if (
            "text" in text.keys()
            and not compare_time(text["end_time"], text["start_time"])[0]
        ):
            problem_sentences.append(
                {
                    "index": (ind % 50) + 1,
                    "page_number": (ind // 50) + 1,
                    "start_time": text["start_time"],
                    "end_time": text["end_time"],
                    "text": text["text"],
                    "target_text": text["target_text"],
                    "issue_type": "Time issue in the sentence.",
                }
            )
        if ind != 0 and ind < len(translation["payload"]):
            compare = False
            if "text" in translation["payload"][ind - 1] and "text" in text.keys():
                compare_with_index = ind - 1
                last_valid_index = ind
                compare = True
            elif (
                "text" in text.keys() and "text" not in translation["payload"][ind - 1]
            ):
                compare_with_index = last_valid_index
                compare = True
            else:
                pass
            if (
                compare
                and compare_time(
                    translation["payload"][compare_with_index]["end_time"],
                    text["start_time"],
                )[0]
            ):
                problem_sentences.append(
                    {
                        "index": (ind % 50) + 1,
                        "page_number": (ind // 50) + 1,
                        "start_time": text["start_time"],
                        "end_time": text["end_time"],
                        "text": text["text"],
                        "target_text": text["target_text"],
                        "issue_type": "Time issue in the sentence.",
                    }
                )
            elif "text" in text.keys() and text["end_time"] > (
                str(0) + str(translation_obj.video.duration) + str(".000")
            ):
                problem_sentences.append(
                    {
                        "index": (ind % 50) + 1,
                        "page_number": (ind // 50) + 1,
                        "start_time": text["start_time"],
                        "end_time": text["end_time"],
                        "text": text["text"],
                        "target_text": text["target_text"],
                        "issue_type": "Time issue in the sentence.",
                    }
                )
            elif "text" in text.keys() and text["start_time"] == text["end_time"]:
                problem_sentences.append(
                    {
                        "index": (ind % 50) + 1,
                        "page_number": (ind // 50) + 1,
                        "start_time": text["start_time"],
                        "end_time": text["end_time"],
                        "text": text["text"],
                        "target_text": text["target_text"],
                        "issue_type": "Time issue in the sentence.",
                    }
                )
            else:
                pass
        if (
            ("text" in text.keys() and len(text["text"]) < 1)
            or ("target_text" in text.keys() and len(text["target_text"]) < 1)
        ) and translation_obj.translation_type != "ORIGINAL_SOURCE":
            problem_sentences.append(
                {
                    "page_number": (ind // 50) + 1,
                    "index": (ind % 50) + 1,
                    "start_time": text["start_time"],
                    "end_time": text["end_time"],
                    "text": text["text"],
                    "target_text": text["target_text"],
                    "issue_type": "Empty card is not allowed.",
                }
            )
    return problem_sentences


def get_bad_sentences_in_progress_for_transcription(transcription_obj, target_language):
    problem_sentences = []
    translation = transcription_obj.payload
    compare_with_index = -1
    last_valid_index = -1
    for ind, text in enumerate(translation["payload"]):
        if (
            "text" in text.keys()
            and not compare_time(text["end_time"], text["start_time"])[0]
        ):
            problem_sentences.append(
                {
                    "index": (ind % 50) + 1,
                    "page_number": (ind // 50) + 1,
                    "start_time": text["start_time"],
                    "end_time": text["end_time"],
                    "text": text["text"],
                    "issue_type": "Time issue in the sentence.",
                }
            )
        if ind != 0 and ind < len(translation["payload"]):
            compare = False
            if "text" in translation["payload"][ind - 1] and "text" in text.keys():
                compare_with_index = ind - 1
                last_valid_index = ind
                compare = True
            elif (
                "text" in text.keys() and "text" not in translation["payload"][ind - 1]
            ):
                compare_with_index = last_valid_index
                compare = True
            else:
                pass
            if (
                compare
                and compare_time(
                    translation["payload"][compare_with_index]["end_time"],
                    text["start_time"],
                )[0]
            ):
                problem_sentences.append(
                    {
                        "index": (ind % 50) + 1,
                        "page_number": (ind // 50) + 1,
                        "start_time": text["start_time"],
                        "end_time": text["end_time"],
                        "text": text["text"],
                        "issue_type": "Time issue in the sentence.",
                    }
                )
            elif "text" in text.keys() and text["end_time"] > (
                str(0) + str(transcription_obj.video.duration) + str(".000")
            ):
                problem_sentences.append(
                    {
                        "index": (ind % 50) + 1,
                        "page_number": (ind // 50) + 1,
                        "start_time": text["start_time"],
                        "end_time": text["end_time"],
                        "text": text["text"],
                        "issue_type": "Time issue in the sentence.",
                    }
                )
            elif "text" in text.keys() and text["start_time"] == text["end_time"]:
                problem_sentences.append(
                    {
                        "index": (ind % 50) + 1,
                        "page_number": (ind // 50) + 1,
                        "start_time": text["start_time"],
                        "end_time": text["end_time"],
                        "text": text["text"],
                        "issue_type": "Time issue in the sentence.",
                    }
                )
            else:
                pass
        if "text" in text.keys() and len(text["text"]) < 1:
            problem_sentences.append(
                {
                    "page_number": (ind // 50) + 1,
                    "index": (ind % 50) + 1,
                    "start_time": text["start_time"],
                    "end_time": text["end_time"],
                    "text": text["text"],
                    "issue_type": "Empty card is not allowed.",
                }
            )
    return problem_sentences


def process_translation_payload(translation_obj, target_language):
    tts_input = []
    empty_sentences = []
    delete_indices = []
    translation = translation_obj.payload
    for ind, text in enumerate(translation["payload"]):
        if ind != 0:
            equal_sentences(ind, translation["payload"][ind - 1], text, delete_indices)

    delete_indices.reverse()
    for index in delete_indices:
        translation["payload"].pop(index)
    for ind, text in enumerate(translation["payload"]):
        if not compare_time(text["end_time"], text["start_time"])[0]:
            return {
                "message": "Voice Over can't be generated as end time of a sentence is smaller than start time.",
                "status": status.HTTP_400_BAD_REQUEST,
            }
        if (
            ind != 0
            and ind < len(translation["payload"])
            and compare_time(
                translation["payload"][ind - 1]["end_time"], text["start_time"]
            )[0]
        ):
            logging.info(
                "Voice Over can't be generated as start time of a sentence is greater than end time of previous sentence. %s",
                str(ind),
            )
            return {
                "message": "Voice Over can't be generated as start time of a sentence is greater than end time of previous sentence.",
                "status": status.HTTP_400_BAD_REQUEST,
            }

        clean_target_text = (
            text["target_text"].replace('""', "").replace('"."', "").replace('"', "")
        )
        if (
            len(clean_target_text) > 1
            and clean_target_text != " "
            and clean_target_text.isspace() == False
            and re.match(r"^[_\W]+$", clean_target_text) == None
        ):
            tts_input.append(
                {
                    "source": clean_target_text,
                    "index": ind,
                    "speaker_id": text.get("speaker_id", ""),
                }
            )
        else:
            empty_sentences.append(ind)
    return (
        tts_input,
        target_language,
        translation,
        translation_obj.id,
        empty_sentences,
    )


def group_speakers(tts_input):
    for ind, input in enumerate(tts_input):
        if ind > 0 and "speaker_id" in input.keys() and len(input["speaker_id"]) == 0:
            if len(tts_input[ind - 1]["speaker_id"]) > 0:
                input["speaker_id"] = tts_input[ind - 1]["speaker_id"]
            else:
                input["speaker_id"] = DEFAULT_SPEAKER

    speakers_tts_input = {}
    for ind, input in enumerate(tts_input):
        if input["speaker_id"] not in speakers_tts_input.keys():
            speakers_tts_input[input["speaker_id"]] = []
            speakers_tts_input[input["speaker_id"]].append(input)
        else:
            speakers_tts_input[input["speaker_id"]].append(input)
    return speakers_tts_input


def adjust_voiceover(translation_payload):
    output = [0] * voice_over_payload_offset_size
    for index, (translation_text, audio, duration) in enumerate(translation_payload):
        if type(audio) == dict and "audioContent" in audio.keys():
            if len(audio["audioContent"]) > 400:
                uuid_num = str(uuid.uuid4())
                audio_file = "temp_" + uuid_num + ".wav"
                first_audio_decoded = base64.b64decode(audio["audioContent"])
                with open(audio_file, "wb") as output_f:
                    output_f.write(first_audio_decoded)
                try:
                    AudioSegment.from_file(audio_file).export(
                        "temp_" + uuid_num + ".ogg", format="ogg"
                    )
                except:
                    audio_file = "temp_" + uuid_num + ".ogg"
                    first_audio_decoded = base64.b64decode(audio["audioContent"])
                    with open(audio_file, "wb") as output_f:
                        output_f.write(first_audio_decoded)
                adjust_audio(
                    "temp_" + uuid_num + ".ogg", translation_payload[index][2], -1
                )
                encoded_audio = base64.b64encode(
                    open("temp_" + uuid_num + ".ogg", "rb").read()
                )
                output[index] = (
                    translation_payload[index][0],
                    {"audioContent": encoded_audio.decode()},
                )
            else:
                logging.info("Recieved wrong input for %s", translation_text)
                output[index] = (translation_payload[index][0], "")
        else:
            output[index] = (translation_payload[index][0], "")
    return output


def generate_voiceover_payload(translation_payload, target_language, task):
    tts_input = []
    if(len(translation_payload)>voice_over_payload_offset_size):
        output = [0] * len(translation_payload)
    else:
        output = [0] * voice_over_payload_offset_size
    pre_generated_audio_indices = []
    post_generated_audio_indices = []
    post_generated_audio_indices = []

    for index, (translation_text, audio, call_tts, duration) in enumerate(
        translation_payload
    ):
        if call_tts:
            if len(translation_text) > 1 or translation_text != " ":
                logging.info("Translate Sentence %s", translation_text)
                tts_input.append({"source": translation_text})
                post_generated_audio_indices.append(index)
            else:
                output[index] = ""
        else:
            pre_generated_audio_indices.append(index)
            output[index] = (translation_text, audio)

    if len(tts_input) > 0:
        if task.video.gender == None:
            gender = "male"
        else:
            gender = task.video.gender
        voiceover_machine_generated = get_tts_output(
            tts_input, target_language, task.video.multiple_speaker, gender.lower()
        )
        if (
            type(voiceover_machine_generated) == dict
            and "audio" in voiceover_machine_generated
        ):
            for voice_over in voiceover_machine_generated["audio"]:
                if (
                    "audioContent" in voice_over.keys()
                    and len(voice_over["audioContent"]) > 100
                ):
                    ind = post_generated_audio_indices.pop(0)
                    uuid_num = str(uuid.uuid4())
                    audio_file = "temp_" + uuid_num + ".wav"
                    first_audio_decoded = base64.b64decode(voice_over["audioContent"])
                    with open(audio_file, "wb") as output_f:
                        output_f.write(first_audio_decoded)
                    AudioSegment.from_wav(audio_file).export(
                        "temp_" + uuid_num + ".ogg", format="ogg"
                    )
                    adjust_audio(
                        "temp_" + uuid_num + ".ogg", translation_payload[ind][3], -1
                    )
                    encoded_audio = base64.b64encode(
                        open("temp_" + uuid_num + ".ogg", "rb").read()
                    )
                    output[ind] = (
                        translation_payload[ind][0],
                        {"audioContent": encoded_audio.decode()},
                    )
                    os.remove(audio_file)
                    os.remove("temp_" + uuid_num + ".ogg")
                else:
                    output[ind] = (
                        translation_payload[ind][0],
                        {"audioContent": ""},
                    )
        else:
            ind = post_generated_audio_indices.pop(0)
            output[ind] = (
                translation_payload[ind][0],
                {"audioContent": ""},
            )
    return output


def download_video(url, file_name):
    logging.info("Downloading video %s", url)
    ydl = YoutubeDL({"format": "best"})
    """
    Get video details from Google's platforms:
    YouTube and Drive
    """
    try:
        with YoutubeDL(
            {"format": "best", "outtmpl": "{}.%(ext)s".format(file_name)}
        ) as ydl:
            ydl.download([url])
    except DownloadError:
        return {"message": "Error in downloading video"}
    logging.info("Downloaded video")


def integrate_audio_with_video(file_name, voice_over_obj, video):
    logging.info("Audio Integration Started.")
    integrate_all_audios(file_name, voice_over_obj.payload, video.duration)
    logging.info("Audio Integration Completed.")
    # load the video
    audio_file = file_name + "final.ogg"
    AudioSegment.from_wav(file_name + "final.wav").export(
        file_name + "final.ogg", format="ogg"
    )
    audio_clip = AudioFileClip(audio_file)
    if voice_over_obj.video.project_id.video_integration == True:
        download_video(video.url, file_name)
        video_file = file_name + ".mp4"
        video_clip = VideoFileClip(video_file)
        # load the audio
        audio_clip = audio_clip.volumex(1)
        end = video_clip.end
        start = 0
        # make sure audio clip is less than video clip in duration
        # setting the start & end of the audio clip to `start` and `end` paramters
        # audio_clip = audio_clip.subclip(start, end)
        final_audio = audio_clip
        # add the final audio to the video
        final_clip = video_clip.set_audio(final_audio)
        # save the final clip
        final_clip.write_videofile(os.path.join(file_name + "final.mp4"))
        logging.info("Integration of audio and video done")
        os.remove(video_file)
        os.rename(os.path.join(file_name + "final.mp4"), file_name + ".mp4")


def check_audio_completion(voice_over_obj):
    length_translation_payload = len(voice_over_obj.translation.payload["payload"])
    length_voiceover_payload = len(voice_over_obj.payload["payload"].keys())
    missing_cards = []

    for index, payload in enumerate(voice_over_obj.translation.payload["payload"]):
        if str(index) in voice_over_obj.payload["payload"].keys():
            if (
                "audio" in voice_over_obj.payload["payload"][str(index)].keys()
                and type(voice_over_obj.payload["payload"][str(index)]["audio"]) == dict
                and "audioContent"
                in voice_over_obj.payload["payload"][str(index)]["audio"].keys()
                and len(
                    voice_over_obj.payload["payload"][str(index)]["audio"][
                        "audioContent"
                    ]
                )
                > 0
            ):
                continue
            else:
                missing_cards.append(
                    {
                        "card_number": index + 1,
                        "message": "There is no audio present in this card.",
                    }
                )
    return missing_cards


def audio_duration(length):
    hours = length // 3600  # calculate in hours
    length %= 3600
    mins = length // 60  # calculate in minutes
    length %= 60
    seconds = length  # calculate in seconds

    return hours, mins, seconds  # returns the duration


"""
def adjust_speed(audio_file, speed_adjustment):
    # reload the audio to use librosa's expected format
    lr_speech_data, lr_speech_rate = librosa.load(audio_file)
    if speed_adjustment != 1:
        stretched = librosa.effects.time_stretch(lr_speech_data, rate=speed_adjustment)
        wavfile.write(audio_file, lr_speech_rate, stretched)


def adjust_audio_wav(audio_file, original_time, audio_speed):
    audio = AudioFileClip(audio_file)
    seconds = audio.duration
    logging.info("Original Time of audio is %s", str(original_time))
    logging.info("Seconds of audio %s", str(seconds))
    audio_time_difference = original_time - seconds
    if audio_time_difference > 0:
        logging.info("Add silence in the audio of wav %s", str(audio_time_difference))
        # duration in milliseconds
        silence_segment = AudioSegment.silent(duration=audio_time_difference * 1000)
        # read wav file to an audio segment
        audio = AudioSegment.from_wav(audio_file)
        # Add above two audio segments
        final_audio = audio + silence_segment
        # save modified audio
        final_audio.export(audio_file, format="wav")
    elif audio_time_difference == 0:
        logging.info("No time difference")
    else:
        logging.info("Speed up the audio by %s", str(seconds / original_time))
        adjust_speed(audio_file, seconds / original_time)
"""


def adjust_audio(audio_file, original_time, audio_speed):
    audio = AudioFileClip(audio_file)
    seconds = audio.duration
    audio = AudioSegment.from_file(audio_file)
    audio_time_difference = (original_time * 1000 - len(audio)) / 1000
    if audio_time_difference > 0:
        logging.info("Add silence in the audio of %s", str(audio_time_difference))
        # duration in millisecond
        silence_segment = AudioSegment.silent(duration=audio_time_difference * 1000)
        orig_seg = AudioSegment.from_file(audio_file)
        # for adding silence at the end of audio
        combined_audio = orig_seg + silence_segment
        combined_audio.export(audio_file, format="ogg")
    elif audio_time_difference == 0:
        logging.info("No time difference")
    elif audio_time_difference < -0.001:
        logging.info("Speed up the audio by %s", str(seconds / original_time))
        speedup_factor = seconds / original_time
        if speedup_factor > 1.009:
           
            output_file = "temp_output.ogg"
            subprocess.run([
                "ffmpeg", "-y", "-i", audio_file, "-filter:a", f"atempo={speedup_factor}", output_file
            ])
            # Trim the audio to the original length
            subprocess.run([
                "ffmpeg", "-y", "-i", output_file, "-t", str(original_time), audio_file
            ])
            subprocess.run(["rm", output_file])
            
            audio = AudioFileClip(audio_file)
            seconds = audio.duration
            logging.info("Seconds of adjusted ogg audio %s", str(seconds))
    else:
        pass


def compare_time(original_time, end_time):
    original_date_time = datetime.strptime(original_time, "%H:%M:%S.%f")
    end_date_time = datetime.strptime(end_time, "%H:%M:%S.%f")
    if original_date_time > end_date_time:
        delta = original_date_time - end_date_time
    else:
        delta = end_date_time - original_date_time
    return original_date_time > end_date_time, delta.total_seconds()


def get_original_duration(start_time, end_time):
    time_difference = (
        datetime.strptime(end_time, "%H:%M:%S.%f")
        - timedelta(
            hours=float(start_time.split(":")[0]),
            minutes=float(start_time.split(":")[1]),
            seconds=float(start_time.split(":")[-1]),
        )
    ).strftime("%H:%M:%S.%f")

    t_d = (
        int(time_difference.split(":")[0]) * 3600
        + int(time_difference.split(":")[1]) * 60
        + float(time_difference.split(":")[2])
    )
    return t_d


def integrate_all_audios(file_name, payload, video_duration):
    length_payload = len(payload["payload"])
    first_audio = payload["payload"]["0"]["audio"]["audioContent"]
    first_audio_decoded = base64.b64decode(first_audio)
    logging.info("Index of Audio : #%s", str(0))
    audio_file_paths = []
    with open(file_name + "_" + str(0) + ".ogg", "wb") as out_f23:
        out_f23.write(first_audio_decoded)
    adjust_audio(
        file_name + "_" + str(0) + ".ogg",
        payload["payload"][str(0)]["time_difference"],
        -1,
    )
    first_start_time = payload["payload"]["0"]["start_time"]
    difference_between_payloads = get_original_duration(
        "00:00:00.000", first_start_time
    )
    if difference_between_payloads > 0:
        silence_segment = AudioSegment.silent(
            duration=difference_between_payloads * 1000
        )
        # read wav file to an audio segment
        audio = AudioSegment.from_file(file_name + "_" + str(0) + ".ogg")
        # Add above two audio segments
        final_audio = silence_segment + audio
        final_audio.export(file_name + "_" + str(0) + ".ogg", format="ogg")

    sorted_keys = list(payload["payload"].keys())
    audio_file_paths.append(file_name + "_" + str(0) + ".ogg")
    empty_audios = []
    last_valid_index = 0
    for key in sorted_keys:
        index = int(key)
        if str(index) in payload["payload"].keys() and index > 0:
            if str(index - 1) in payload["payload"].keys():
                current_payload = payload["payload"][str(index)]["start_time"]
                previous_payload = payload["payload"][str(last_valid_index)]["end_time"]
                difference_between_payloads = get_original_duration(
                    previous_payload, current_payload
                )
                if difference_between_payloads > 3600 or (
                    current_payload
                    == payload["payload"][str(last_valid_index)]["start_time"]
                ):
                    empty_audios.append(index)
                    continue
                else:
                    previous_index = last_valid_index
                    last_valid_index = index

                if (
                    difference_between_payloads > 0
                    and difference_between_payloads < 3600
                ):
                    silence_segment = AudioSegment.silent(
                        duration=difference_between_payloads * 1000
                    )
                    # duration in milliseconds
                    # read wav file to an audio segment
                    audio = AudioSegment.from_file(
                        file_name + "_" + str(previous_index) + ".ogg"
                    )
                    # Add above two audio segments
                    final_audio = audio + silence_segment
                    final_audio.export(
                        file_name + "_" + str(previous_index) + ".ogg", format="ogg"
                    )
            if index == length_payload - 1:
                original_time = payload["payload"][str(index)]["time_difference"]
                end_time = payload["payload"][str(index)]["end_time"]
                audio_2_decoded = base64.b64decode(
                    payload["payload"][str(index)]["audio"]["audioContent"]
                )
                if compare_time(str(video_duration) + str(".000"), end_time)[0]:
                    last_segment_difference = get_original_duration(
                        end_time, str(video_duration) + str(".000")
                    )
                    if last_segment_difference > 0:
                        with open(
                            file_name + "_" + str(index) + ".ogg", "wb"
                        ) as out_f23:
                            out_f23.write(audio_2_decoded)
                        adjust_audio(
                            file_name + "_" + str(index) + ".ogg", original_time, -1
                        )
                        silence_segment = AudioSegment.silent(
                            duration=last_segment_difference * 1000
                        )
                        # duration in milliseconds
                        # read wav file to an audio segment
                        audio = AudioSegment.from_file(
                            file_name + "_" + str(index) + ".ogg"
                        )
                        # Add above two audio segments
                        final_audio = audio + silence_segment
                        final_audio.export(
                            file_name + "_" + str(index) + ".ogg", format="ogg"
                        )
                        audio_file_paths.append(file_name + "_" + str(index) + ".ogg")
                else:
                    with open(file_name + "_" + str(index) + ".ogg", "wb") as out_f23:
                        out_f23.write(audio_2_decoded)
                    adjust_audio(
                        file_name + "_" + str(index) + ".ogg", original_time, -1
                    )
                    audio_file_paths.append(file_name + "_" + str(index) + ".ogg")

            else:
                logging.info("Index of Audio : #%s", str(index))
                original_time = payload["payload"][str(index)]["time_difference"]
                if len(payload["payload"][str(index)]["audio"]["audioContent"]) < 100:
                    silence_audio = AudioSegment.silent(duration=original_time * 1000)
                    silence_audio.export(
                        file_name + "_" + str(index) + ".ogg", format="ogg"
                    )
                    audio_file_paths.append(file_name + "_" + str(index) + ".ogg")
                elif str(index) in empty_audios:
                    continue
                else:
                    audio_2_decoded = base64.b64decode(
                        payload["payload"][str(index)]["audio"]["audioContent"]
                    )
                    with open(file_name + "_" + str(index) + ".ogg", "wb") as out_f23:
                        out_f23.write(audio_2_decoded)
                    adjust_audio(
                        file_name + "_" + str(index) + ".ogg", original_time, -1
                    )
                    audio_file_paths.append(file_name + "_" + str(index) + ".ogg")

    final_paths = []
    batch_size = math.ceil(len(audio_file_paths) / 20)
    for i in range(batch_size):
        if i == 0:
            audio_batch_paths = audio_file_paths[: (i + 1) * 20]
            clips = [AudioFileClip(c) for c in audio_batch_paths]
            final_clip = concatenate_audioclips(clips)
            final_clip.write_audiofile(file_name + str(i) + ".wav")
            final_paths.append(file_name + str(i) + ".wav")
        elif i == batch_size - 1:
            audio_batch_paths = audio_file_paths[(i * 20) : len(audio_file_paths)]
            clips = [AudioFileClip(c) for c in audio_batch_paths]
            final_clip = concatenate_audioclips(clips)
            final_clip.write_audiofile(file_name + str(i) + ".wav")
            final_paths.append(file_name + str(i) + ".wav")
        else:
            audio_batch_paths = audio_file_paths[(i * 20) : ((i + 1) * 20)]
            clips = [AudioFileClip(c) for c in audio_batch_paths]
            final_clip = concatenate_audioclips(clips)
            final_clip.write_audiofile(file_name + str(i) + ".wav")
            final_paths.append(file_name + str(i) + ".wav")

    clips = [AudioFileClip(c) for c in final_paths]
    final_clip_1 = concatenate_audioclips(clips)
    final_clip_1.write_audiofile(file_name + "final.wav")
    for fname in audio_file_paths + final_paths:
        if os.path.isfile(fname):
            os.remove(fname)


def send_audio_mail_to_user(task, azure_url, user):
    if task.user.enable_mail:
        logging.info("Send Audio email to user %s", azure_url)
        subject = f"Audio is generated for Video ID - {task.video.id}"
        message = """The requested audio has been successfully generated. You can access the audio by copying and pasting the following link into your web browser.
            {url}""".format(
            url=azure_url
        )

        compiled_code = send_email_template(subject, message)
        msg = EmailMultiAlternatives(
            subject,
            compiled_code,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )
        msg.attach_alternative(compiled_code, "text/html")
        msg.send()
        # send_mail(
        #     f"Audio is generated for Video ID - {task.video.id}",
        #     """The requested audio has been successfully generated. You can access the audio by copying and pasting the following link into your web browser.
        #     {url}""".format(
        #         url=azure_url
        #     ),
        #     settings.DEFAULT_FROM_EMAIL,
        #     [user.email],
        # )
    else:
        logging.info("Email is not enabled %s", task.user.email)


def send_audio_zip_mail_to_user(task, azure_url, user):
    if task.user.enable_mail:
        logging.info("Send Bulk Audio email to user %s", user.email)
        try:
            # send_mail(
            #     f"The requested audios have been successfully generated. You can access the audios by copying and pasting the following link into your web browser: {azure_url}",
            #     settings.DEFAULT_FROM_EMAIL,
            #     [user.email],
            # )
            subject = f"Audio is generated for Video ID - {task.video.id}"
            message = f"The requested audios have been successfully generated. You can access the audios by copying and pasting the following link into your web browser: {azure_url}"
            compiled_code = send_email_template(subject, message)
            msg = EmailMultiAlternatives(
                subject,
                compiled_code,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
            )
            msg.attach_alternative(compiled_code, "text/html")
            msg.send()
            logging.info("Email sent successfully to %s", user.email)
        except Exception as e:
            logging.error("Error sending email to %s: %s", user.email, str(e))
    else:
        logging.info("Email is not enabled for user %s", user.email)


def send_mail_to_user(task):
    if task.user.enable_mail:
        if task.eta is not None:
            try:
                task_eta = str(task.eta.strftime("%Y-%m-%d"))
            except AttributeError:
                task_eta = str(task.eta)
        else:
            task_eta = "-"
        logging.info("Send email to user %s", task.user.email)
        table_to_send = "<p>Dear User, Following task is active.</p><p><head><style>table, th, td {border: 1px solid black;border-collapse: collapse;}</style></head><body><table>"
        data = "<tr><th>Video Name</th><td>{name}</td></tr><tr><th>Video URL</th><td>{url}</td></tr><tr><th>Project Name</th><td>{project_name}</td></tr><tr><th>ETA</th><td>{eta}</td></tr></tr><tr><th>Description</th><td>{description}</td></tr></table></body></p>".format(
            name=task.video.name,
            url=task.video.url,
            project_name=task.video.project_id.title,
            eta=task_eta,
            description=task.description,
        )
        final_table = table_to_send + data
        try:
            subject = f"{task.get_task_type_label()} is now active"
            message = f"Following task is active you may check the attachment below \n {final_table}"
            compiled_code = send_email_template(subject, message)
            msg = EmailMultiAlternatives(
                subject,
                compiled_code,
                settings.DEFAULT_FROM_EMAIL,
                [task.user.email],
            )
            msg.attach_alternative(compiled_code, "text/html")
            msg.send()
        except Exception as e:
            logging.error("Error in sending Email: %s", str(e))
    else:
        logging.info("Email is not enabled %s", task.user.email)
