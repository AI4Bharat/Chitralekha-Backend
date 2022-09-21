from typing import Optional
import math
import json
import time
import os
import sys
import io
from multiprocessing import Process
import string
import logging

logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.responses import RedirectResponse

import webvtt
from pydub import AudioSegment
import webrtcvad
from yt_dlp import YoutubeDL

import numpy as np
import torch
from omegaconf import OmegaConf
import urllib
from transformers import AutoTokenizer, AutoModelForTokenClassification
from punctuate import RestorePuncts

from support import load_model, W2lKenLMDecoder, W2lViterbiDecoder, load_data
from vad import frame_generator, vad_collector
from youtube import get_yt_video_and_subs

from tqdm import tqdm


MEDIA_FOLDER = "media/"
CONFIG_PATH = "config.json"
DEVICE = "cuda"

print("Modules imported")

# tokenizer = AutoTokenizer.from_pretrained("felflare/bert-restore-punctuation")
# rpunct_model = AutoModelForTokenClassification.from_pretrained("felflare/bert-restore-punctuation")


os.makedirs(MEDIA_FOLDER, exist_ok=True)

app = FastAPI(debug=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

with open(CONFIG_PATH, "r") as j:
    config = json.load(j)

print("Config loaded.")

# Load punctuation model
rpunct = RestorePuncts()
print("Punctuation model loaded.")
# output = rpunct.punctuate("i am here to introduce the course data science for engineers")
outputs = rpunct.punctuate_batch(
    [
        "i am here to introduce the course data science for engineers",
        "hello how are you",
        "i am fine what about you",
        "my name is giorgio giovanni",
    ]
)
print(outputs)
# breakpoint()

print("Loading models from config..")
name2model_dict = dict()
for k, m in config.items():
    if eval(m["lm_usage"]):
        lmarg = OmegaConf.create(m["lm_details"])
        lmarg.unk_weight = -math.inf
        device = m["device"]
        model, dictionary = load_model(m["model_path"])
        if DEVICE != "cpu" and torch.cuda.is_available():
            model.to(device)
        print("Loading LM..")
        generator = W2lKenLMDecoder(lmarg, dictionary)
    else:
        lmarg = OmegaConf.create({"nbest": 1})
        model, dictionary = load_model(m["model_path"])
        device = m["device"]
        if DEVICE != "cpu" and torch.cuda.is_available():
            model.to(device)
        generator = W2lViterbiDecoder(lmarg, dictionary)
    name2model_dict[k] = [model, generator, dictionary]


def align(fp_arr, DEVICE, lang, restore_punct=True):

    feature = torch.from_numpy(fp_arr).float()
    if DEVICE != "cpu" and torch.cuda.is_available():
        feature = feature.to(DEVICE)
    sample = {"net_input": {"source": None, "padding_mask": None}}
    sample["net_input"]["source"] = feature.unsqueeze(0)
    if DEVICE != "cpu" and torch.cuda.is_available():
        sample["net_input"]["padding_mask"] = (
            torch.BoolTensor(sample["net_input"]["source"].size(1))
            .fill_(False)
            .unsqueeze(0)
            .to(DEVICE)
        )
    else:
        sample["net_input"]["padding_mask"] = (
            torch.BoolTensor(sample["net_input"]["source"].size(1))
            .fill_(False)
            .unsqueeze(0)
        )

    model, generator, dictionary = name2model_dict[lang]

    with torch.no_grad():
        hypo = generator.generate([model], sample, prefix_tokens=None)
    hyp_pieces = dictionary.string(hypo[0][0]["tokens"].int().cpu())
    tr = hyp_pieces.replace(" ", "").replace("|", " ").strip()
    return tr


ydl_opts_audio = {
    "format": "bestaudio[ext=m4a]",
    "outtmpl": MEDIA_FOLDER + "/%(id)s.m4a",
}
ydl_audio = YoutubeDL(ydl_opts_audio)


def download_yt_audio(url):
    info = ydl_audio.extract_info(url, download=True)
    downloaded_audio_path = os.path.join(MEDIA_FOLDER, info["id"]) + ".m4a"
    return downloaded_audio_path


@app.on_event("startup")
async def startup_event():
    print("Model loaded.")


@app.get("/")
async def homepage():
    # Redirect homepage to Swagger
    return RedirectResponse(url="/docs")


# indic_language_dict = {
#     'English' : 'en',
#     'Hindi' : 'hi',
#     'Bengali' : 'bn',
#     'Gujarati' : 'gu',
#     'Kannada' : 'kn',
#     'Malayalam' : 'ml',
#     'Marathi' : 'mr',
#     'Odia' : 'or',
#     'Punjabi' : 'pa',
#     'Sanskrit' : 'sa',
#     'Tamil' : 'ta',
#     'Telugu' : 'te',
#     'Urdu' : 'ur',
# }

indic_language_dict = {
    "English": "en",
    "Hindi": "hi",
    "Bengali": "bn",
    "Gujarati": "gu",
    "Marathi": "mr",
    "Odia": "or",
    "Tamil": "ta",
    "Telugu": "te",
}


@app.get("/supported_languages")
async def supported_languages():
    return indic_language_dict


@app.get("/get_youtube_video_link_with_captions")
@app.post("/get_youtube_video_link_with_captions")
async def _get_youtube_video_link_with_captions(url: str, lang: str = "en"):

    return get_yt_video_and_subs(url, lang)


class VideoRequest(BaseModel):
    url: str


@app.post("/download_video_to_local")
async def download_video_to_local(video_request: VideoRequest):
    yt_url = video_request.url
    ydl_best = YoutubeDL({"format": "best"})
    downloaded_audio_path = download_yt_audio(yt_url)
    info = ydl_best.extract_info(yt_url, download=False)
    print(info.keys())
    direct_url = info["url"]
    print(direct_url)
    if os.path.isfile(downloaded_audio_path):
        # Vieo will be downloaded in background
        # Process(target=download_yt_video, args=(yt_url, )).start()

        downloaded_video_path = downloaded_audio_path.replace(".m4a", ".webm")
        return {
            "success": True,
            "audio_url": downloaded_audio_path,
            "download_path": downloaded_video_path,
            "video_url": direct_url,
        }
    return {
        "success": False,
    }


class AudioRequest(BaseModel):
    url: str
    vad_level: Optional[int] = 2
    chunk_size: Optional[float] = 10.0
    language: Optional[str] = "en"
    restore_punct: Optional[bool] = True


@app.post("/transcribe")
async def transcribe_audio(audio_request: AudioRequest):
    url = audio_request.url
    # vad_val = audio_request.vad_level
    vad_val = 3
    # chunk_size = audio_request.chunk_size
    chunk_size = 10
    language = audio_request.language
    retsore_punct = audio_request.restore_punct

    if "youtube.com" in url or "youtu.be" in url:
        audio_url = download_yt_audio(url)
    else:
        audio_url = url

    return process_audio(audio_url, vad_val, chunk_size, language, retsore_punct)


def get_punctuated(transcript, lang, restore_punct=True):
    if restore_punct:
        if lang == "en":
            tr_nopunct = transcript.translate(
                str.maketrans(string.punctuation, " " * len(string.punctuation))
            ).lower()
            tr_nopunct = " ".join(tr_nopunct.split())
            if tr_nopunct != "":
                transcript = rpunct.punctuate(tr_nopunct, batch_size=128)
                print(transcript)
                print("Punctuation complete.")
    return transcript


def process_audio(audio_url, vad_val, chunk_size, language, restore_punct=True):
    status = "SUCCESS"
    # la = req_data['config']['language']['sourceLanguage']
    # af = req_data['config']['audioFormat']
    if audio_url in [None, ""]:
        status = "ERROR"
        return {"status": status, "output": ""}
    elif audio_url.startswith("media"):
        fp_arr = load_data(audio_url, of="raw")
    else:
        print("Loading data from url..")
        fp_arr = load_data(audio_url, of="url")

    # try:
    #     fp_arr = load_data(audio_uri,of='raw')
    # except Exception as e:
    #     status = 'ERROR'
    #     print(e)
    #     return jsonify({"status":status, "output":""})
    # return jsonify({'op':align(fp_arr,cuda)})
    op = "WEBVTT\n\n"
    op_nochunk = "WEBVTT\n\n"
    sample_rate = 16000
    vad = webrtcvad.Vad(vad_val)  # 2
    frames = frame_generator(10, fp_arr, sample_rate)
    frames = list(frames)
    segments = list(vad_collector(sample_rate, 10, 100, vad, frames))
    vad_time_stamps = []
    counter = 1
    print("Transcribing..")
    for i, (segment, (start_frame, end_frame)) in enumerate(
        tqdm(segments, total=len(segments))
    ):
        song = AudioSegment.from_raw(
            io.BytesIO(segment), sample_width=2, frame_rate=16000, channels=1
        )
        samples = song.get_array_of_samples()
        fp_arr = np.array(samples).T.astype(np.float64)
        fp_arr /= np.iinfo(samples.typecode).max
        arr = fp_arr.reshape(-1)

        op_nochunk += str(i + 1) + "\n"
        op_nochunk += (
            "{0}.000 --> {1}.000".format(
                time.strftime("%H:%M:%S", time.gmtime(start_frame)),
                time.strftime("%H:%M:%S", time.gmtime(end_frame)),
            )
            + "\n"
        )
        # arr = np.array(samples)
        # print(f'Start frame: {start_frame},\t End frame: {end_frame}')
        for e, frame in enumerate(range(0, len(arr), int(chunk_size))):
            # op += str(i+e+1) + '\n'
            if end_frame - frame - start_frame <= chunk_size + 0.1:
                # op += "{0}.000 --> {1}.000".format(time.strftime('%H:%M:%S', time.gmtime(start_frame+frame)),time.strftime('%H:%M:%S', time.gmtime(end_frame)))+'\n'
                # print(len(arr[int((start_frame+frame)*16000):int((end_frame)*16000)]),'Done')
                # print(end_frame-frame-start_frame)
                op_pred = (
                    align(
                        arr[int((frame) * 16000) : int((end_frame) * 16000)],
                        DEVICE,
                        language,
                        restore_punct,
                    )
                    + "\n\n"
                )
                if len(op_pred.strip()) > 2:
                    op += str(counter) + "\n"
                    counter += 1
                    # op += str(i+e+1) + '\n'
                    op += (
                        "{0}.000 --> {1}.000".format(
                            time.strftime("%H:%M:%S", time.gmtime(start_frame + frame)),
                            time.strftime("%H:%M:%S", time.gmtime(end_frame)),
                        )
                        + "\n"
                    )
                    op += op_pred
                    op_nochunk += op_pred
                # op+= op_pred
                # op_nochunk += op_pred
                break
            else:
                # print('\nHere')
                # print(int((start_frame+frame)*16000),int((start_frame+frame+5.1)*16000),'Done')
                op_pred = align(
                    arr[int((frame) * 16000) : int((frame + chunk_size + 0.1) * 16000)],
                    DEVICE,
                    language,
                )
                if len(op_pred.strip()) > 2:
                    op += str(counter) + "\n"
                    counter += 1
                    # op += str(i+e+1) + '\n'
                    op += (
                        "{0}.000 --> {1}.000".format(
                            time.strftime("%H:%M:%S", time.gmtime(start_frame + frame)),
                            time.strftime(
                                "%H:%M:%S",
                                time.gmtime(start_frame + frame + chunk_size),
                            ),
                        )
                        + "\n"
                    )
                    op += op_pred + "\n"
                    op_nochunk += op_pred + " "

                # op += "{0}.000 --> {1}.000".format(time.strftime('%H:%M:%S', time.gmtime(start_frame+frame)),time.strftime('%H:%M:%S', time.gmtime(start_frame+frame+chunk_size)))+'\n'
                # op_pred = align(arr[int((frame)*16000):int((frame+chunk_size+0.1)*16000)],cuda)
                # op+= op_pred + '\n'
                # op_nochunk += op_pred +' '
            op += "\n"
        op_nochunk += "\n"
    #    print(op)
    # return jsonify({'output':op})
    # op += str(i+1) + '\n'
    # op += "{0}.000 --> {1}.000".format(time.strftime('%H:%M:%S', time.gmtime(start_frame)),time.strftime('%H:%M:%S', time.gmtime(end_frame)))+'\n'
    # op += align(arr,cuda) +'\n'
    # print(op)

    with open("placeholder.vtt", "w") as f:
        f.write(op)

    captions = webvtt.read("placeholder.vtt")

    print("Punctuating..")
    all_text = ""
    word_positions = [0]
    for i in range(len(captions)):
        all_text += captions[i].text + " "
        word_positions.append(len(all_text.split()))
    punct_text = get_punctuated(all_text, language, restore_punct=restore_punct)
    punct_words = punct_text.split()
    print("Lengths", len(punct_words), len(all_text.split()))
    for i in range(len(captions)):
        captions[i].text = " ".join(
            punct_words[word_positions[i] : word_positions[i + 1]]
        )

    ## Batch punctuation (depreciated because punctuation model won't perform best if each chunk is sent individually)
    # all_captions = []
    # for i in range(len(captions)):
    #     tr_nopunct = captions[i].text.translate(str.maketrans(string.punctuation, ' '*len(string.punctuation))).lower()
    #     tr_nopunct = " ".join(tr_nopunct.split())
    #     all_captions.append(tr_nopunct)
    # punct_captions = rpunct.punctuate_batch(all_captions, batch_size=128)
    # for i in range(len(captions)):
    #     captions[i].text = punct_captions[i]

    merged_caption = webvtt.WebVTT()

    for i in range(0, len(captions), 2):
        if i + 1 < len(captions):
            curr_caption_len = len(captions[i].text.split(" "))
            next_caption_len = len(captions[i + 1].text.split(" "))

            if curr_caption_len <= 4 or next_caption_len <= 4:

                m_cap = webvtt.Caption(
                    captions[i].start,
                    captions[i + 1].end,
                    captions[i].text + " " + captions[i + 1].text,
                )
                merged_caption.captions.append(m_cap)

            else:
                m_cap = webvtt.Caption(
                    captions[i].start, captions[i].end, captions[i].text
                )
                merged_caption.captions.append(m_cap)

                m_cap = webvtt.Caption(
                    captions[i + 1].start, captions[i + 1].end, captions[i + 1].text
                )
                merged_caption.captions.append(m_cap)

        if i == len(captions):
            m_cap = webvtt.Caption(
                captions[i + 1].start, captions[i + 1].end, captions[i + 1].text
            )
            merged_caption.captions.append(m_cap)

    op = merged_caption.content
    return {"status": status, "output": op, "vad_nochunk": op_nochunk}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5050)
