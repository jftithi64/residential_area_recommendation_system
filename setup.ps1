# One-time setup on Windows:  powershell -ExecutionPolicy Bypass -File setup.ps1
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install --only-binary :all: -r requirements.txt
.\.venv\Scripts\python.exe check_setup.py
