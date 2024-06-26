from pydub import AudioSegment
import numpy as np
import requests
import json
import argparse


def get_alignment(wav, text, lang, mode="wav"):
    if mode == "wav":
        audio = AudioSegment.from_file(wav)
        samples = np.array(audio.get_array_of_samples()).astype("float64")
    else:
        samples = wav

    url = "http://0.0.0.0:8000/align_audio"

    payload = json.dumps(
        {
            "text": text,
            "wav_chunk": samples.tolist(),
            "start_time": 0.0,
            "language": lang,
        }
    )
    headers = {"Content-Type": "application/json"}

    response = requests.request("POST", url, headers=headers, data=payload)
    return response


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Align API")

    parser.add_argument("-w", "--wav", help="wav file path", type=str)

    parser.add_argument("-t", "--text", help="text", type=str)

    parser.add_argument("-l", "--lang", help="Language code", type=str)

    parser.add_argument(
        "-m",
        "--mode",
        help="load from file path or as numpy array",
        default="wav",
        type=str,
    )

    args = parser.parse_args()
    response = get_alignment(args.wav, args.text, args.lang, args.mode)
    print(response.json())
