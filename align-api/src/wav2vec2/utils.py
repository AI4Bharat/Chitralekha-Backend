from glob import glob
from torchaudio.models.wav2vec2.utils import import_fairseq_model
import fairseq
import torch
import torchaudio
from dataclasses import dataclass
from rich.console import Console
from rich.traceback import install

install()
console = Console()


@dataclass
class Point:
    token_index: int
    time_index: int
    score: float


@dataclass
class Segment:
    label: str
    start: float
    end: float
    score: float

    def __repr__(self):
        return f"{self.label}\t({self.score:4.2f}): [{self.start:5d}, {self.end:5d})"

    @property
    def length(self):
        return self.end - self.start


class Wav2vec2:
    def __init__(self, model_path, language_code, mode, device):
        self.asr_path = glob(model_path + "/" + language_code + "/*.pt")[0]
        self.dict_path = glob(model_path + "/" + language_code + "/*.txt")[0]
        self.device = device
        self.encoder = self.load_model_encoder()
        self.labels = self.get_labels()
        self.mode = mode

    def load_model_encoder(self):
        model, _, _ = fairseq.checkpoint_utils.load_model_ensemble_and_task(
            [self.asr_path]
        )
        console.log(f"Model loaded on [green underline]{self.device}")       
        model = model[0].to(self.device)
        encoder = import_fairseq_model(model.w2v_encoder)
        console.log(
            f":thumbs_up: Wav2vec2 model loaded successfully from [green underline]{self.asr_path}"
        )
        return encoder

    def get_emissions(self, wav):
        if self.mode == "file":
            with torch.inference_mode():
                waveform, _ = torchaudio.load(wav)
                emissions, _ = self.encoder(waveform)
                emissions = torch.log_softmax(emissions, dim=-1)
            emissions = emissions[0].cpu().detach()
        else:
            with torch.inference_mode():
                waveform = wav
                emissions, _ = self.encoder(waveform)
                emissions = torch.log_softmax(emissions, dim=-1)
            emissions = emissions[0].cpu().detach()
        return emissions, waveform[0].size(0)

    def get_transcript(self, txt_path):
        if self.mode == "file":
            with open(txt_path, encoding="utf-8") as f:
                txt = f.read().strip()
            words = txt.split()
            transcript = words[0]
            for word in words[1:]:
                transcript += "|" + word
        else:
            txt = txt_path
            words = txt.split()
            transcript = words[0]
            for word in words[1:]:
                transcript += "|" + word
        return transcript

    def get_labels(self):
        with open(self.dict_path, encoding="utf-8") as f:
            chars = f.read().splitlines()
        chars = [i.split()[0] for i in chars]
        labels = ["<s>", "<pad>", "</s>", "<unk>"] + chars
        labels = tuple(labels)
        return tuple(labels)

    def get_transcript_tokens(self, txt_path):
        dictionary = {c: i for i, c in enumerate(self.labels)}
        tokens = [dictionary[c] for c in self.get_transcript(txt_path)]
        return tokens

    def get_trellis(self, wav_path, txt_path, blank_id=0):
        emission, wav_size = self.get_emissions(wav_path)
        tokens = self.get_transcript_tokens(txt_path)
        num_frame = emission.size(0)
        num_tokens = len(tokens)

        # Trellis has extra diemsions for both time axis and tokens.
        # The extra dim for tokens represents <SoS> (start-of-sentence)
        # The extra dim for time axis is for simplification of the code.
        trellis = torch.empty((num_frame + 1, num_tokens + 1))
        trellis[0, 0] = 0
        trellis[1:, 0] = torch.cumsum(emission[:, 0], 0)
        trellis[0, -num_tokens:] = -float("inf")
        trellis[-num_tokens:, 0] = float("inf")

        for t in range(num_frame):
            trellis[t + 1, 1:] = torch.maximum(
                # Score for staying at the same token
                trellis[t, 1:] + emission[t, blank_id],
                # Score for changing to the next token
                trellis[t, :-1] + emission[t, tokens],
            )
        ratio = wav_size / (trellis.size(0) - 1)
        return emission, tokens, trellis, ratio

    def backtrack(self, wav_path, txt_path, blank_id=0):
        # Note:
        # j and t are indices for trellis, which has extra dimensions
        # for time and tokens at the beginning.
        # When referring to time frame index `T` in trellis,
        # the corresponding index in emission is `T-1`.
        # Similarly, when referring to token index `J` in trellis,
        # the corresponding index in transcript is `J-1`.
        emission, tokens, trellis, ratio = self.get_trellis(
            wav_path=wav_path, txt_path=txt_path
        )
        j = trellis.size(1) - 1
        t_start = torch.argmax(trellis[:, j]).item()

        path = []
        for t in range(t_start, 0, -1):
            # 1. Figure out if the current position was stay or change
            # Note (again):
            # `emission[J-1]` is the emission at time frame `J` of trellis dimension.
            # Score for token staying the same from time frame J-1 to T.
            stayed = trellis[t - 1, j] + emission[t - 1, blank_id]
            # Score for token changing from C-1 at T-1 to J at T.
            changed = trellis[t - 1, j - 1] + emission[t - 1, tokens[j - 1]]

            # 2. Store the path with frame-wise probability.
            prob = (
                emission[t - 1, tokens[j - 1] if changed > stayed else 0].exp().item()
            )
            # Return token index and time index in non-trellis coordinate.
            path.append(Point(j - 1, t - 1, prob))

            # 3. Update the token
            if changed > stayed:
                j -= 1
                if j == 0:
                    break
        else:
            raise ValueError("Failed to align")
        return path[::-1], ratio

    def merge_repeats(self, wav_path, txt_path):
        path, ratio = self.backtrack(wav_path=wav_path, txt_path=txt_path)
        transcript = self.get_transcript(txt_path=txt_path)
        i1, i2 = 0, 0
        segments = []
        while i1 < len(path):
            while i2 < len(path) and path[i1].token_index == path[i2].token_index:
                i2 += 1
            score = sum(path[k].score for k in range(i1, i2)) / (i2 - i1)
            segments.append(
                Segment(
                    transcript[path[i1].token_index],
                    path[i1].time_index,
                    path[i2 - 1].time_index + 1,
                    score,
                )
            )
            i1 = i2
        return segments, ratio

    def formatSrtTime(self, secTime):
        sec, micro = str(secTime).split(".")
        m, s = divmod(int(sec), 60)
        h, m = divmod(m, 60)
        return "{:02}:{:02}:{:02}.{}".format(h, m, s, micro[:2])

    def merge_words(self, wav_path, txt_path, separator="|", begin=0):
        segments, ratio = self.merge_repeats(wav_path=wav_path, txt_path=txt_path)
        words = []
        d = {}
        word_stamps = []
        i1, i2 = 0, 0
        while i1 < len(segments):
            if i2 >= len(segments) or segments[i2].label == separator:
                if i1 != i2:
                    segs = segments[i1:i2]
                    word = "".join([seg.label for seg in segs])
                    score = sum(seg.score * seg.length for seg in segs) / sum(
                        seg.length for seg in segs
                    )
                    words.append(
                        Segment(word, segments[i1].start, segments[i2 - 1].end, score)
                    )
                    d[word] = {
                        "start": self.formatSrtTime(
                            begin + segments[i1].start * (ratio / 16000)
                        ),
                        "end": self.formatSrtTime(
                            begin + segments[i2 - 1].end * (ratio / 16000)
                        ),
                        "score": score,
                    }
                    word_stamps.append(d)
                i1 = i2 + 1
                i2 = i1
            else:
                d = {}
                i2 += 1
        return word_stamps


if __name__ == "__main__":
    pass
