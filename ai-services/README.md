# Individual Server Components

## Setting up the Speech server locally

1. Clone the repository - `git clone --recursive https://github.com/AI4Bharat/chitralekha-backend.git`
2. Change directory - `cd pratilipi/speech/api`
4. Make sure you have torch > 1.7 installed
5. Install fairseq,kenlm,flashlight ```bash setup.sh```
6. Install dependencies by running ```pip install -r requirements.txt```
7. Download acoustic and language models - 
```
wget https://storage.googleapis.com/indicwav2vec-public/shared_to_vivek/evW2V_12K_64.pt
wget https://storage.googleapis.com/indicwav2vec-public/shared_to_vivek/lexicon.lst
wget https://storage.googleapis.com/indicwav2vec-public/shared_to_vivek/lm.binary
```
8. Change model path in test.json
9. Run the server using ```python flask_api.py <cpu/cuda:0>``` 
```uvicorn main:app --host 0.0.0.0 --port 5000```

## Setting up the Translation server locally

1. Clone the repository - `git clone --recursive https://github.com/AI4Bharat/pratilipi.git`
2. Install dependencies - ```bash download_and_setup_translation_models.sh```
3. Fire up the flask server locally - 
`FLASK_APP=api flask run -p 5050 -h 0.0.0.0`
`uvicorn main:app --host 0.0.0.0 --port 5050`
