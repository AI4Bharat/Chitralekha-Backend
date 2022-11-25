from pydub import AudioSegment
import numpy as np
import requests
import json

audio = AudioSegment.from_file('sample.wav')
chunk = audio[1000:2000]

samples = np.array(chunk.get_array_of_samples()).astype("float64")

url = "http://127.0.0.1:8000"

payload = json.dumps({"text": "क्या सेंट मैरीस की एयर क्वालिटी घातक है",
                      "wav_chunk": samples.tolist(),
                      "start_time": 0.0,
                      "language": "hi"})
headers = {"Content-Type": "application/json"}

response = requests.request("POST", url, headers=headers, data=payload)

print(response.text)
