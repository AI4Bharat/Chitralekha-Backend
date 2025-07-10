# Installation instructions

```
conda create -n alignment python=3.10
conda activate alignment
python -m pip install --upgrade pytube
pip install torch torchvision torchaudio
git clone https://github.com/agupta54/fairseq-align.git
cd fairseq-align
pip install -e .
cd ..
git clone https://github.com/AI4Bharat/Chitralekha-Backend.git
cd Chitralekha-Backend/align-api
pip install -r requirements.txt
```

# Download models 
All the models are bundled in a zip file which is around $35$ Gb in size. Uncompressed size is $44$ Gb.
```
mkdir -p models/wav2vec2/
wget -P models/wav2vec2/ https://storage.googleapis.com/test_public_bucket/aligner_models.zip
cd models/wav2vec2 
unzip aligner_models.zip
```

# Usage 
Currently. the following langauges are supported. Please use the language codes to load models.

```
English - en
Hindi - hi
Bengali - bn
Gujarati - gu
Kannada - kn
Malayalam - ml
Marathi - mr
Odia - or
Punjabi - pa
Sanskrit - sa
Tamil - ta
Telugu - te
Urdu - ur
```
Make changes in  `wav2vec2_path`, `language_codes` and `device` arguments in  `configuration.py` according to your needs.

Start the server: 
```
uvicorn main:app --host=0.0.0.0 --port=8000

python infer.py -w data/sample.wav -t "क्या सेंट मैरीस की एयर क्वालिटी घातक है" -l hi
```
```{json}
{
  "text": "क्या सेंट मैरीस की एयर क्वालिटी घातक है",
  "timestamps": [
    {
      "क्या": {
        "start": "00:00:01.04",
        "end": "00:00:01.26",
        "score": 0.49771117469803855
      }
    },
    {
      "सेंट": {
        "start": "00:00:01.30",
        "end": "00:00:01.64",
        "score": 0.6091309013666913
      }
    },
    {
      "मैरीस": {
        "start": "00:00:01.68",
        "end": "00:00:02.18",
        "score": 0.6003621731046587
      }
    },
    {
      "की": {
        "start": "00:00:02.28",
        "end": "00:00:02.36",
        "score": 0.4160352870821953
      }
    },
    {
      "एयर": {
        "start": "00:00:02.38",
        "end": "00:00:02.55",
        "score": 0.4701317776343785
      }
    },
    {
      "क्वालिटी": {
        "start": "00:00:02.59",
        "end": "00:00:03.03",
        "score": 0.4657399899918925
      }
    },
    {
      "घातक": {
        "start": "00:00:03.07",
        "end": "00:00:03.35",
        "score": 0.5823210459867758
      }
    },
    {
      "है": {
        "start": "00:00:03.39",
        "end": "00:00:03.47",
        "score": 0.3947810977988411
      }
    }
  ]
}
```
API documentation can be accessed at http://0.0.0.0:8000/redoc once the server has successfully started.

## Align subtitle files

Modify `wav_path`, `srt_path` and `language` in `configuration.py`. Make sure you have loaded the appropriate model while starting the server. `srt_align.py` directly generates the corresponding `.ytt` file for the given subtitles. 

```{bash}
python srt_align.py
```
## Align with json files
This format can be found in files `data/tic_tac_learn.json` and `data/khan_academy.json` and is specific to Chitralekha backend.
The `align_json` endpoint excepts the following fields in the payload. 

```
class ExtendedAudioAlign(BaseModel):
    srt: dict = None # subtitles in json format
    url: str = None # youtube url 
    language: str = None # language code
```

```{bash}
uvicorn main:app --host=0.0.0.0 --port=8000

curl --location --request POST 'http://0.0.0.0:8000/align_json' \
--header 'Content-Type: application/json' \
--data-raw '{
    "srt": {"payload":[{"start_time":"00:00:00.111","end_time":"00:00:02.793","text":"- [Instructor] You are likely\nalready familiar with the idea"}]},
    "url": "https://www.youtube.com/watch?v=N2PpRnFqnqY",
    "language": "en"
}'

```
This should give a response for alignment of a single chunk. 
To align the whole youtube audio with subtitles the python client can be used. 

```
python align_json.py https://www.youtube.com/watch\?v\=4DwfmwZe_jo data/tic_tac_learn.json en
python align_json.py https://www.youtube.com/watch\?v\=N2PpRnFqnqY data/khan_academy.json en
```
If everything was up and running you should have received the response with word level alignment. 

