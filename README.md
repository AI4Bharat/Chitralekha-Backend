# Pratilipi
Transcribe your videos and translate it into Indic languages.

## Setting up the Speech server locally

1. Clone the repository - `git clone --recursive https://github.com/AI4Bharat/pratilipi.git`
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

## Setting up the Translation server locally

1. Clone the repository - `git clone --recursive https://github.com/AI4Bharat/pratilipi.git`
2. Install dependencies - ```bash download_and_setup_translation_models.sh```
3. Fire up the flask server locally - 
`FLASK_APP=api flask run -p 5050 -h 0.0.0.0`

## Setting up the Feedback API server locally

1. Change to the feedback api directory - `cd feedback-api`
2. Install dependencies - `pip install -r requirements.txt`
3. Fire up the flask server locally - `FLASK_APP=api flask run -p 6070 -h 0.0.0.0`

## Setting up the Frontend server locally

1. Clone the repository - `git clone --recursive https://github.com/AI4Bharat/pratilipi.git`
2. Make sure you are using a python version >= 3.5
3. Change the api http paths in the following lines in `index.html`. This step should be done once all the api servers are up and running.
```
Line numbers - 408, 409, 410
```
4. Fire up the HTTP server locally - `python -m http.server 8090 -b 0.0.0.0`

