from flask import Flask, request
from flask import jsonify
from flask_cors import CORS, cross_origin
from omegaconf import OmegaConf
import numpy as np, math, torch, json
from support import load_model, W2lKenLMDecoder, W2lViterbiDecoder, load_data
import time, os
import sys
import webvtt
from nltk import sent_tokenize

# from punctuate import RestorePuncts
from yt_dlp import YoutubeDL
import ffmpeg
import datetime
import re
from gevent.pywsgi import WSGIServer
import subprocess

import io
from pydub import AudioSegment
import webrtcvad
from vad import frame_generator, vad_collector

from multiprocessing import Process

cuda = sys.argv[1]
# punct_model = RestorePuncts()

with open("config.json", "r") as j:
    config = json.load(j)

name2model_dict = dict()
for k, m in config.items():
    if eval(m["lm_usage"]):
        lmarg = OmegaConf.create(m["lm_details"])
        lmarg.unk_weight = -math.inf
        model, dictionary = load_model(m["model_path"])
        if cuda != "cpu" and torch.cuda.is_available():
            model.to(cuda)
        generator = W2lKenLMDecoder(lmarg, dictionary)
    else:
        lmarg = OmegaConf.create({"nbest": 1})
        model, dictionary = load_model(m["model_path"])
        if cuda != "cpu" and torch.cuda.is_available():
            model.to(cuda)
        generator = W2lViterbiDecoder(lmarg, dictionary)
    name2model_dict[k] = [model, generator, dictionary]


def align(fp_arr, cuda):
    feature = torch.from_numpy(fp_arr).float()
    if cuda != "cpu" and torch.cuda.is_available():
        feature = feature.to(cuda)
    sample = {"net_input": {"source": None, "padding_mask": None}}
    sample["net_input"]["source"] = feature.unsqueeze(0)
    if cuda != "cpu" and torch.cuda.is_available():
        sample["net_input"]["padding_mask"] = (
            torch.BoolTensor(sample["net_input"]["source"].size(1))
            .fill_(False)
            .unsqueeze(0)
            .to(cuda)
        )
    else:
        sample["net_input"]["padding_mask"] = (
            torch.BoolTensor(sample["net_input"]["source"].size(1))
            .fill_(False)
            .unsqueeze(0)
        )

    model, generator, dictionary = name2model_dict["en"]

    with torch.no_grad():
        hypo = generator.generate([model], sample, prefix_tokens=None)
    hyp_pieces = dictionary.string(hypo[0][0]["tokens"].int().cpu())
    tr = hyp_pieces.replace(" ", "").replace("|", " ").strip()
    return tr


# ----------------------------------------------

MEDIA_FOLDER = "static/media"
os.makedirs(MEDIA_FOLDER, exist_ok=True)
# ydl_opts = {'outtmpl': MEDIA_FOLDER+'/%(id)s'}
ydl_opts_audio = {
    "format": "bestaudio[ext=m4a]",
    "outtmpl": MEDIA_FOLDER + "/%(id)s.m4a",
}
ydl_audio = YoutubeDL(ydl_opts_audio)


def download_yt_audio(url):
    info = ydl_audio.extract_info(url, download=True)
    downloaded_audio_path = os.path.join(MEDIA_FOLDER, info["id"]) + ".m4a"
    return downloaded_audio_path


ydl_opts_video = {
    #'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
    "outtmpl": MEDIA_FOLDER
    + "/%(id)s.webm"
}

ydl_video = YoutubeDL(ydl_opts_video)


def download_yt_video(yt_url):
    return yt_url
    # info = ydl_video.extract_info(yt_url, download=True)
    # downloaded_video_path = os.path.join(MEDIA_FOLDER, info['id']) + '.webm'
    # return downloaded_video_path


app = Flask(__name__)
cors = CORS(app)
app.config["CORS_HEADERS"] = "Content-Type"


@app.route("/")
@cross_origin()
def hello_world():
    return "<p>Hi</p>"


@app.route("/download_video_to_local", methods=["POST"])
def download_video_to_local():
    yt_url = request.form["url"]
    ydl_best = YoutubeDL({"format": "best"})
    downloaded_audio_path = download_yt_audio(yt_url)
    info = ydl_best.extract_info(yt_url, download=False)
    print(info.keys())
    direct_url = info["url"]
    print(direct_url)
    if os.path.isfile(downloaded_audio_path):
        # Vieo will be downloaded in background
        Process(target=download_yt_video, args=(yt_url,)).start()

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


@app.route("/transcribe_local_audio", methods=["POST"])
@cross_origin()
def transcribe_local_audio():
    req_data = json.loads(request.data)
    status = "SUCCESS"
    # print(req_data)
    audio_uri = req_data.get("audio_url", None)
    vad_val = req_data.get("vad_level", 2)
    chunk_size = float(req_data.get("chunk_size", 10.0))
    # la = req_data['config']['language']['sourceLanguage']
    # af = req_data['config']['audioFormat']
    if audio_uri in [None, ""]:
        status = "ERROR"
        return jsonify({"status": status, "output": ""})
    print(audio_uri)
    fp_arr = load_data(audio_uri, of="raw")

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
    segments = vad_collector(sample_rate, 30, 300, vad, frames)
    vad_time_stamps = []
    counter = 1
    for i, (segment, (start_frame, end_frame)) in enumerate(segments):
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
                    align(arr[int((frame) * 16000) : int((end_frame) * 16000)], cuda)
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
                    cuda,
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
    return jsonify({"status": status, "output": op, "vad_nochunk": op_nochunk})

    """
    captions = webvtt.read('placeholder.vtt')
    source_sentences = [caption.text.replace('\r', '').replace('\n', ' ') for caption in captions]

    sent = ' '.join(source_sentences)
    sent = sent.lower()
    sent = re.sub(r'[^\w\s]', '', sent)
    punctuated = punct_model.punctuate(sent)
    tokenised = sent_tokenize(punctuated)

    # words = punctuated.split(' ')

    # len_marker = 0
    # for i in range(len(captions)):
    #     curr = len(captions[i].text.split(' '))
    #     captions[i].text = ' '.join(words[len_marker: len_marker+curr])
    #     len_marker += curr
    #     # return captions.content
    # captions.save('normalised.vtt')
    final_vtt = webvtt.WebVTT()
    start = datetime.datetime.strptime('00:00:00.000', '%H:%M:%S.%f')

    for i in range(len(tokenised)):
        len_ = len(tokenised[i].split(' '))
        secs = len_ // 2
        micro = round((len_/3)%1*1000)
        delta = datetime.timedelta(seconds=secs, microseconds=micro)
        end = start + delta
        caption = webvtt.Caption(
            start.time().strftime('%H:%M:%S.%f'),
            end.time().strftime('%H:%M:%S.%f'),
            tokenised[i]
        )
        start = end
        final_vtt.captions.append(caption)
    
    final_vtt.save('normalised.vtt')

    with open('normalised.vtt', 'r') as f:
        content = f.read()

    return jsonify({"status":status, "output":content})
    # return jsonify({"status":status, "output":""})
    # return None
    """


if __name__ == "__main__":
    # app.logger.setLevel(logging.DEBUG)
    # from gevent import pywsgi
    # from geventwebsocket.handler import WebSocketHandler

    server = WSGIServer(("", 5000), app)
    print("Server listening on: http://localhost:" + str(5000))
    server.serve_forever()

# @app.route("/infer_ulca_en",methods=['POST'])
# @cross_origin()
# def infer_ulca_en():
#    req_data = json.loads(request.data)
#    status = "SUCCESS"
#    preds = []
#    for f in req_data['audio']:
#        audio_uri, audio_bytes = f.get('audioUri',None),f.get('audioContent',None)
#        la = req_data['config']['language']['sourceLanguage']
#        af = req_data['config']['audioFormat']
#        if audio_uri in [None,''] and audio_bytes in [None,'']:
#            status = 'ERROR'
#            continue
#        try:
#            if audio_bytes == None:
#                fp_arr = load_data(audio_uri,of='url',lang=la)
#            else:
#                nm = str(round(time.time() * 1000))
#                fp_arr = load_data(audio_bytes,of='bytes',lang=la,bytes_name=nm+"."+af)
#        except:
#            status = 'ERROR'
#            continue
#
#        op = "WEBVTT\n\n"
#        for e,frame in enumerate(range(0,len(fp_arr),5)):
#            op += str(e+1) + '\n'
#            op += "{0}.000 --> {1}.000".format(time.strftime('%H:%M:%S', time.gmtime(frame)),time.strftime('%H:%M:%S', time.gmtime(frame+5)))+'\n'
#            try:
#                op+= align(fp_arr[frame*16000:int((frame+5.1)*16000)],cuda) +'\n'
#                #print(align(fp_arr[frame*16000:int((frame+5.1)*16000)],cuda))
#            except:
#                op += ''
#                break
#            op += '\n'

# preds.append({'source':op})
# print(op)

#        with open('placeholder.vtt', 'w') as f:
#            f.write(op)

#        captions = webvtt.read('placeholder.vtt')
#        source_sentences = [caption.text.replace('\r', '').replace('\n', ' ') for caption in captions]
#
#        sent = ' '.join(source_sentences)
#        sent = sent.lower()
#        punctuated = punct_model.punctuate(sent)
#        # tokenised = sent_tokenize(punctuated)
#
#        words = punctuated.split(' ')
#
#        len_marker = 0
#        for i in range(len(captions)):
#           curr = len(captions[i].text.split(' '))
#          captions[i].text = ' '.join(words[len_marker: len_marker+curr])
#
#           len_marker += curr
#      # return captions.content
#     captions.save('normalised.vtt')
#
#       with open('normalised.vtt', 'r') as f:
#          content = f.read()
#
#       preds.append({'source':content})
#  return jsonify({"status":status, "output":preds})
