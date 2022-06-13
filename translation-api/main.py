from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from pydantic import BaseModel
from starlette.responses import RedirectResponse

import time

import re
from math import floor
import webvtt
from io import StringIO

from indicTrans.inference.engine import Model, split_sentences
from punctuate import RestorePuncts
from lemmatizer import lemmatize

app = FastAPI(debug=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# print("Loading Indic-En Model..")
# indic2en_model = Model(expdir='models/indic-en')
# print("Loading En-Indic Model..")
# en2indic_model = Model(expdir='models/en-indic')
print("Loading M2M Model..")
m2m_model = Model(expdir='models/m2m')

rpunct = RestorePuncts('hi')
indic_language_dict = {
    'Assamese': 'as',
    'Hindi' : 'hi',
    'Marathi' : 'mr',
    'Tamil' : 'ta',
    'Bengali' : 'bn',
    'Kannada' : 'kn',
    'Oriya' : 'or',
    'Telugu' : 'te',
    'Gujarati' : 'gu',
    'Malayalam' : 'ml',
    'Punjabi' : 'pa',
}
# splitter = MosesSentenceSplitter('en')

def get_inference_params(source_language, target_language):

    if source_language in indic_language_dict.values() and target_language == 'en':
        model = indic2en_model
    elif source_language == 'en' and target_language in indic_language_dict.values():
        model = en2indic_model
    elif source_language in indic_language_dict.values() and target_language in indic_language_dict.values():
        model = m2m_model
    
    return model, source_language, target_language

@app.get("/")
async def homepage():
    # Redirect homepage to Swagger
    return RedirectResponse(url="/docs")

@app.get("/supported_languages")
async def supported_languages():
    return indic_language_dict

@app.get("/lemmatize_sentence")
@app.post("/lemmatize_sentence")
async def _lemmatize_sentence(
    sentence: str,
    lang: str = 'en'
):

    if lang != 'en':
        return "ERROR: Language not supported!"

    return lemmatize(sentence)


class SentenceTranslationRequest(BaseModel):
    text: str
    source_language: Optional[str] = 'en'
    target_language: str

@app.post("/translate_sentence")
async def translate_sentence(translation_request: SentenceTranslationRequest):
    model, source_lang, target_lang = get_inference_params(
        translation_request.source_language,
        translation_request.target_language
    )
    source_text = translation_request.text

    start_time = time.time()
    target_text = model.translate_paragraph(source_text, source_lang, target_lang)
    end_time = time.time()
    return {'text':target_text, 'duration':round(end_time-start_time, 2)} 


class BatchTranslationRequest(BaseModel):
    text_lines: list
    source_language: Optional[str] = 'en'
    target_language: str

@app.post("/batch_translate")
async def batch_translate(translation_request: BatchTranslationRequest):
    model, source_lang, target_lang = get_inference_params(
        translation_request.source_language,
        translation_request.target_language
    )
    text_lines = translation_request.text_lines

    start_time = time.time()
    target_lines = model.batch_translate(text_lines, source_lang, target_lang)
    end_time = time.time()
    return {'text_lines':target_lines, 'duration':round(end_time-start_time, 2)}

class VTTTranslationRequest(BaseModel):
    webvtt: str
    source_language: Optional[str] = 'en'
    target_language: str

@app.post("/translate_vtt")
def infer_vtt_indic_en(translation_request: VTTTranslationRequest):
    start_time = time.time()
    model, source_lang, target_lang = get_inference_params(
        translation_request.source_language,
        translation_request.target_language
    )
    source_text = translation_request.webvtt
    # vad_segments = request.form['vad_nochunk'] # Assuming it is an array of start & end timestamps

    vad = webvtt.read_buffer(StringIO(source_text))
    source_sentences = [v.text.replace('\r', '').replace('\n', ' ') for v in vad]

    ## SUMANTH LOGIC HERE ##

    # for each vad timestamp, do:
    large_sentence = ' '.join(source_sentences) # only sentences in that time range
    # Only for english
    # large_sentence = large_sentence.lower()
    # large_sentence = re.sub(r'[^\w\s]', '', large_sentence)
    # split_sents = sentence_split(large_sentence, 'en')
    # print(split_sents)

    print("Large sentence", large_sentence)
    punctuated = rpunct.punctuate(large_sentence, batch_size=32)
    end_time = time.time()
    print("Time Taken for punctuation: {} s".format(end_time - start_time))
    start_time = time.time()
    # split_sents = splitter([punctuated]) ### Please uncomment
    print("Punctuated", punctuated)
    split_sents = split_sentences(punctuated, source_lang)
    print("split_sents", split_sents)
    

    # print(split_sents)
    # output_sentence_punctuated = model.translate_paragraph(punctuated, source_lang, target_lang)
    output_sents = model.batch_translate(split_sents, source_lang, target_lang)
    print("output_sents", output_sents)
    # print(output_sents)
    # output_sents = split_sents
    # print(output_sents)
    # align this to those range of source_sentences in `captions`

    map_ = {split_sents[i] : output_sents[i] for i in range(len(split_sents))}
    # print(map_)
    punct_para = ' '.join(list(map_.keys()))
    nmt_para = ' '.join(list(map_.values()))
    nmt_words = nmt_para.split(' ')

    len_punct = len(punct_para.split(' '))
    len_nmt = len(nmt_para.split(' '))

    start = 0
    for i in range(len(vad)):
        if vad[i].text == '':
            continue

        len_caption = len(vad[i].text.split(' '))
        frac = (len_caption / len_punct)
        # frac = round(frac, 2)

        req_nmt_size = floor(frac * len_nmt)
        # print(frac, req_nmt_size)

        vad[i].text = ' '.join(nmt_words[start:start+req_nmt_size])
        # print(vad[i].text)
        # print(start, req_nmt_size)
        start += req_nmt_size

    end_time = time.time()
    
    print("Time Taken for translation: {} s".format(end_time - start_time))

    # vad.save('aligned.vtt')

    return {
        'text': vad.content,
        'duration': round(end_time-start_time, 2)
    }
