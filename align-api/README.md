# Installation instructions

```
conda create -n alignment python=3.10
conda activate alignment
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
Oriya - or
Punjabi - pa
Sanskrit - sa
Tamil - ta
Telugu - te
Urdu - ur
```
In `wav2vec2_path`, `language_codes` and `device` in  `configuration.py`.

Run the server: 
```
uvicorn main:app --host=0.0.0.0 --port=8000   

python infer.py -w sample.wav -t "क्या सेंट मैरीस की एयर क्वालिटी घातक है" -l hi
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