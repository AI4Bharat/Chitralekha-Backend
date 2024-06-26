import os
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError
from yt_dlp.extractor import get_info_extractor
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_audioclips
from spleeter.separator import Separator
import shutil
from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_subclip
from azure.storage.blob import BlobServiceClient
from config import (
    storage_account_key,
    connection_string,
    container_name,
)
import urllib.parse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import math
from pydub import AudioSegment

app = FastAPI()
export_type = "flac"


def utils_add_bg_music(file_path, video_link):
    file_name = file_path.replace(".flac", "")
    ydl = YoutubeDL({"format": "best"})
    with YoutubeDL(
        {"format": "best", "outtmpl": "{}.%(ext)s".format(file_name)}
    ) as ydl:
        ydl.download([video_link])

    video = VideoFileClip(file_name + ".mp4")
    audio = video.audio

    audio_file = file_name + ".wav"
    audio.write_audiofile(audio_file)
    audio = AudioFileClip(audio_file)
    count = 1
    duration_of_clip = 60  # in seconds, duration of final audio clip
    src_duration = math.ceil(
        audio.duration
    )  # in seconds, the duration of the original audio
    audio_file_paths_bg = []

    for i in range(0, src_duration, duration_of_clip):
        ffmpeg_extract_subclip(
            audio_file, i, i + 60, targetname=f"{file_name}_{count}.wav"
        )
        audio_file_paths_bg.append(f"{file_name}_{count}.wav")
        count += 1

    separator = Separator(
        "spleeter:2stems"
    )  # Load the 2stems (vocals/accompaniment) model
    bg_music = []
    for a_file in audio_file_paths_bg:
        # Use Spleeter to separate vocals and accompaniment
        separation = separator.separate_to_file(a_file, "output")
        temp_file_path = os.path.join(
            "output", a_file.split("/")[-1].replace(".wav", "")
        )
        bg_music.append(temp_file_path + "/accompaniment.wav")

    final_paths = []
    concatenated_bg_audios = audio_file.replace(".wav", "_bg_final.wav")
    clips = [AudioFileClip(c) for c in bg_music]
    final_clip_1 = concatenate_audioclips(clips)
    final_clip_1.write_audiofile(concatenated_bg_audios)

    sound1 = AudioSegment.from_file(concatenated_bg_audios)
    AudioSegment.from_file(file_path.split("/")[-1]).export(
        file_path.replace(".flac", ".wav"), format="wav"
    )
    sound2 = AudioSegment.from_file(
        os.path.join(
            file_path.split("/")[-1].replace(".flac", ".wav"),
        )
    )
    audio1 = sound1
    audio2 = sound2 + 2
    combined = sound2.overlay(audio1)

    combined.export(file_path.replace(".wav", "_final.wav"), format="wav")
    for fname in audio_file_paths_bg:
        if os.path.isfile(fname):
            os.remove(fname)

    try:
        shutil.rmtree("output")
        os.remove(concatenated_bg_audios)
        os.remove(
            os.path.join(
                file_path.split("/")[-1].replace(".flac", ".wav"),
            )
        )
        os.remove(file_path.replace(".flac", "") + ".mp4")
    except OSError as e:
        print("Error: %s - %s." % (e.filename, e.strerror))
    return file_path.replace(".wav", "_final.wav")


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
                print("Audio uploaded successfully!")
                print(blob_client_audio.url)
            else:
                blob_client_audio.delete_blob()
                print("Old Audio deleted successfully!")
                blob_client_audio.upload_blob(data)
                print("New audio uploaded successfully!")
        except Exception as e:
            print("This audio can't be uploaded")
    return blob_client_audio.url


if __name__ == "__main__":
    os.mkdir("temporary_audio_storage")


class BGMusicRequest(BaseModel):
    azure_audio_url: str
    youtube_url: str


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


@app.post("/add_background_music")
async def add_background_music(audio_request: BGMusicRequest):
    url = audio_request.azure_audio_url
    youtube_url = audio_request.youtube_url
    print("Downloading")
    download_from_azure_blob(str(url))
    print("Downloaded")
    file_path = url.split("/")[-1]
    file_path_music = utils_add_bg_music(file_path, youtube_url)
    AudioSegment.from_file(file_path_music).export(
        file_path.split("/")[-1].replace(".flac", "") + "." + export_type,
        format=export_type,
    )
    azure_url_audio = upload_audio_to_azure_blob(file_path, export_type, export=True)
    try:
        os.remove(file_path)
        os.remove(file_path.split("/")[-1].replace(".flac", "") + "." + export_type)
    except:
        print("Error in removing files")
    return {"status": "Success", "output": azure_url_audio}
