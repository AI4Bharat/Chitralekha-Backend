FROM nvcr.io/nvidia/pytorch:21.06-py3

# Ensure apt-get won't prompt for selecting options
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y unzip

# WORKDIR /workspace/tranlation-api

# RUN git clone https://github.com/AI4Bharat/indicTrans.git && \
#     cd indicTrans && \
#     # clone requirements repositories
#     git clone https://github.com/anoopkunchukuttan/indic_nlp_library.git && \
#     git clone https://github.com/anoopkunchukuttan/indic_nlp_resources.git && \
#     git clone https://github.com/rsennrich/subword-nmt.git && \
#     cd ..

# Install the necessary libraries
RUN pip install sacremoses pandas mock sacrebleu tensorboardX pyarrow indic-nlp-library && \
    pip install mosestokenizer subword-nmt simpletransformers
# Install fairseq from source

WORKDIR /home
RUN git clone https://github.com/pytorch/fairseq.git && \
    cd fairseq && \
    pip install --editable ./

    # git checkout da9eaba12d82b9bfc1442f0e2c6fc1b895f4d35d && \

# WORKDIR /workspace/tranlation-api/models

# # make sure unzip is installed with `sudo apt-get install unzip` before running this
# RUN wget https://storage.googleapis.com/samanantar-public/V0.3/models/en-indic.zip && \
#     unzip en-indic.zip && \
#     cd ..

WORKDIR /workspace/translation-api
# RUN cp indicTrans/api/punctuate.py . && \
#     cp -r /workspace/translation-api/indicTrans/model_configs/ /workspace/translation-api

COPY ./requirements.txt /workspace/translation-api/requirements.txt
RUN pip install -r requirements.txt

COPY . /workspace/translation-api/