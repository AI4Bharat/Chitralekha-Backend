sudo apt-get install liblzma-dev libbz2-dev libzstd-dev libsndfile1-dev libopenblas-dev libfftw3-dev libgflags-dev libgoogle-glog-dev
sudo apt install build-essential cmake libboost-system-dev libboost-thread-dev libboost-program-options-dev libboost-test-dev libeigen3-dev zlib1g-dev libbz2-dev liblzma-dev

pip install packaging soundfile swifter


# Install Fairseq
git clone https://github.com/pytorch/fairseq.git
cd fairseq
pip install -e .
cd ..

# Install KenLM
git clone https://github.com/kpu/kenlm.git
cd kenlm
mkdir -p build && cd build
cmake .. 
make -j 16
cd ..
export KENLM_ROOT=$PWD
# for CPU uncomment the following line
export USE_CUDA=0
cd ..

#Install flashlight
git clone https://github.com/flashlight/flashlight.git
cd flashlight/bindings/python
export USE_MKL=0
python setup.py install
