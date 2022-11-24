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

```
mkdir -p models/wav2vec2/
wget -P models/wav2vec2/ https://storage.googleapis.com/test_public_bucket/aligner_models.zip
cd models/wav2vec2 
unzip aligner_models.zip
```

# Usage 

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