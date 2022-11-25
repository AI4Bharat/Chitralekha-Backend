from dataclasses import dataclass


@dataclass(order=True)
class ModelPath:
    wav2vec2_path: str = "models/wav2vec2/indic"
    language_codes = ["hi"]
    device = 'cuda' # cuda or cpu


@dataclass(order=True)
class Data:
    wav_path: str = "audio/english.wav"
    txt_path: str = "../examples/sample.txt"
    srt_path: str = "srt/English_corrected.srt"
    language: str = "hi"