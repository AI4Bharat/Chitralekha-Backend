from fastapi import FastAPI
from typing import Optional
from pydantic import BaseModel

import time

import re
from math import floor
import webvtt
from io import StringIO
from mosestokenizer import MosesSentenceSplitter

from indicTrans.inference.engine import Model
from punctuate import RestorePuncts
app = FastAPI()

# indic2en_model = Model(expdir='models/v3/indic-en')
en2indic_model = Model(expdir='/workspace/translation-api/models/en-indic')
# m2m_model = Model(expdir='models/m2m')

rpunct = RestorePuncts()
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
splitter = MosesSentenceSplitter('en')

def get_inference_params(source_language, target_language):

    if source_language in indic_language_dict and target_language == 'English':
        model = indic2en_model
        source_lang = indic_language_dict[source_language]
        target_lang = 'en'
    elif source_language == 'English' and target_language in indic_language_dict:
        model = en2indic_model
        source_lang = 'en'
        target_lang = indic_language_dict[target_language]
    elif source_language in indic_language_dict and target_language in indic_language_dict:
        model = m2m_model
        source_lang = indic_language_dict[source_language]
        target_lang = indic_language_dict[target_language]
    
    return model, source_lang, target_lang

@app.get("/")
async def root():
    return {"message": "Welcom to IndicTrans API. For usage instructions, visit /docs."}

@app.get("/supported_languages/")
async def supported_languages():
    return indic_language_dict

class SentenceTranslationRequest(BaseModel):
    text: str
    source_language: Optional[str] = 'English'
    target_language: str

@app.post("/translate_sentence/")
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
    source_language: Optional[str] = 'English'
    target_language: str

@app.post("/batch_translate/")
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
    source_language: Optional[str] = 'English'
    target_language: str

@app.post("/batch_translate/")
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
    large_sentence = large_sentence.lower()
    # split_sents = sentence_split(large_sentence, 'en')
    # print(split_sents)

    large_sentence = re.sub(r'[^\w\s]', '', large_sentence)
    punctuated = rpunct.punctuate(large_sentence, batch_size=32)
    end_time = time.time()
    print("Time Taken for punctuation: {} s".format(end_time - start_time))
    start_time = time.time()
    split_sents = splitter([punctuated]) ### Please uncomment


    # print(split_sents)
    # output_sentence_punctuated = model.translate_paragraph(punctuated, source_lang, target_lang)
    output_sents = model.batch_translate(split_sents, source_lang, target_lang)
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
