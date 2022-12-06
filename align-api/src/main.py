from configuration import ModelPath
from wav2vec2.utils import Wav2vec2
from rich.console import Console
from rich.traceback import install
from fastapi import FastAPI, status, HTTPException
from pydantic import BaseModel
import numpy as np
import torch
from utils import filter_text, wav_from_buffer, SubtitleJson
from typing import Optional
from pytube import YouTube
import re
from tqdm import tqdm
import string

install()
console = Console()

app = FastAPI()


class AlignData(BaseModel):
    text: str = None
    wav_chunk: list[float] = None
    start_time: Optional[float] = 0.0
    language: str = None


class ExtendedAudioAlign(BaseModel):
    srt: dict = None
    url: str = None
    language: str = None


language_codes = ModelPath.language_codes
aligner_models = {}
for language in language_codes:
    console.log(f"Loading aligner model for language [green underline]{language}")
    aligner_models[language] = Wav2vec2(
        ModelPath.wav2vec2_path,
        language_code=language,
        mode="tensor",
        device=ModelPath.device,
    )


@app.post("/align_audio")
def align(align_data: AlignData) -> dict:
    if align_data.language not in language_codes:
        console.log(
            f"User is trying [red underline]{align_data.language} which is not loaded"
        )
        return f"{align_data.language} is not loaded. Use another language."
    alignment = {}
    float_wav = np.array(align_data.wav_chunk)
    wav_tensor = torch.from_numpy(float_wav).float().view(1, -1)
    cleaned_text = filter_text(align_data.text, align_data.language)
    word_segments = aligner_models[align_data.language].merge_words(
        wav_tensor, cleaned_text, begin=align_data.start_time
    )
    alignment["text"] = align_data.text
    alignment["timestamps"] = word_segments
    return alignment


@app.post("/align_json")
def align_json(align_data: ExtendedAudioAlign) -> dict:
    if align_data.language not in language_codes:
        raise HTTPException(status_code=status.HTTP_204_NO_CONTENT,
                            detail='the language code must be from specified language codes in documentation')
    try:
        console.log(f"Fetching audio video from {align_data.url}")
        selected_video = YouTube(align_data.url)
        audio = selected_video.streams.filter(
            only_audio=True, file_extension="mp4"
        ).first()
    except:
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail="audio stream not available for current youtube video at the moment",
        )

    console.log("Extracting bytes from audio")
    wav = wav_from_buffer(audio)
    console.log(f"Duration of audio is {wav.duration_seconds} seconds")
    srt_json = align_data.srt["payload"]

    aligned_json = {}

    for idx, sub in tqdm(enumerate(srt_json), leave=False):

        text = sub["text"]
        alignment = {}

        text = re.sub("[\(\[].*?[\)\]]", "", text).replace("\n", " ")
        clean_text = (
            re.sub("[%s]" % re.escape(string.punctuation + "।" + "-"), "", text)
            .strip()
            .replace("\n", " ")
        )

        if not clean_text:
            alignment["text"] = "[Noise]"
            alignment["timestamps"] = None
            aligned_json[str(idx + 1)] = alignment
            continue

        start, end = SubtitleJson.extract_time(sub["start_time"], sub["end_time"])
        chunk = SubtitleJson.clip_audio(wav, start, end)
        float_wav = np.array(chunk.get_array_of_samples()).astype("float64")
        wav_tensor = torch.from_numpy(float_wav).float().view(1, -1)
        filtered_text = filter_text(clean_text, align_data.language)
        try:
            word_segments = aligner_models[align_data.language].merge_words(
            wav_tensor, filtered_text, begin=start
            )
        except:
            console.log(f"Text contains some unknown character: {filtered_text}")
            alignment["text"] = "[Unkown]"
            alignment["timestamps"] = None
            aligned_json[str(idx+1)] = alignment
            continue
        
        alignment['text'] = clean_text
        alignment['timestamps'] = word_segments
        aligned_json[str(idx+1)] = alignment
        
    console.log(f"Alignment complete")
    
    if align_data.language == 'en':
        aligned_json = SubtitleJson.adjust_alignment(aligned_json, align_data.language)
        
    return aligned_json
