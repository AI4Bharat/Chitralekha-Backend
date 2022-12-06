from dataclasses import dataclass


@dataclass(order=True)
class ModelPath:
    wav2vec2_path: str = "models/wav2vec2/indic"
    language_codes = ["en"]  # add language codes which need to be loaded
    device = "cpu"  # cuda or cpu


@dataclass(order=True)
class Data:
    wav_path: str = "data/english.wav"
    srt_path: str = "data/english.srt"
    language: str = "en"
