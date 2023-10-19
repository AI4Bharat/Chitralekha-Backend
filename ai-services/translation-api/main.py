from fastapi import FastAPI, HTTPException
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

# from punctuate import RestorePuncts
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
indic2en_model = Model(expdir="models/indic-en")
print("Loading En-Indic Model..")
en2indic_model = Model(expdir="models/en-indic")
print("Loading M2M Model..")
m2m_model = Model(expdir="models/m2m")

# rpunct = RestorePuncts('hi')
indic_language_dict = {
    "Assamese": "as",
    "English": "en",
    "Hindi": "hi",
    "Marathi": "mr",
    "Tamil": "ta",
    "Bengali": "bn",
    "Kannada": "kn",
    "Oriya": "or",
    "Telugu": "te",
    "Gujarati": "gu",
    "Malayalam": "ml",
    "Punjabi": "pa",
}
# splitter = MosesSentenceSplitter('en')


def get_inference_params(source_language, target_language):
    assert (
        source_language in indic_language_dict.values()
    ), f"Source language {source_language} not supported."
    assert (
        target_language in indic_language_dict.values()
    ), f"Target language {target_language} not supported."

    if source_language in indic_language_dict.values() and target_language == "en":
        model = indic2en_model
    elif source_language == "en" and target_language in indic_language_dict.values():
        model = en2indic_model
    elif (
        source_language in indic_language_dict.values()
        and target_language in indic_language_dict.values()
    ):
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
async def _lemmatize_sentence(sentence: str, lang: str = "en"):
    if lang != "en":
        return "ERROR: Language not supported!"

    return lemmatize(sentence)


class SentenceTranslationRequest(BaseModel):
    text: str
    source_language: Optional[str] = "en"
    target_language: str


@app.post("/translate_sentence")
async def translate_sentence(translation_request: SentenceTranslationRequest):
    try:
        model, source_lang, target_lang = get_inference_params(
            translation_request.source_language, translation_request.target_language
        )
    except AssertionError as e:
        raise HTTPException(status_code=500, detail=str(e))
    source_text = translation_request.text

    start_time = time.time()
    target_text = model.translate_paragraph(source_text, source_lang, target_lang)
    end_time = time.time()
    return {"text": target_text, "duration": round(end_time - start_time, 2)}


class BatchTranslationRequest(BaseModel):
    text_lines: list
    source_language: Optional[str] = "en"
    target_language: str


@app.post("/batch_translate")
async def batch_translate(translation_request: BatchTranslationRequest):
    try:
        model, source_lang, target_lang = get_inference_params(
            translation_request.source_language, translation_request.target_language
        )
    except AssertionError as e:
        raise HTTPException(status_code=500, detail=str(e))

    text_lines = translation_request.text_lines

    start_time = time.time()
    target_lines = model.batch_translate(text_lines, source_lang, target_lang)
    end_time = time.time()
    return {"text_lines": target_lines, "duration": round(end_time - start_time, 2)}


class VTTTranslationRequest(BaseModel):
    webvtt: str
    source_language: Optional[str] = "en"
    target_language: str


@app.post("/translate_vtt")
def infer_vtt_indic_en(translation_request: VTTTranslationRequest):
    start_time = time.time()
    source_language = "en"
    target_language = "hi"
    model, source_lang, target_lang = get_inference_params(
        source_language, target_language
    )
    source_text = translation_request.webvtt
    # vad_segments = request.form['vad_nochunk'] # Assuming it is an array of start & end timestamps

    vad = webvtt.read_buffer(StringIO(source_text))
    source_lines = [v.text.replace("\r", "").replace("\n", " ") for v in vad]
    start_time = time.time()
    target_lines = model.batch_translate(source_lines, source_lang, target_lang)
    end_time = time.time()
    for i in range(len(vad)):
        if vad[i].text == "":
            continue
        vad[i].text = target_lines[i]

    return {"text": vad.content, "duration": round(end_time - start_time, 2)}
