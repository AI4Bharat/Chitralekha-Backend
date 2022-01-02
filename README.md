# Pratilipi
Transcribe your videos and translate it into Indic languages.

## Setting up the Frontend server locally

1. Clone the repository - `git clone --recursive https://github.com/AI4Bharat/pratilipi.git`
2. Make sure you are using a python version >= 3.5
3. Change the api http paths in the following lines in `index.html`. This step should be done once all the api servers are up and running.
```
Line numbers - 430, 443, 456, 491, 589
```
4. Fire up the HTTP server locally - `python -m http.server 8090 -b 0.0.0.0`

## Setting up the Feedback API server locally

1. Change to the feedback api directory - `cd feedback-api`
2. Install dependencies - `pip install -r requirements.txt`
3. Fire up the flask server locally - `FLASK_APP=api flask run -p 6070 -h 0.0.0.0`