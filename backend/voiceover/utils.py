import requests
from uuid import UUID
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
from django.core.mail import send_mail


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


def download_from_blob_storage(file_path):
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    blob_client = blob_service_client.get_blob_client(
        container=container_name, blob=file_path.split("/")[-1]
    )
    with open(file=file_path.split("/")[-1], mode="wb") as sample_blob:
        download_stream = blob_client.download_blob()
        sample_blob.write(download_stream.readall())


def uploadToBlobStorage(file_path, voice_over_obj):
    full_path = file_path + ".mp4"
    full_path_mp3 = file_path + "final.mp3"
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    blob_client = blob_service_client.get_blob_client(
        container=container_name, blob=file_path.split("/")[-1] + ".mp4"
    )
    blob_client_mp3 = blob_service_client.get_blob_client(
        container=container_name, blob=file_path.split("/")[-1] + ".mp3"
    )
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

        with open(full_path_mp3, "rb") as data:
            try:
                if not blob_client_mp3.exists():
                    blob_client_mp3.upload_blob(data)
                    logging.info("Audio uploaded successfully!")
                    logging.info(blob_client.url)
                else:
                    blob_client_mp3.delete_blob()
                    logging.info("Old Audio deleted successfully!")
                    blob_client_mp3.upload_blob(data)
                    logging.info("New audio uploaded successfully!")
            except Exception as e:
                logging.info("This audio can't be uploaded")

        logging.info(blob_client.url)
        os.remove(file_path + ".mp4")
        os.remove(file_path + "final.mp3")
        return blob_client.url, blob_client_mp3.url


def get_tts_output(tts_input, target_language, gender):
    json_data = {
        "input": tts_input,
        "config": {"language": {"sourceLanguage": target_language}, "gender": gender},
    }
    logging.info("Calling TTS API")
    tts_url = get_tts_url(target_language)
    if tts_url is None:
        return {
            "message": "Error in TTS API. Target Language is not supported.",
            "status": status.HTTP_400_BAD_REQUEST,
        }
    try:
        response = requests.post(
            tts_url,
            headers={"authorization": dhruva_key},
            json=json_data,
        )
        tts_output = response.json()
        # Collect the translated sentences
        return tts_output

    except Exception as e:
        logging.info("Error in TTS API %s", str(e))
        return {
            "message": "Error in TTS API. Invalid sentence was passed.",
            "status": status.HTTP_400_BAD_REQUEST,
        }


def generate_tts_output(
    tts_input, target_language, translation, translation_obj, empty_sentences
):
    if translation_obj.video.gender == None:
        gender = "MALE"
    else:
        gender = translation_obj.video.gender
    tts_output = get_tts_output(tts_input, target_language, gender.lower())
    if type(tts_output) != dict or "audio" not in tts_output.keys():
        return tts_output
    logging.info("Size of TTS output %s", str(asizeof(tts_output)))
    logging.info("Output from TTS generated")
    voiceover_payload = {"payload": {}}
    count = 0
    payload_size = 0
    payload_size_encoded = 0
    for ind, text in enumerate(translation["payload"]):
        start_time = text["start_time"]
        end_time = text["end_time"]
        logging.info("Starting time of this sentence %s", start_time)
        logging.info("Ending time of this sentence %s", end_time)
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
            audio_file = "temp_1.wav"
            audio_decoded = base64.b64decode(tts_output["audio"][count]["audioContent"])
            with open(audio_file, "wb") as output_f:
                output_f.write(audio_decoded)
            audio = AudioFileClip("temp_1.wav")
            wav_seconds = audio.duration
            AudioSegment.from_wav("temp_1.wav").export("temp_1.mp3", format="mp3")
            logging.info("Seconds of wave audio %s", str(wav_seconds))
            audio = AudioFileClip("temp_1.mp3")
            seconds = audio.duration
            logging.info("Seconds of mp3 audio %s", str(seconds))
            adjust_audio("temp_1.mp3", t_d, -1)
            encoded_audio = base64.b64encode(open("temp_1.mp3", "rb").read())
            decoded_audio = encoded_audio.decode()
            os.remove("temp_1.mp3")
            payload_size = payload_size + asizeof(decoded_audio)
            logging.info("Payload size %s", str(asizeof(decoded_audio)))
            logging.info("Index %s", str(ind))
            voiceover_payload["payload"][str(count)] = {
                "time_difference": t_d,
                "start_time": start_time,
                "end_time": end_time,
                "text": text["target_text"],
                "audio": {"audioContent": decoded_audio},
                "audio_speed": 1,
            }
            count = count + 1
        else:
            pass
    logging.info("Size of voiceover payload %s", str(asizeof(voiceover_payload)))
    logging.info("Size of combined audios %s", str(payload_size))
    return voiceover_payload


def process_translation_payload(translation_obj, target_language):
    tts_input = []
    empty_sentences = []
    translation = translation_obj.payload
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
            return {
                "message": "Voice Over can't be generated as start time of a sentence is greater than end time of previous sentence.",
                "status": status.HTTP_400_BAD_REQUEST,
            }

        clean_target_text = text["target_text"].replace('""', "").replace('"."', "")
        match = re.search(r"[a-zA-Z]+", clean_target_text) or re.search(
            r"[0-9]+", clean_target_text
        )
        if (
            len(clean_target_text) > 1
            and clean_target_text != " "
            and clean_target_text.isspace() == False
            and re.match(r"^[_\W]+$", clean_target_text) == None
        ):
            tts_input.append({"source": clean_target_text})
        else:
            empty_sentences.append(ind)
    return (
        tts_input,
        target_language,
        translation,
        translation_obj.id,
        empty_sentences,
    )


def generate_voiceover_payload(translation_payload, target_language, task):
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
        if task.video.gender == None:
            gender = "MALE"
        else:
            gender = task.video.gender
        voiceover_machine_generated = get_tts_output(
            tts_input, target_language, gender.lower()
        )
        for voice_over in voiceover_machine_generated["audio"]:
            ind = post_generated_audio_indices.pop(0)
            audio_file = "temp.wav"
            first_audio_decoded = base64.b64decode(voice_over["audioContent"])
            with open(audio_file, "wb") as output_f:
                output_f.write(first_audio_decoded)
            AudioSegment.from_wav("temp.wav").export("temp.mp3", format="mp3")
            adjust_audio("temp.mp3", translation_payload[ind][3], -1)
            encoded_audio = base64.b64encode(open("temp.mp3", "rb").read())
            output[ind] = (
                translation_payload[ind][0],
                {"audioContent": encoded_audio.decode()},
            )
            os.remove(audio_file)
            os.remove("temp.mp3")
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
    download_video(video.url, file_name)
    video_file = file_name + ".mp4"
    video_clip = VideoFileClip(video_file)
    # load the audio
    audio_file = file_name + "final.mp3"
    audio_clip = AudioFileClip(audio_file)
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
    # audio_time_difference = original_time - seconds
    audio = AudioSegment.from_file(audio_file)
    audio_time_difference = (original_time * 1000 - len(audio)) / 1000
    if audio_time_difference > 0.11:
        logging.info("Add silence in the audio of %s", str(audio_time_difference))
        # duration in millisecond
        silence_segment = AudioSegment.silent(duration=audio_time_difference * 1000)
        orig_seg = AudioSegment.from_file(audio_file)
        # for adding silence at the end of audio
        combined_audio = orig_seg + silence_segment
        combined_audio.export(audio_file, format="mp3")
    elif audio_time_difference == 0:
        logging.info("No time difference")
    elif audio_time_difference < 0:
        logging.info("Speed up the audio by %s", str(seconds / original_time))
        sound = AudioSegment.from_mp3(audio_file)
        # sound.export("temp_original_" + str(ind) + ".mp3", format="mp3")
        # generate a slower audio for example
        faster_sound = speedup(sound, seconds / original_time, 100)
        final_sound = faster_sound[: original_time * 1000]
        final_sound.export(audio_file, format="mp3")
        audio = AudioFileClip(audio_file)
        seconds = audio.duration
        logging.info("Seconds of adjusted mp3 audio %s", str(seconds))
        audio = MP3(audio_file)
        # faster_sound.export("temp_" + str(ind) + ".mp3", format="mp3")
        # speed_change(sound, 0.5)
        # adjust_speed(audio_file, seconds / original_time)
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
    with open(file_name + "_" + str(0) + ".mp3", "wb") as out_f23:
        out_f23.write(first_audio_decoded)
    adjust_audio(
        file_name + "_" + str(0) + ".mp3",
        payload["payload"][str(0)]["time_difference"],
        -1,
    )
    sorted_keys = list(payload["payload"].keys())
    audio_file_paths.append(file_name + "_" + str(0) + ".mp3")
    for key in sorted_keys:
        index = int(key)
        if str(index) in payload["payload"].keys() and index > 0:
            if str(index - 1) in payload["payload"].keys():
                current_payload = payload["payload"][str(index)]["start_time"]
                previous_payload = payload["payload"][str(index - 1)]["end_time"]
                difference_between_payloads = get_original_duration(
                    previous_payload, current_payload
                )
                # print("current_payload", current_payload)
                # print("previous_payload", previous_payload)
                # print("difference_betwwen_payloads", difference_between_payloads)
                if difference_between_payloads > 0:
                    silence_segment = AudioSegment.silent(
                        duration=difference_between_payloads * 1000
                    )
                    # duration in milliseconds
                    # read wav file to an audio segment
                    audio = AudioSegment.from_file(
                        file_name + "_" + str(index - 1) + ".mp3"
                    )
                    # Add above two audio segments
                    final_audio = audio + silence_segment
                    final_audio.export(
                        file_name + "_" + str(index - 1) + ".mp3", format="mp3"
                    )
            if index == length_payload - 1:
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
                            file_name + "_" + str(index) + ".mp3", "wb"
                        ) as out_f23:
                            out_f23.write(audio_2_decoded)
                        silence_segment = AudioSegment.silent(
                            duration=last_segment_difference * 1000
                        )
                        # duration in milliseconds
                        # read wav file to an audio segment
                        audio = AudioSegment.from_file(
                            file_name + "_" + str(index) + ".mp3"
                        )
                        # Add above two audio segments
                        final_audio = audio + silence_segment
                        final_audio.export(
                            file_name + "_" + str(index) + ".mp3", format="mp3"
                        )
                        audio_file_paths.append(file_name + "_" + str(index) + ".mp3")
                else:
                    with open(file_name + "_" + str(index) + ".mp3", "wb") as out_f23:
                        out_f23.write(audio_2_decoded)
                    audio_file_paths.append(file_name + "_" + str(index) + ".mp3")
            else:
                logging.info("Index of Audio : #%s", str(index))
                original_time = payload["payload"][str(index)]["time_difference"]
                audio_2_decoded = base64.b64decode(
                    payload["payload"][str(index)]["audio"]["audioContent"]
                )
                with open(file_name + "_" + str(index) + ".mp3", "wb") as out_f23:
                    out_f23.write(audio_2_decoded)

                adjust_audio(file_name + "_" + str(index) + ".mp3", original_time, -1)
                audio_file_paths.append(file_name + "_" + str(index) + ".mp3")

    batch_size = math.ceil(len(audio_file_paths) / 20)
    final_paths = []
    for i in range(batch_size):
        if i == 0:
            audio_batch_paths = audio_file_paths[: (i + 1) * 20]
            clips = [AudioFileClip(c) for c in audio_batch_paths]
            final_clip = concatenate_audioclips(clips)
            final_clip.write_audiofile(file_name + str(i) + ".mp3")
            final_paths.append(file_name + str(i) + ".mp3")
        elif i == batch_size - 1:
            audio_batch_paths = audio_file_paths[(i) * 20 : len(audio_file_paths)]
            clips = [AudioFileClip(c) for c in audio_batch_paths]
            final_clip = concatenate_audioclips(clips)
            final_clip.write_audiofile(file_name + str(i) + ".mp3")
            final_paths.append(file_name + str(i) + ".mp3")
        else:
            audio_batch_paths = audio_file_paths[(i) * 20 : (i + 1) * 20]
            clips = [AudioFileClip(c) for c in audio_batch_paths]
            final_clip = concatenate_audioclips(clips)
            final_clip.write_audiofile(file_name + str(i) + ".mp3")
            final_paths.append(file_name + str(i) + ".mp3")

    clips = [AudioFileClip(c) for c in final_paths]
    final_clip_1 = concatenate_audioclips(clips)
    final_clip_1.write_audiofile(file_name + "final.mp3")
    for fname in audio_file_paths + final_paths:
        if os.path.isfile(fname):
            os.remove(fname)


def send_mail_to_user(task):
    if task.user.enable_mail:
        if task.eta is not None:
            try:
                task_eta = str(task.eta.strftime("%Y-%m-%d"))
            except:
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
        send_mail(
            f"{task.get_task_type_label} is active",
            "Dear User, Following task is active.",
            settings.DEFAULT_FROM_EMAIL,
            [task.user.email],
            html_message=final_table,
        )
    else:
        logging.info("Email is not enabled %s", task.user.email)
