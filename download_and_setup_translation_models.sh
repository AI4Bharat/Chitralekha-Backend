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


mkdir indicTrans-web
cd indicTrans-web
mkdir api
cd api
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
pip3 install sacremoses pandas mock sacrebleu tensorboardX pyarrow indic-nlp-library
pip3 install mosestokenizer subword-nmt
# Install fairseq from source
git clone https://github.com/pytorch/fairseq.git
cd fairseq
# uncomment the following line if you want to use a reliable old version of fairseq in case something breaks with latest version
git checkout da9eaba12d82b9bfc1442f0e2c6fc1b895f4d35d
echo "Installing fairseq"
pip3 install --editable ./
cd ..

mv indicTrans/api/api.py .
mv indicTrans/api/punctuate.py .
mv indicTrans/model_configs .
mv indicTrans/interface ..

mkdir models

cd  models
echo "Downloading IndicTrans en-Indic Multilingual Model"
wget https://storage.googleapis.com/samanantar-public/V0.3/models/en-indic.zip
# make sure unzip is installed with `sudo apt-get install unzip` before running this
unzip en-indic.zip
rm en-indic.zip
cd ..

echo "Done"
