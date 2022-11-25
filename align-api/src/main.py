from configuration import ModelPath
from wav2vec2.utils import Wav2vec2
from rich.console import Console
from rich.traceback import install
from fastapi import FastAPI
from pydantic import BaseModel
import numpy as np
import torch
from utils import filter_text
from typing import Optional
import uvicorn

install()
console = Console()

app = FastAPI()

class AlignData(BaseModel):
    text: str = None
    wav_chunk: list[float] = None
    start_time: Optional[float] = 0.0
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

@app.post("/")
def align(align_data: AlignData) -> dict:
    if align_data.language not in language_codes:
        console.log(f"User is trying [red underline]{align_data.language} which is not loaded")
        return f"{align_data.language} is not loaded. Use another language."
    alignment = {}
    float_wav = np.array(align_data.wav_chunk)
    wav_tensor = torch.from_numpy(float_wav).float().view(1, -1)
    cleaned_text =  filter_text(align_data.text, align_data.language)
    word_segments = aligner_models[align_data.language].merge_words(
        wav_tensor, cleaned_text, begin=align_data.start_time
    )
    alignment["text"] = align_data.text
    alignment["timestamps"] = word_segments
    return alignment
