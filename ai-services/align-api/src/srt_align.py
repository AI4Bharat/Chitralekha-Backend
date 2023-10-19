from configuration import Data
from rich.console import Console
from rich.traceback import install
import numpy as np
from tqdm import tqdm
import numpy as np
from rich.console import Console
from rich.traceback import install
from infer import get_alignment
from utils import SubtitleTimestamps
from json2ytt import ytt_genorator

install()
console = Console()


def align_subtitle(subtitle_utils: SubtitleTimestamps) -> dict:
    subs = subtitle_utils.read_subtitles()

    aligned_srt = {}

    for sub in tqdm(subs, leave=False):
        alignment = {}

        if sub.content == "[Music]":
            alignment["text"] = sub.content
            alignment["timestamps"] = None
            aligned_srt[str(sub.index)] = alignment
            continue

        start, end = subtitle_utils.segment_start_end_times_seconds(sub)
        chunk = subtitle_utils.clip_audio(start, end)
        float_wav = np.array(chunk.get_array_of_samples()).astype("float64")
        cleaned_text = subtitle_utils.filter_text(sub.content)
        word_segments = get_alignment(
            wav=float_wav, text=cleaned_text, lang="en", mode="tensor"
        ).json()
        alignment["text"] = sub.content
        alignment["timestamps"] = word_segments["timestamps"]

        aligned_srt[str(sub.index)] = alignment

    return aligned_srt


if __name__ == "__main__":
    obj = SubtitleTimestamps(Data.srt_path, Data.wav_path, Data.language)
    aligned_srt = align_subtitle(obj)
    alignment = obj.adjust_alignment(aligned_srt)

    ytt_genorator(alignment, "alignment.ytt", mode="data")
