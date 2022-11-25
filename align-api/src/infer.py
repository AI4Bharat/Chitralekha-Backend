from pydub import AudioSegment
import numpy as np
import requests
import json
import argparse

parser = argparse.ArgumentParser(description="Align API")

parser.add_argument(
    '-w',
    '--wav',
    help="wav file path",
    type=str
)

parser.add_argument(
    '-t',
    '--text',
    help="text",
    type=str
)

parser.add_argument(
    '-l',
    '--lang',
    help="Language code",
    type=str
)

args = parser.parse_args()

audio = AudioSegment.from_file(args.wav)

samples = np.array(audio.get_array_of_samples()).astype("float64")

url = "http://0.0.0.0:8000"

payload = json.dumps({"text": args.text,
                      "wav_chunk": samples.tolist(),
                      "start_time": 0.0,
                      "language": args.lang})
headers = {"Content-Type": "application/json"}

response = requests.request("POST", url, headers=headers, data=payload)

print(response.text)
