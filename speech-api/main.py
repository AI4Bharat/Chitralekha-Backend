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

from support import load_model,W2lKenLMDecoder,W2lViterbiDecoder,load_data
from vad import frame_generator, vad_collector

class Item(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    tax: Optional[float] = None

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    print("Model loaded.")

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.post("/items/")
async def create_item(item: Item):
    return item
