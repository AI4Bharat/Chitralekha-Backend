FROM python:3.8 as base

ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1

RUN apt-get update && apt-get install -y libsndfile1 libsndfile1-dev ffmpeg

WORKDIR /home/backend
COPY deploy/requirements.txt ./deploy/requirements.txt
RUN pip install --no-cache-dir -r deploy/requirements.txt 

COPY . .
RUN chmod -R 777 .

# RUN python3 manage.py makemigrations
RUN python3 manage.py migrate

CMD ["python3", "manage.py", "runserver", "0:8000", "--noreload", "--insecure"]