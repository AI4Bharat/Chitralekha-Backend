# Chitralekha Backend
Transcribe your videos and translate it into Indic languages.

This repository contains the [Chitralekha](https://github.com/AI4Bharat/Chitralekha) Backend codebase. The backend is built using Django Rest Framework.

You can watch a demo of our tool - [Video](https://youtu.be/l9jUcja0E94)

## Pre-requisites

- Recommended [Python: 3.7+](https://www.python.org/downloads/).
- `cd backend`
- Installing dependencies: `pip install deploy/requirements.txt`

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
cd ..
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
