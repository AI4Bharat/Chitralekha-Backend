from typing import Optional
import math
import json
import time
import os
import shutil
import sys
import io
from multiprocessing import Process
import string
import logging

logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)
import gdown
from pathlib import Path
import subprocess

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
import whisper
import nemo.collections.asr as nemo_asr


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

TOKEN_OFFSET = 100

# # Load punctuation model
# rpunct = RestorePuncts()
# print("Punctuation model loaded.")
# # output = rpunct.punctuate("i am here to introduce the course data science for engineers")
# outputs = rpunct.punctuate_batch([
#     "i am here to introduce the course data science for engineers",
#     "hello how are you",
#     "i am fine what about you",
#     "my name is giorgio giovanni"
#     ])
# print(outputs)
# # breakpoint()

print("Loading models from config..")
name2model_dict = dict()
for k, m in config.items():
    if m["model_type"] == "IndicWav2Vec":
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
        name2model_dict[k] = [m["model_type"], model, (generator, dictionary)]

    elif m["model_type"] == "IndicTinyASR":
        model = nemo_asr.models.EncDecCTCModel.restore_from(
            restore_path=m["model_path"]
        )
        model.freeze()
        # model.decoder.freeze()
        print(list(model.decoder.vocabulary), m["lm_path"])
        vocab = model.decoder.vocabulary
        vocab = [chr(idx + TOKEN_OFFSET) for idx in range(len(vocab))]
        beam_search = nemo_asr.modules.BeamSearchDecoderWithLM(
            vocab=vocab,
            beam_width=128,
            alpha=0.7,
            beta=-0.5,  # TODO: Change the values
            lm_path=m["lm_path"],
            num_cpus=max(os.cpu_count(), 1),
            input_tensor=False,
        )
        name2model_dict[k] = (m["model_type"], model, beam_search)


en_model = whisper.load_model("medium.en").to("cuda:3")


def softmax(logits):
    e = np.exp(logits - np.max(logits))
    return e / e.sum(axis=-1).reshape([logits.shape[0], 1])


def align_nemo(fp_arr, DEVICE, lang, restore_punct=True):
    _, asr, beam_search = name2model_dict[lang]
    ids_to_text_func = asr.tokenizer.ids_to_text
    feature = torch.from_numpy(fp_arr).float()
    lengths = torch.Tensor([len(feature)])
    # model = name2model_dict['hi']
    if DEVICE != "cpu" and torch.cuda.is_available():
        feature = feature.cuda()
        lengths = lengths.cuda()
        asr = asr.cuda()
    asr.freeze()
    # model.decoder.freeze()
    with torch.no_grad():
        logits, logits_len, greedy_predictions = asr.forward(
            input_signal=feature.unsqueeze(0).cuda(), input_signal_length=lengths
        )
        current_hypotheses, all_hyp = asr.decoding.ctc_decoder_predictions_tensor(
            logits,
            decoder_lengths=logits_len,
            return_hypotheses=True,
        )
        text = current_hypotheses[0].text
    return text


def align_w2v(fp_arr, DEVICE, lang, restore_punct=True):

    _, model, (generator, dictionary) = name2model_dict[lang]
    DEVICE = next(model.parameters()).device

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

    with torch.no_grad():
        hypo = generator.generate([model], sample, prefix_tokens=None)
    hyp_pieces = dictionary.string(hypo[0][0]["tokens"].int().cpu())
    tr = hyp_pieces.replace(" ", "").replace("|", " ").strip()
    return tr


def align(fp_arr, DEVICE, lang, restore_punct=True):

    model_type, _, _ = name2model_dict[lang]
    if model_type == "IndicWav2Vec":
        text = align_w2v(fp_arr, DEVICE, lang, restore_punct=True)
    elif model_type == "IndicTinyASR":
        text = align_nemo(fp_arr, DEVICE, lang, restore_punct=True)
    return text


ydl_opts_audio = {
    "format": "bestaudio[ext=m4a]",
    "outtmpl": MEDIA_FOLDER + "/%(id)s.m4a",
}
ydl_audio = YoutubeDL(ydl_opts_audio)


def download_yt_audio(url):
    info = ydl_audio.extract_info(url, download=True)
    downloaded_audio_path = os.path.join(MEDIA_FOLDER, info["id"]) + ".m4a"
    # Create a new folder for each file to perform audio enhancement
    new_audio_folder = os.path.join(MEDIA_FOLDER, info["id"])
    Path(new_audio_folder).mkdir(exist_ok=True, parents=True)
    new_file_path = os.path.join(new_audio_folder, info["id"] + ".m4a")
    shutil.move(downloaded_audio_path, new_file_path)
    return new_file_path


drive_opts_audio = {
    "format": "bestaudio[ext=mp3]",
    "outtmpl": MEDIA_FOLDER + "/%(id)s.mp3",
}
drive_audio = YoutubeDL(drive_opts_audio)


def download_drive_audio(url):
    output = gdown.download(url=url, quiet=False, fuzzy=True)
    new_audio_folder = os.path.join(MEDIA_FOLDER, Path(output).stem)
    Path(new_audio_folder).mkdir(exist_ok=True, parents=True)
    downloaded_audio_path = os.path.join(new_audio_folder, output)
    print(f"Downloaded audio path: {downloaded_audio_path}")
    shutil.move(output, downloaded_audio_path)
    subprocess.call(
        [
            "ffmpeg",
            "-y",
            "-i",
            downloaded_audio_path,
            "-ar",
            "16k",
            "-ac",
            "1",
            "-hide_banner",
            "-loglevel",
            "error",
            downloaded_audio_path + "new.wav",
        ]
    )
    # if Path(output).suffix in [".mp3"]:
    #     sound = AudioSegment.from_mp3(downloaded_audio_path)
    #     downloaded_audio_path = downloaded_audio_path.replace(".mp3", ".wav")
    #     sound.export(downloaded_audio_path, format="wav")
    return downloaded_audio_path + "new.wav"


@app.on_event("startup")
async def startup_event():
    print("Model loaded.")


@app.get("/")
async def homepage():
    # Redirect homepage to Swagger
    return RedirectResponse(url="/docs")


indic_language_dict = {
    "English": "en",
    "Hindi": "hi",
    "Bengali": "bn",
    "Gujarati": "gu",
    "Kannada": "kn",
    "Malayalam": "ml",
    "Marathi": "mr",
    "Odia": "or",
    "Punjabi": "pa",
    "Sanskrit": "sa",
    "Tamil": "ta",
    "Telugu": "te",
    "Urdu": "ur",
}

# indic_language_dict = {
#     'English' : 'en',
#     'Hindi' : 'hi',
#     'Bengali' : 'bn',
#     'Gujarati' : 'gu',
#     'Marathi' : 'mr',
#     'Odia' : 'or',
#     'Tamil' : 'ta',
#     'Telugu' : 'te',
# }


@app.get("/supported_languages")
async def supported_languages():
    return indic_language_dict


@app.get("/get_youtube_video_link_with_captions")
@app.post("/get_youtube_video_link_with_captions")
async def _get_youtube_video_link_with_captions(url: str, lang: str = "en"):

    return get_yt_video_and_subs(url, lang)


class VideoRequest(BaseModel):
    url: str


# @app.post("/download_video_to_local")
# async def download_video_to_local(video_request: VideoRequest):
#     yt_url = video_request.url
#     ydl_best = YoutubeDL({'format': 'best'})
#     downloaded_audio_path = download_yt_audio(yt_url)
#     info = ydl_best.extract_info(yt_url, download=False)
#     print(info.keys())
#     direct_url = info['url']
#     print(direct_url)
#     if os.path.isfile(downloaded_audio_path):
#         # Vieo will be downloaded in background
#         # Process(target=download_yt_video, args=(yt_url, )).start()

#         downloaded_video_path = downloaded_audio_path.replace('.m4a', '.webm')
#         return {
#             'success': True,
#             'audio_url': downloaded_audio_path,
#             'download_path': downloaded_video_path,
#             'video_url': direct_url,
#         }
#     return {
#         'success': False,
#     }


class AudioRequest(BaseModel):
    url: str
    vad_level: Optional[int] = 3.0
    chunk_size: Optional[float] = 10.0
    language: Optional[str] = "en"
    restore_punct: Optional[bool] = True
    denoiser: Optional[bool] = False


@app.post("/transcribe")
async def transcribe_audio(audio_request: AudioRequest):
    url = audio_request.url
    vad_val = audio_request.vad_level
    # chunk_size = audio_request.chunk_size
    chunk_size = 10
    language = audio_request.language
    retsore_punct = audio_request.restore_punct
    is_denoiser = audio_request.denoiser

    if "youtube.com" in url or "youtu.be" in url:
        print("Loaded from youtube URL")
        audio_url = download_yt_audio(url)
    elif "drive.google.com" in url:
        print("Loaded from drive URL")
        audio_url = download_drive_audio(url)
    else:
        audio_url = url

    return process_audio(
        audio_url, vad_val, chunk_size, language, is_denoiser, retsore_punct
    )


def get_punctuated(transcript, lang, restore_punct=True):
    # if restore_punct:
    #     if lang == 'en':
    #         tr_nopunct = transcript.translate(str.maketrans(string.punctuation, ' '*len(string.punctuation))).lower()
    #         tr_nopunct = " ".join(tr_nopunct.split())
    #         if tr_nopunct != '':
    #             transcript = rpunct.punctuate(tr_nopunct, batch_size=128)
    #             print(transcript)
    #             print("Punctuation complete.")
    return transcript


def process_audio(
    audio_url, vad_val, chunk_size, language, denoiser=False, restore_punct=True
):
    status = "SUCCESS"
    # la = req_data['config']['language']['sourceLanguage']
    # af = req_data['config']['audioFormat']
    if audio_url in [None, ""]:
        status = "ERROR"
        return {"status": status, "output": ""}
    elif audio_url.startswith("media"):
        fp_arr, output_wavpath = load_data(audio_url, of="raw", denoiser=denoiser)
    else:
        print("Loading data from url..")
        fp_arr, output_wavpath = load_data(audio_url, of="url", denoiser=denoiser)

    if language == "en":
        result = en_model.transcribe(
            output_wavpath,
            language="en",
        )
        op = "WEBVTT\n\n"

        for idx, segment in enumerate(result["segments"]):
            op += str(idx + 1) + "\n"
            op += (
                "{0}.000 --> {1}.000".format(
                    time.strftime("%H:%M:%S", time.gmtime(segment["start"])),
                    time.strftime("%H:%M:%S", time.gmtime(segment["end"])),
                )
                + "\n"
            )
            op += segment["text"]
            op += "\n\n"

        return {"status": status, "output": op}

    print(f"Length of loaded array: {len(fp_arr)}")

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
    frames = frame_generator(30, fp_arr, sample_rate)
    frames = list(frames)
    segments = list(vad_collector(sample_rate, 30, 300, vad, frames))
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
