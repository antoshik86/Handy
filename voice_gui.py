import os, queue, sys, threading, time, json, urllib.request, zipfile, signal, tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import sounddevice as sd
import keyboard

os.environ["VOSK_LOG_LEVEL"] = "-1"
import vosk

MODEL_DIR = os.path.expanduser("~/.vosk/vosk-model-small-ru-0.22")
MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
SAMPLE_RATE = 16000
HOTKEY = "right ctrl"


class VoiceApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Voice Input (Vosk)")
        self.root.geometry("520x520")
        self.root.resizable(True, True)
        self.root.configure(bg="#1e1e2e")

        self.recording = False
        self.running = True
        self.audio_queue = queue.Queue()
        self.recorded = []
        self.model = None
        self.recognizer = None
        self.stream = None
        self.status = "INIT"
        self.last_text = ""

        self._build_ui()
        self._init_vosk()
        self._start_stream()
        self._update_meter()

    # ── UI ──────────────────────────────────────────────────────

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#1e1e2e")
        style.configure("TLabel", background="#1e1e2e", foreground="#cdd6f4", font=("Segoe UI", 10))
        style.configure("Status.TLabel", font=("Segoe UI", 28, "bold"))
        style.configure("Big.TButton", font=("Segoe UI", 12, "bold"), padding=12)

        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        # status indicator
        self.status_label = ttk.Label(frame, text="●", font=("Segoe UI", 48))
        self.status_label.pack(pady=(0, 4))
        self.status_label.configure(foreground="#585b70")

        self.status_text = ttk.Label(frame, text="Загрузка модели…", style="Status.TLabel")
        self.status_text.pack(pady=(0, 8))

        # audio level
        level_frame = ttk.Frame(frame)
        level_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(level_frame, text="Уровень:").pack(side=tk.LEFT)
        self.level_bar = tk.Canvas(level_frame, height=18, bg="#313244", highlightthickness=0)
        self.level_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

        # button
        self.btn = ttk.Button(frame, text="🎙  Удерживай Правый Ctrl", style="Big.TButton")
        self.btn.pack(fill=tk.X, pady=(0, 8))
        self.btn.bind("<ButtonPress-1>", lambda e: self._start_recording())
        self.btn.bind("<ButtonRelease-1>", lambda e: self._stop_recording())

        # text output
        ttk.Label(frame, text="Распознанный текст:").pack(anchor=tk.W)
        self.text_box = scrolledtext.ScrolledText(frame, height=8, font=("Consolas", 11),
                                                  bg="#313244", fg="#cdd6f4",
                                                  insertbackground="#cdd6f4",
                                                  relief=tk.FLAT, wrap=tk.WORD)
        self.text_box.pack(fill=tk.BOTH, expand=True, pady=(4, 8))

        # log
        ttk.Label(frame, text="Лог:").pack(anchor=tk.W)
        self.log_box = scrolledtext.ScrolledText(frame, height=5, font=("Consolas", 9),
                                                 bg="#181825", fg="#6c7086",
                                                 relief=tk.FLAT, wrap=tk.WORD)
        self.log_box.pack(fill=tk.BOTH, expand=True)

        # keyboard hooks
        keyboard.hook(self._on_key)

    # ── VOSK ────────────────────────────────────────────────────

    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.log_box.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_box.see(tk.END)

    def _set_status(self, state, text):
        colors = {"REC": "#f38ba8", "READY": "#a6e3a1", "BUSY": "#f9e2af", "INIT": "#585b70", "ERR": "#f38ba8"}
        self.status = state
        self.status_label.configure(foreground=colors.get(state, "#585b70"))
        self.status_text.configure(text=text)

    def _init_vosk(self):
        def _load():
            if not os.path.exists(MODEL_DIR):
                self._set_status("BUSY", "Скачивание модели…")
                self._log("Скачиваю модель Vosk…")
                try:
                    os.makedirs(os.path.dirname(MODEL_DIR), exist_ok=True)
                    urllib.request.urlretrieve(MODEL_URL, MODEL_DIR + ".zip")
                    with zipfile.ZipFile(MODEL_DIR + ".zip", "r") as z:
                        z.extractall(os.path.dirname(MODEL_DIR))
                    os.remove(MODEL_DIR + ".zip")
                    self._log("Модель скачана и распакована.")
                except Exception as e:
                    self._set_status("ERR", f"Ошибка скачивания: {e}")
                    self._log(f"Ошибка: {e}")
                    return

            self._log("Загружаю модель…")
            try:
                self.model = vosk.Model(MODEL_DIR)
                self.recognizer = vosk.KaldiRecognizer(self.model, SAMPLE_RATE)
                self._set_status("READY", "Готово")
                self._log("Модель загружена. Нажми кнопку или Правый Ctrl.")
            except Exception as e:
                self._set_status("ERR", f"Ошибка модели: {e}")
                self._log(f"Ошибка модели: {e}")

        threading.Thread(target=_load, daemon=True).start()

    # ── AUDIO ───────────────────────────────────────────────────

    def _audio_callback(self, indata, frames, time_info, status):
        if self.recording:
            self.audio_queue.put(indata.copy())

    def _start_stream(self):
        try:
            self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                                         callback=self._audio_callback)
            self.stream.start()
        except Exception as e:
            self._set_status("ERR", f"Нет микрофона: {e}")
            self._log(f"Ошибка микрофона: {e}")

    def _update_meter(self):
        if self.recording:
            try:
                chunk = self.audio_queue.get_nowait()
                level = max(abs(int(s)) for s in chunk) / 32768.0
            except queue.Empty:
                level = 0
        else:
            level = 0

        self.level_bar.delete("all")
        w = self.level_bar.winfo_width()
        bar_w = int(w * min(level * 3, 1.0))
        color = "#f38ba8" if level > 0.7 else "#a6e3a1" if level > 0.01 else "#313244"
        self.level_bar.create_rectangle(0, 0, bar_w, 18, fill=color, outline="")

        self.root.after(80, self._update_meter)

    def _start_recording(self):
        if self.recording or self.recognizer is None:
            return
        self.recording = True
        self.recorded = []
        self._set_status("REC", "Запись…")
        self._log("Запись начата.")

    def _stop_recording(self):
        if not self.recording:
            return
        self.recording = False
        self._set_status("BUSY", "Распознавание…")
        self._log("Распознаю…")

        def _transcribe():
            try:
                chunks = []
                while not self.audio_queue.empty():
                    chunks.append(self.audio_queue.get_nowait())
                audio = b"".join(c.tobytes() for c in chunks)
                if not audio:
                    self.root.after(0, lambda: self._set_status("READY", "Готово"))
                    self.root.after(0, lambda: self._log("Тишина."))
                    return

                if self.recognizer.AcceptWaveform(audio):
                    text = json.loads(self.recognizer.Result()).get("text", "").strip()
                else:
                    text = json.loads(self.recognizer.PartialResult()).get("partial", "").strip()

                if text:
                    keyboard.write(text)
                    self.last_text += text + " "
                    self.root.after(0, lambda t=text: self._show_text(t))
                    self.root.after(0, lambda: self._log(f"→ {text}"))
                else:
                    self.root.after(0, lambda: self._log("Тишина или не распознано."))
            except Exception as e:
                self.root.after(0, lambda: self._log(f"Ошибка: {e}"))
            finally:
                self.root.after(0, lambda: self._set_status("READY", "Готово"))

        threading.Thread(target=_transcribe, daemon=True).start()

    def _show_text(self, text):
        self.text_box.insert(tk.END, text + "\n")
        self.text_box.see(tk.END)

    # ── HOTKEY ──────────────────────────────────────────────────

    def _on_key(self, e):
        if e.name != HOTKEY:
            return
        if e.event_type == "down" and not self.recording:
            self.root.after(0, self._start_recording)
        elif e.event_type == "up" and self.recording:
            self.root.after(0, self._stop_recording)

    # ── RUN ─────────────────────────────────────────────────────

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        self.running = False
        keyboard.unhook_all()
        if self.stream:
            self.stream.stop()
        self.root.destroy()


if __name__ == "__main__":
    app = VoiceApp()
    app.run()
