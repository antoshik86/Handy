import os, queue, sys, threading, time, json, urllib.request, zipfile
import sounddevice as sd
import vosk
import keyboard

MODEL_DIR = os.path.expanduser("~/.vosk/vosk-model-small-ru-0.22")
MODEL_ZIP = os.path.expanduser("~/.vosk/vosk-model-small-ru-0.22.zip")
MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
SAMPLE_RATE = 16000
HOTKEY = 'ctrl+shift+v'

def download_model():
    os.makedirs(os.path.dirname(MODEL_DIR), exist_ok=True)
    print(f"Downloading Vosk Russian model (46MB)...")
    sys.stdout.flush()
    urllib.request.urlretrieve(MODEL_URL, MODEL_ZIP)
    print("Extracting...")
    with zipfile.ZipFile(MODEL_ZIP, 'r') as z:
        z.extractall(os.path.dirname(MODEL_DIR))
    os.remove(MODEL_ZIP)
    print("Model ready.")

if not os.path.exists(MODEL_DIR):
    download_model()

model = vosk.Model(MODEL_DIR)
recognizer = vosk.KaldiRecognizer(model, SAMPLE_RATE)

recording = False
audio_queue = queue.Queue()
recorded = []

def callback(indata, frames, time_info, status):
    if recording:
        audio_queue.put(indata.copy())

def worker():
    global recording, recorded
    while True:
        if recording:
            try:
                recorded.append(audio_queue.get(timeout=0.1))
            except queue.Empty:
                pass
        else:
            time.sleep(0.05)

def finish():
    global recorded
    if not recorded:
        return
    audio = b''.join([c.tobytes() for c in recorded])
    recorded = []
    if recognizer.AcceptWaveform(audio):
        text = json.loads(recognizer.Result()).get("text", "").strip()
    else:
        text = json.loads(recognizer.PartialResult()).get("partial", "").strip()
    if text:
        keyboard.write(text)

def toggle():
    global recording
    if not recording:
        recording = True
        print("[REC]")
    else:
        recording = False
        print("[TRN]")
        finish()
        print("[RDY]")

stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16', callback=callback)
threading.Thread(target=worker, daemon=True).start()
stream.start()

print("=== Voice Input (Vosk) ===")
print(f"Hotkey: {HOTKEY} — press to start/stop recording")
print("Ready.")
keyboard.add_hotkey(HOTKEY, toggle)
keyboard.wait()
