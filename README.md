# Chitralekha Backend
Transcribe your videos and translate it into Indic languages.

This repository contains the [Chitralekha](https://github.com/AI4Bharat/Chitralekha) Backend codebase. The backend is built using Django and Django Rest Framework.

You can watch a demo of our tool - [Video](https://youtu.be/l9jUcja0E94)

## Pre-requisites

The project was created using [Python 3.7](https://www.python.org/downloads/). All major dependencies are listed below; the rest are in the `backend/deploy/requirements.txt` file.

- django
- djangorestframework
- django-cors-headers
- knox
- drf-yasg
- psycopg2
- python-dotenv
- webvtt-py

<!-- ## Installation

The installation and setup instructions have been tested on the following platforms:

- Docker
- Docker-Compose
- Ubuntu 20.04

If you are using a different operating system, you will have to look at external resources (eg. StackOverflow) to correct any errors. -->

### Create a Virtual Environment

We recommend you to create a virtual environment to install all the dependencies required for the project.

```bash
python3 -m venv <YOUR-ENVIRONMENT-NAME>
source <YOUR-ENVIRONMENT-NAME>/bin/activate # this command may be different based on your OS

# Install dependencies
pip install -r deploy/requirements-dev.txt
```

### Environment file

To set up the environment variables needed for the project, run the following lines:
```bash
cp .env.example ./backend/.env
```

This creates an `.env` file at the root of the project. It is needed to make sure that the project runs correctly. Please go through the file and set the parameters according to your installation.

To create a new secret key, run the following commands (within the virtual environment):

```bash
# Open a Python shell
python backend/manage.py shell

>> from django.core.management.utils import get_random_secret_key
>> get_random_secret_key()
```

Paste the value you get there into the `.env` file.

## Run the project

To run the project, run the following commands:

```bash
# Check if there are makemigrations 
python backend/manage.py makemigrations

# Run migrations
python backend/manage.py migrate

# Create superuser
python backend/manage.py createsuperuser

# 1. Need to install REDIS and run in one terminal parallely
# 2. Start Flower
   python -m celery -A backend flower   
# 3. 1st CELERY worker needs to start with below cmnd
   python -m celery -A backend worker -Q default --concurrency=1 -l DEBUG
# 4. 2nd CELERY worker needs to start with below cmnd
   python -m celery -A backend worker -Q voiceover --concurrency=1 -l DEBUG
# 5. Run the server
   python manage.py runserver

```
The project will start running on `http://localhost:8000/`.

### Running Linters and Formatters

Installing the dev requirements file would have also installed linters. We have `black` available for formatting. You can run the following commands to check for linting errors and format the code:


```bash
black ./backend/
```

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

