import re
import string
from indicnlp.normalize.indic_normalize import IndicNormalizerFactory
from pydub import AudioSegment
from rich.console import Console
from rich.traceback import install
import srt
import io
import re

install()
console = Console()


class SubtitleTimestamps:
    def __init__(self, srt_path, wav_path, language):
        self.srt_path = srt_path
        self.segments = self.read_subtitles()
        self.wav = AudioSegment.from_wav(wav_path)
        self.language = language
        self.factory = IndicNormalizerFactory()
        console.log(f"Subtitle path: [green]{srt_path}")
        console.log(f"Audio path: [green]{wav_path}")
        console.log(f"Language:  [green]{language}")

    def read_subtitles(self):

        with open(self.srt_path, "r", encoding="utf-8") as f:
            subtitles = f.read()

        subs = list(srt.parse(subtitles))
        return subs

    def segment_start_end_times_seconds(self, segment):
        return segment.start.total_seconds(), segment.end.total_seconds()

    def clip_audio(self, start, end):
        return self.wav[start * 1000 : end * 1000]

    def filter_text(self, text):

        cleaned_text = re.sub("[%s]" % re.escape(string.punctuation + "।"), "", text)

        if self.language == "en":
            words = cleaned_text.split()
            new_text = " "
            for word in words:
                new_text += word.lower() + " "
            new_text = new_text.strip()
            return new_text

        else:
            normalizer = self.factory.get_normalizer(self.language, remove_nuktas=False)
            return normalizer.normalize(cleaned_text)

    def adjust_alignment(self, data):

        if self.language == "en":
            for d, k in data.items():
                words = k["text"].split()

                for i in range(len(words)):

                    old_key = list(k["timestamps"][i].keys())[0]

                    if old_key != words[i]:
                        k["timestamps"][i][words[i]] = k["timestamps"][i][old_key]
                        del k["timestamps"][i][old_key]
            return data

        else:
            return data


def filter_text(text, language):

    factory = IndicNormalizerFactory()
    cleaned_text = re.sub("[%s]" % re.escape(string.punctuation + "।" + "-"), "", text)

    if language == "en":
        words = cleaned_text.split()
        new_text = " "
        for word in words:
            new_text += word.lower() + " "
        new_text = new_text.strip()
        return new_text

    else:
        normalizer = factory.get_normalizer(language, remove_nuktas=False)
        return normalizer.normalize(cleaned_text)


def wav_from_buffer(audio):
    buffer = io.BytesIO()
    audio.stream_to_buffer(buffer)
    buffer.seek(0)
    audio_data = buffer.read()
    wav = (
        AudioSegment.from_file(io.BytesIO(audio_data))
        .set_channels(1)
        .set_frame_rate(16000)
    )
    return wav


class SubtitleJson:
    def extract_time(start, end):
        def convert_hhmmssms_to_s(time):
            seconds = sum(
                float(x) * 60**i for i, x in enumerate(reversed(time.split(":")))
            )
            return seconds

        return convert_hhmmssms_to_s(start), convert_hhmmssms_to_s(end)

    def clip_audio(wav, start, end):
        return wav[start * 1000 : end * 1000]
    
    def adjust_alignment(data, language):

        if language == "en":
            for d, k in data.items():
                words = k["text"].split()
                for i in range(len(words)):
                    if k["timestamps"] != None:
                        old_key = list(k["timestamps"][i].keys())[0]

                        if old_key != words[i]:
                            k["timestamps"][i][words[i]] = k["timestamps"][i][old_key]
                            del k["timestamps"][i][old_key]
            return data

        else:
            return data
