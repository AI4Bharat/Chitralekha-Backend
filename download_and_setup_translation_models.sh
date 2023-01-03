# After running this code, you ll have a folder structure that looks like this
# indicTrans-web (Contains all the web code for indictrans translation models)
# ├── api
# │   ├── api.py (Contains the code for the flask server)
# │   ├── fairseq (Latest fairseq cloned here)
# │   ├── indicTrans (Contains the indicTrans code cloned from repo)
# │   ├── model_configs (Contains custom model configration for indictrans)
# │   ├── models (the indictrans multilingual models are download and placed here)
# │   └── punctuate.py (Contains the code for punctuation model)
# ├── interface (Contains the interface html files and logo for the website)
#    ├── index.html
#    └── logo.png

sudo apt install -y liblzma-dev libbz2-dev libzstd-dev libsndfile1-dev libopenblas-dev libfftw3-dev libgflags-dev libgoogle-glog-dev
sudo apt install -y build-essential cmake libboost-system-dev libboost-thread-dev libboost-program-options-dev libboost-test-dev libeigen3-dev zlib1g-dev libbz2-dev liblzma-dev
sudo apt install -y git wget unzip

cd translation-api
echo "Cloning IndicTrans  Repo"
git clone https://github.com/AI4Bharat/indicTrans.git

echo "cloning dependencies of indicTrans"
cd indicTrans
# clone requirements repositories
git clone https://github.com/anoopkunchukuttan/indic_nlp_library.git
git clone https://github.com/anoopkunchukuttan/indic_nlp_resources.git
git clone https://github.com/rsennrich/subword-nmt.git
cd ..

echo "Installing required libraries and cloning Fairseq"
# Install the necessary libraries
pip install sacremoses pandas mock sacrebleu tensorboardX pyarrow indic-nlp-library
pip install mosestokenizer subword-nmt simpletransformers
# Install fairseq from source
git clone https://github.com/pytorch/fairseq.git
cd fairseq
# uncomment the following line if you want to use a reliable old version of fairseq in case something breaks with latest version
git checkout cf8ff8c3c5242e6e71e8feb40de45dd699f3cc08
echo "Installing fairseq"
pip install --editable ./
cd ..

mkdir models

cd  models
echo "Downloading IndicTrans en-Indic Multilingual Model"
wget https://storage.googleapis.com/samanantar-public/V0.3/models/en-indic.zip
wget https://storage.googleapis.com/samanantar-public/V0.3/models/indic-en.zip
wget https://storage.googleapis.com/samanantar-public/V0.3/models/m2m.zip
# make sure unzip is installed with `sudo apt-get install unzip` before running this
unzip en-indic.zip
rm en-indic.zip
unzip indic-en.zip
rm indic-en.zip
unzip m2m.zip
rm m2m.zip
cd ..

pip install -r requirements.txt

echo "Done"
