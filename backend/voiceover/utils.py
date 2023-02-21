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
from pydub import AudioSegment
from datetime import datetime, date, timedelta
from scipy.io.wavfile import write, read
import os
import wave
import base64
from scipy.io.wavfile import read as read_wav
from datetime import timedelta
import webvtt
from io import StringIO
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError
from yt_dlp.extractor import get_info_extractor
from django.http import HttpRequest
from moviepy.editor import VideoFileClip, AudioFileClip
from scipy.io import wavfile
from mutagen.wave import WAVE
import numpy
import librosa


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
            # blob_data = blob_client.download_blob()
            # data = blob_data.readall()
            # print(data)
        # delete temporary audio and video


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
        voiceover_machine_generated = get_tts_output(tts_input, target_language)
        for voice_over in voiceover_machine_generated["audio"]:
            ind = post_generated_audio_indices.pop(0)
            audio_file = "temp.wav"
            first_audio_decoded = base64.b64decode(voice_over["audioContent"])
            with open(audio_file, "wb") as output_f:
                output_f.write(first_audio_decoded)
            adjust_audio(audio_file, translation_payload[ind][3], -1)
            encoded_audio = base64.b64encode(open(audio_file, "rb").read())
            output[ind] = (translation_payload[ind][0], {"audioContent": encoded_audio})
    return output


def download_video(url):
    ydl = YoutubeDL({"format": "best"})
    """
    Get video details from Google's platforms:
    YouTube and Drive
    """
    try:
        with YoutubeDL(
            {
                "format": "best",
                "outtmpl": os.path.join(
                    "temporary_video_audio_storage", "%(title)s.%(ext)s"
                ),
            }
        ) as ydl:
            ydl.download([url])
    except DownloadError:
        return {"message": "Error in downloading video"}


def integrate_audio_with_video(file_name, voice_over_obj, video):
    integrate_all_audios(file_name, voice_over_obj.payload, video.duration)
    # load the video
    download_video(video.url)
    video_file = file_name + ".mp4"
    video_clip = VideoFileClip(video_file)
    # load the audio
    audio_file = file_name + ".wav"
    audio_clip = AudioFileClip(audio_file)
    audio_clip = audio_clip.volumex(1)
    end = video_clip.end
    start = 0
    # make sure audio clip is less than video clip in duration
    # setting the start & end of the audio clip to `start` and `end` paramters
    audio_clip = audio_clip.subclip(start, end)
    final_audio = audio_clip
    # add the final audio to the video
    final_clip = video_clip.set_audio(final_audio)
    # save the final clip
    final_clip.write_videofile(video_file)


def check_audio_completion(voice_over_obj):
    length_translation_payload = len(voice_over_obj.translation.payload["payload"])
    length_voiceover_payload = len(voice_over_obj.payload["payload"].keys())
    missing_cards = []

    for index, payload in enumerate(voice_over_obj.translation.payload["payload"]):
        if str(index) in voice_over_obj.payload["payload"].keys():
            if (
                "audio" in voice_over_obj.payload["payload"][str(index)].keys()
                and "audioContent"
                in voice_over_obj.payload["payload"][str(index)]["audio"].keys()
            ):
                continue
            else:
                missing_cards.append(
                    {
                        "card_number": index + 1,
                        "message": "There is no audio present in this card.",
                    }
                )
        else:
            missing_cards.append(
                {"card_number": index + 1, "message": "This card was not saved."}
            )
    return missing_cards


def audio_duration(length):
    hours = length // 3600  # calculate in hours
    length %= 3600
    mins = length // 60  # calculate in minutes
    length %= 60
    seconds = length  # calculate in seconds

    return hours, mins, seconds  # returns the duration


def adjust_speed(audio_file, speed_adjustment):
    # reload the audio to use librosa's expected format
    lr_speech_data, lr_speech_rate = librosa.load(audio_file)
    if speed_adjustment != 1:
        stretched = librosa.effects.time_stretch(lr_speech_data, rate=speed_adjustment)
        wavfile.write(audio_file, lr_speech_rate, stretched)


def adjust_audio(audio_file, original_time, audio_speed):
    audio = WAVE(audio_file)
    audio_info = audio.info
    length = int(audio_info.length)
    hours, mins, seconds = audio_duration(length)
    audio_time_difference = original_time - seconds
    if audio_time_difference > 0:
        silence_segment = AudioSegment.silent(
            duration=audio_time_difference * 1000
        )  # duration in milliseconds
        # read wav file to an audio segment
        audio = AudioSegment.from_wav(audio_file)
        # Add above two audio segments
        final_audio = audio + silence_segment
        # Either save modified audio
        final_audio.export(audio_file, format="wav")
    elif audio_time_difference == 0:
        print("No time difference")
    else:
        adjust_speed(audio_file, seconds / original_time)


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
    with open(file_name + ".wav", "wb") as out_f23:
        out_f23.write(first_audio_decoded)
    adjust_audio(file_name + ".wav", payload["payload"][str(0)]["time_difference"], -1)
    for index in range(length_payload):
        if index > 0:
            curent_payload = payload["payload"][str(index)]["start_time"]
            previous_payload = payload["payload"][str(index - 1)]["end_time"]
            difference_between_payloads = get_original_duration(
                previous_payload, curent_payload
            )
            if difference_between_payloads > 0:
                silence_segment = AudioSegment.silent(
                    duration=difference_between_payloads * 1000
                )  # duration in milliseconds
                # read wav file to an audio segment
                audio = AudioSegment.from_wav(file_name + ".wav")
                # Add above two audio segments
                final_audio = audio + silence_segment
                final_audio.export(file_name + ".wav", format="wav")
            if index == length_payload - 1:
                end_time = payload["payload"][str(index)]["end_time"]
                last_segment_difference = get_original_duration(
                    end_time, str(video_duration) + str(".000")
                )
                audio_2_decoded = base64.b64decode(
                    payload["payload"][str(index)]["audio"]["audioContent"]
                )
                if last_segment_difference > 0:
                    with open(file_name + "_1.wav", "wb") as out_f23:
                        out_f23.write(audio_2_decoded)
                    adjust_audio(file_name + "_1.wav", last_segment_difference, -1)
            else:
                original_time = payload["payload"][str(index)]["time_difference"]
                audio_2_decoded = base64.b64decode(
                    payload["payload"][str(index)]["audio"]["audioContent"]
                )
                with open(file_name + "_1.wav", "wb") as out_f23:
                    out_f23.write(audio_2_decoded)

                adjust_audio(file_name + "_1.wav", original_time, -1)

            sound1 = AudioSegment.from_wav(file_name + ".wav")
            sound2 = AudioSegment.from_wav(file_name + "_1.wav")
            combined_sounds = sound1 + sound2
            combined_sounds.export(file_name + ".wav", format="wav")
    adjust_audio(file_name + ".wav", video_duration.total_seconds(), -1)
