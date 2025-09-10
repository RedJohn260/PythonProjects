@echo off
echo Installing PyTorch with CUDA 11.8 support...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

echo Installing other required packages...
pip install ultralytics opencv-python numpy simpleaudio

echo All done! Your environment is ready.
pause
