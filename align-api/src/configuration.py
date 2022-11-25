from dataclasses import dataclass


@dataclass(order=True)
class ModelPath:
    wav2vec2_path: str = "models/wav2vec2/indic"
    language_codes = ["hi"] # add language codes which need to be loaded
    device = 'cuda' # cuda or cpu


@dataclass(order=True)
class Data:
    wav_path: str = "audio/english.wav"
    srt_path: str = "srt/English_corrected.srt"
    language: str = "hi"