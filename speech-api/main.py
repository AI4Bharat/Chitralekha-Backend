from typing import Optional
import math
import json
import time
import os
import sys
import io
from multiprocessing import Process

from fastapi import FastAPI
from pydantic import BaseModel
import webvtt
from pydub import AudioSegment
import webrtcvad
from yt_dlp import YoutubeDL

import numpy as np
import torch
from omegaconf import OmegaConf
import urllib

from support import load_model,W2lKenLMDecoder,W2lViterbiDecoder,load_data
from vad import frame_generator, vad_collector

MEDIA_FOLDER = "media/"
CONFIG_PATH = "config.json"
DEVICE = "cuda"

print("Modules imported")

os.makedirs(MEDIA_FOLDER, exist_ok=True)

app = FastAPI()
with open(CONFIG_PATH,'r') as j:
    config = json.load(j)

print("Config loaded.")

print("Loading models from config..")
name2model_dict = dict()
for k,m in config.items():
    if eval(m['lm_usage']):
        lmarg = OmegaConf.create(m['lm_details'])
        lmarg.unk_weight = -math.inf
        model,dictionary = load_model(m['model_path'])
        if DEVICE != 'cpu' and torch.cuda.is_available():
            model.to(DEVICE)
        generator = W2lKenLMDecoder(lmarg, dictionary)
    else:
        lmarg = OmegaConf.create({'nbest':1})
        model,dictionary = load_model(m['model_path'])
        if DEVICE != 'cpu' and torch.cuda.is_available():
            model.to(DEVICE)
        generator = W2lViterbiDecoder(lmarg, dictionary)
    name2model_dict[k] = [model,generator,dictionary]


def align(fp_arr,DEVICE):
    feature = torch.from_numpy(fp_arr).float()
    if DEVICE != 'cpu' and torch.cuda.is_available():
        feature = feature.to(DEVICE)
    sample = {"net_input":{"source":None,"padding_mask":None}}
    sample["net_input"]["source"] = feature.unsqueeze(0)
    if DEVICE != 'cpu' and torch.cuda.is_available():
        sample["net_input"]["padding_mask"] = torch.BoolTensor(sample["net_input"]["source"].size(1)).fill_(False).unsqueeze(0).to(DEVICE)
    else:
        sample["net_input"]["padding_mask"] = torch.BoolTensor(sample["net_input"]["source"].size(1)).fill_(False).unsqueeze(0)
        
    model,generator,dictionary = name2model_dict['en']

    with torch.no_grad():
        hypo = generator.generate([model], sample, prefix_tokens=None)
    hyp_pieces = dictionary.string(hypo[0][0]["tokens"].int().cpu())
    tr = hyp_pieces.replace(' ','').replace('|',' ').strip()
    return tr


ydl_opts_audio = {
    'format': 'bestaudio[ext=m4a]',
    'outtmpl': MEDIA_FOLDER+'/%(id)s.m4a',
}
ydl_audio = YoutubeDL(ydl_opts_audio)
def download_yt_audio(url):
    info = ydl_audio.extract_info(url, download=True)
    downloaded_audio_path = os.path.join(MEDIA_FOLDER, info['id']) + '.m4a'
    return downloaded_audio_path


@app.on_event("startup")
async def startup_event():
    print("Model loaded.")

@app.get("/")
async def root():
    return {"message": "Welcome to AI4Bharat Speech-to-Text API. \
Visit /docs for usage information."}

class VideoRequest(BaseModel):
    url: str

@app.post("/download_video_to_local/")
async def download_video_to_local(video_request: VideoRequest):
    yt_url = video_request.url
    ydl_best = YoutubeDL({'format': 'best'})
    downloaded_audio_path = download_yt_audio(yt_url)
    info = ydl_best.extract_info(yt_url, download=False)
    print(info.keys())
    direct_url = info['url']
    print(direct_url)
    if os.path.isfile(downloaded_audio_path):
        # Vieo will be downloaded in background
        # Process(target=download_yt_video, args=(yt_url, )).start()

        downloaded_video_path = downloaded_audio_path.replace('.m4a', '.webm')
        return {
            'success': True,
            'audio_url': downloaded_audio_path,
            'download_path': downloaded_video_path,
            'video_url': direct_url,
        }
    return {
        'success': False,
    }


class AudioRequest(BaseModel):
    audio_url: str
    vad_level: Optional[int] = 2
    chunk_size: Optional[float] = 10.0
    language: Optional[str] = 'en'

@app.post("/transcribe_audio/")
async def transcribe_audio(audio_request: AudioRequest):
    status = "SUCCESS"
    audio_url = audio_request.audio_url
    vad_val = audio_request.vad_level
    chunk_size = audio_request.chunk_size
    language = audio_request.language
    #la = req_data['config']['language']['sourceLanguage']
    #af = req_data['config']['audioFormat']
    if audio_url in [None,'']:
        status = 'ERROR'
        return {"status":status, "output":""}
    elif audio_url.startswith('media'):
        fp_arr = load_data(audio_url,of='raw')
    else:
        fp_arr = load_data(audio_url, of='url')

    # try:
    #     fp_arr = load_data(audio_uri,of='raw')
    # except Exception as e:
    #     status = 'ERROR' 
    #     print(e)
    #     return jsonify({"status":status, "output":""})
    #return jsonify({'op':align(fp_arr,cuda)})
    op = "WEBVTT\n\n"
    op_nochunk = "WEBVTT\n\n"
    sample_rate = 16000
    vad = webrtcvad.Vad(vad_val) #2
    frames = frame_generator(30, fp_arr, sample_rate)
    frames = list(frames)
    segments = vad_collector(sample_rate, 30, 300, vad, frames)
    vad_time_stamps = []
    counter = 1
    for i, (segment, (start_frame, end_frame)) in enumerate(segments):
        song=AudioSegment.from_raw(io.BytesIO(segment), sample_width=2, frame_rate=16000, channels=1)
        samples = song.get_array_of_samples()
        fp_arr = np.array(samples).T.astype(np.float64)
        fp_arr /= np.iinfo(samples.typecode).max
        arr = fp_arr.reshape(-1)
        
        op_nochunk += str(i+1) + '\n'
        op_nochunk += "{0}.000 --> {1}.000".format(time.strftime('%H:%M:%S', time.gmtime(start_frame)),time.strftime('%H:%M:%S', time.gmtime(end_frame)))+'\n'
        #arr = np.array(samples)
        # print(f'Start frame: {start_frame},\t End frame: {end_frame}')
        for e,frame in enumerate(range(0,len(arr),int(chunk_size))):        
            #op += str(i+e+1) + '\n'
            if end_frame-frame-start_frame <= chunk_size + 0.1:
                #op += "{0}.000 --> {1}.000".format(time.strftime('%H:%M:%S', time.gmtime(start_frame+frame)),time.strftime('%H:%M:%S', time.gmtime(end_frame)))+'\n'
                # print(len(arr[int((start_frame+frame)*16000):int((end_frame)*16000)]),'Done')
                # print(end_frame-frame-start_frame)
                op_pred = align(arr[int((frame)*16000):int((end_frame)*16000)],DEVICE) +'\n\n' 
                if len(op_pred.strip()) >2:
                     op += str(counter) + '\n'
                     counter += 1
                     #op += str(i+e+1) + '\n'
                     op += "{0}.000 --> {1}.000".format(time.strftime('%H:%M:%S', time.gmtime(start_frame+frame)),time.strftime('%H:%M:%S', time.gmtime(end_frame)))+'\n' 
                     op+= op_pred
                     op_nochunk += op_pred
                #op+= op_pred
                #op_nochunk += op_pred
                break
            else:
                #print('\nHere')
                # print(int((start_frame+frame)*16000),int((start_frame+frame+5.1)*16000),'Done')
                op_pred = align(arr[int((frame)*16000):int((frame+chunk_size+0.1)*16000)],DEVICE)
                if len(op_pred.strip()) > 2:
                     op += str(counter) + '\n'
                     counter += 1
                     #op += str(i+e+1) + '\n'
                     op += "{0}.000 --> {1}.000".format(time.strftime('%H:%M:%S', time.gmtime(start_frame+frame)),time.strftime('%H:%M:%S', time.gmtime(start_frame+frame+chunk_size)))+'\n'
                     op+= op_pred + '\n'
                     op_nochunk += op_pred +' '

                #op += "{0}.000 --> {1}.000".format(time.strftime('%H:%M:%S', time.gmtime(start_frame+frame)),time.strftime('%H:%M:%S', time.gmtime(start_frame+frame+chunk_size)))+'\n'
                #op_pred = align(arr[int((frame)*16000):int((frame+chunk_size+0.1)*16000)],cuda)
                #op+= op_pred + '\n'
                #op_nochunk += op_pred +' '
            op += '\n'
        op_nochunk += '\n'
    #    print(op)
    #return jsonify({'output':op})
        # op += str(i+1) + '\n'
        # op += "{0}.000 --> {1}.000".format(time.strftime('%H:%M:%S', time.gmtime(start_frame)),time.strftime('%H:%M:%S', time.gmtime(end_frame)))+'\n'
        # op += align(arr,cuda) +'\n'
    #print(op)

    with open('placeholder.vtt', 'w') as f:
        f.write(op)

    captions = webvtt.read('placeholder.vtt')

    merged_caption = webvtt.WebVTT()

    for i in range(0, len(captions), 2):
        if i + 1 < len(captions):
            curr_caption_len = len(captions[i].text.split(' '))
            next_caption_len = len(captions[i+1].text.split(' '))

            if curr_caption_len <= 4 or next_caption_len <= 4:

                m_cap = webvtt.Caption(
                    captions[i].start,
                    captions[i+1].end,
                    captions[i].text + ' ' + captions[i+1].text
                )
                merged_caption.captions.append(m_cap)

            else:
                m_cap = webvtt.Caption(
                    captions[i].start,
                    captions[i].end,
                    captions[i].text
                )
                merged_caption.captions.append(m_cap)

                m_cap = webvtt.Caption(
                    captions[i+1].start,
                    captions[i+1].end,
                    captions[i+1].text
                )
                merged_caption.captions.append(m_cap)

        if i == len(captions):
            m_cap = webvtt.Caption(
                captions[i+1].start,
                captions[i+1].end,
                captions[i+1].text
            )
            merged_caption.captions.append(m_cap)

    op = merged_caption.content
    return {"status":status, "output":op,'vad_nochunk':op_nochunk}
