FROM python:3.10

WORKDIR /usr/src/backend

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN pip install --upgrade pip
COPY ./deploy/requirements.txt /usr/src/backend/requirements.txt
RUN pip install --default-timeout=200 -r requirements.txt

# COPY ./entrypoint.sh /usr/src/backend/entrypoint.sh

COPY . /usr/src/backend/

# RUN ["chmod", "+x", "/usr/src/backend/entrypoint.sh"]

# ENTRYPOINT ["sh", "/usr/src/backend/entrypoint.sh"]