import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import socket
import time
import json
import os
import numpy as np

try:
    import pyaudiowpatch as pyaudio
except ImportError:
    messagebox.showerror("Ошибка", "Установи: pip install pyaudiowpatch")
    raise

try:
    import lameenc
except ImportError:
    messagebox.showerror("Ошибка", "Установи: pip install lameenc")
    raise


CONFIG_FILE = "shoutcast_settings.json"


class ShoutcastStreamer:
    def __init__(self, app):
        self.app = app
        self.running = False
        self.sock = None
        self.stream = None
        self.pa = None
        self.encoder = None
        self.thread = None
        self.device_index = None
        self.sample_rate = None
        self.channels = None
        self.bitrate = None

    def connect(self, host, port, password, bitrate, name, genre, url, title):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(10)
            self.sock.connect((host, int(port)))

            self.sock.sendall(f"{password}\r\n".encode("utf-8"))
            response = self.sock.recv(1024).decode("utf-8", errors="ignore").strip()

            if not response.upper().startswith("OK"):
                raise Exception(f"Сервер отклонил пароль: {response}")

            headers = (
                f"icy-name:{name}\r\n"
                f"icy-genre:{genre}\r\n"
                f"icy-url:{url}\r\n"
                f"icy-pub:1\r\n"
                f"icy-br:{bitrate}\r\n"
                f"icy-metaint:0\r\n"
                f"Content-Type:audio/mpeg\r\n"
                f"\r\n"
            )
            self.sock.sendall(headers.encode("utf-8"))
            self.sock.settimeout(None)

            self.app.log(f"Подключено! Ответ сервера: {response}")
            return True

        except Exception as e:
            self.app.log(f"Ошибка подключения: {e}")
            if self.sock:
                try:
                    self.sock.close()
                except:
                    pass
                self.sock = None
            return False

    def start(self, host, port, password, bitrate, name, genre, url, title, device_index, sample_rate, channels):
        if self.running:
            return

        if not self.connect(host, port, password, bitrate, name, genre, url, title):
            self.app.set_status("Ошибка подключения", "red")
            return

        self.device_index = device_index
        self.sample_rate = sample_rate
        self.channels = channels
        self.bitrate = bitrate

        self.running = True
        self.app.set_status("В эфире", "green")
        self.thread = threading.Thread(target=self._stream_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self._close_audio()
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None
        self.app.set_status("Отключено", "gray")
        self.app.log("Стрим остановлен")

    def _close_audio(self):
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except:
                pass
            self.stream = None
        if self.pa:
            try:
                self.pa.terminate()
            except:
                pass
            self.pa = None

    def _open_audio(self):
        self.pa = pyaudio.PyAudio()

        self.encoder = lameenc.Encoder()
        self.encoder.set_bit_rate(int(self.bitrate))
        self.encoder.set_in_sample_rate(int(self.sample_rate))
        self.encoder.set_channels(int(self.channels))
        self.encoder.set_quality(2)
        self.encoder.silence()

        CHUNK = 1024

        def callback(in_data, frame_count, time_info, status):
            if not self.running:
                return (None, pyaudio.paComplete)

            try:
                audio = np.frombuffer(in_data, dtype=np.int16)

                if len(audio) > 0:
                    rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2))
                    level = min(100, int(rms / 100))
                    self.app.root.after(0, self.app.update_level, level)

                mp3_data = self.encoder.encode(audio.tobytes())
                if mp3_data and self.sock:
                    self.sock.sendall(mp3_data)

            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError) as e:
                self.app.root.after(0, self.app.log, f"Соединение с сервером разорвано: {e}")
                self.running = False
                return (None, pyaudio.paComplete)
            except Exception as e:
                self.app.root.after(0, self.app.log, f"Ошибка в callback: {e}")
                return (None, pyaudio.paComplete)

            return (in_data, pyaudio.paContinue)

        self.stream = self.pa.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=CHUNK,
            stream_callback=callback
        )
        self.stream.start_stream()

    def _stream_loop(self):
        self.app.log(f"Стрим запущен | {self.sample_rate} Hz | {self.channels} ch | {self.bitrate} kbps")

        while self.running:
            try:
                self._open_audio()
                self.app.log("Захват звука запущен")

                while self.running and self.stream and self.stream.is_active():
                    time.sleep(0.2)

                if self.running:
                    self.app.log("Захват звука прервался (переключение трека?). Перезапускаю...")
                    self._close_audio()
                    time.sleep(0.5)

            except Exception as e:
                self.app.log(f"Ошибка аудио: {e}")
                self._close_audio()
                if self.running:
                    time.sleep(1)

        self._close_audio()


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("LoopShout")
        self.root.geometry("520x640")
        self.root.resizable(False, False)

        self.streamer = ShoutcastStreamer(self)
        self.devices = []

        self._build_ui()
        self.refresh_devices()
        self.load_settings()

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # === Server settings ===
        frm = ttk.LabelFrame(self.root, text="Сервер Shoutcast", padding=10)
        frm.pack(fill="x", **pad)

        ttk.Label(frm, text="Хост / IP:").grid(row=0, column=0, sticky="w")
        self.host = ttk.Entry(frm, width=28)
        self.host.insert(0, "127.0.0.1")
        self.host.grid(row=0, column=1, sticky="ew", padx=5)

        ttk.Label(frm, text="Порт:").grid(row=0, column=2, sticky="w")
        self.port = ttk.Entry(frm, width=8)
        self.port.insert(0, "8000")
        self.port.grid(row=0, column=3, sticky="w")

        ttk.Label(frm, text="Пароль:").grid(row=1, column=0, sticky="w")
        self.password = ttk.Entry(frm, width=28, show="*")
        self.password.grid(row=1, column=1, sticky="ew", padx=5)

        ttk.Label(frm, text="Битрейт:").grid(row=1, column=2, sticky="w")
        self.bitrate = ttk.Combobox(frm, values=["64", "96", "128", "160", "192", "256", "320"], width=6)
        self.bitrate.set("128")
        self.bitrate.grid(row=1, column=3, sticky="w")

        # === Station info ===
        frm2 = ttk.LabelFrame(self.root, text="Информация о станции", padding=10)
        frm2.pack(fill="x", **pad)

        ttk.Label(frm2, text="Название:").grid(row=0, column=0, sticky="w")
        self.name = ttk.Entry(frm2, width=40)
        self.name.insert(0, "My Radio")
        self.name.grid(row=0, column=1, columnspan=3, sticky="ew", padx=5)

        ttk.Label(frm2, text="Жанр:").grid(row=1, column=0, sticky="w")
        self.genre = ttk.Entry(frm2, width=20)
        self.genre.insert(0, "Various")
        self.genre.grid(row=1, column=1, sticky="ew", padx=5)

        ttk.Label(frm2, text="URL:").grid(row=1, column=2, sticky="w")
        self.url = ttk.Entry(frm2, width=20)
        self.url.insert(0, "http://example.com")
        self.url.grid(row=1, column=3, sticky="ew", padx=5)

        ttk.Label(frm2, text="Сейчас играет:").grid(row=2, column=0, sticky="w")
        self.title = ttk.Entry(frm2, width=40)
        self.title.insert(0, "Live")
        self.title.grid(row=2, column=1, columnspan=3, sticky="ew", padx=5)

        # === Device ===
        frm3 = ttk.LabelFrame(self.root, text="Устройство (системный звук)", padding=10)
        frm3.pack(fill="x", **pad)

        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(frm3, textvariable=self.device_var, width=55, state="readonly")
        self.device_combo.pack(side="left", fill="x", expand=True)

        ttk.Button(frm3, text="Обновить", command=self.refresh_devices).pack(side="right", padx=5)

        # === Controls ===
        frm4 = ttk.Frame(self.root)
        frm4.pack(fill="x", **pad)

        self.btn_connect = ttk.Button(frm4, text="▶  В ЭФИР", command=self.on_connect, width=18)
        self.btn_connect.pack(side="left", padx=5)

        self.btn_disconnect = ttk.Button(frm4, text="■  СТОП", command=self.on_disconnect, width=12, state="disabled")
        self.btn_disconnect.pack(side="left", padx=5)

        self.status_label = ttk.Label(frm4, text="Отключено", foreground="gray", font=("", 10, "bold"))
        self.status_label.pack(side="left", padx=15)

        self.level = ttk.Progressbar(frm4, length=120, mode="determinate", maximum=100)
        self.level.pack(side="right", padx=5)

        # === Log ===
        frm5 = ttk.LabelFrame(self.root, text="Лог", padding=5)
        frm5.pack(fill="both", expand=True, **pad)

        self.log_text = scrolledtext.ScrolledText(frm5, height=10, state="disabled", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)

        ttk.Label(self.root, text="LoopShout  •  Open Source  •  Только Shoutcast",
                  foreground="gray").pack(pady=4)

    def load_settings(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.host.delete(0, tk.END)
            self.host.insert(0, data.get("host", "127.0.0.1"))

            self.port.delete(0, tk.END)
            self.port.insert(0, data.get("port", "8000"))

            self.password.delete(0, tk.END)
            self.password.insert(0, data.get("password", ""))

            self.bitrate.set(data.get("bitrate", "128"))

            self.name.delete(0, tk.END)
            self.name.insert(0, data.get("name", "My Radio"))

            self.genre.delete(0, tk.END)
            self.genre.insert(0, data.get("genre", "Various"))

            self.url.delete(0, tk.END)
            self.url.insert(0, data.get("url", "http://example.com"))

            self.title.delete(0, tk.END)
            self.title.insert(0, data.get("title", "Live"))

            self.log("Настройки загружены")
        except Exception as e:
            self.log(f"Не удалось загрузить настройки: {e}")

    def save_settings(self):
        data = {
            "host": self.host.get().strip(),
            "port": self.port.get().strip(),
            "password": self.password.get(),
            "bitrate": self.bitrate.get(),
            "name": self.name.get().strip(),
            "genre": self.genre.get().strip(),
            "url": self.url.get().strip(),
            "title": self.title.get().strip(),
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.log("Настройки сохранены")
        except Exception as e:
            self.log(f"Ошибка сохранения: {e}")

    def refresh_devices(self):
        self.devices = []
        try:
            pa = pyaudio.PyAudio()
            wasapi_info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)

            names = []
            for loopback in pa.get_loopback_device_info_generator():
                idx = loopback["index"]
                name = loopback["name"]
                rate = int(loopback["defaultSampleRate"])
                ch = loopback["maxInputChannels"]
                self.devices.append({
                    "index": idx,
                    "name": name,
                    "rate": rate,
                    "channels": ch
                })
                names.append(f"[{idx}] {name} ({rate} Hz, {ch} ch)")

            pa.terminate()

            self.device_combo["values"] = names
            if names:
                self.device_combo.current(0)
            self.log(f"Найдено устройств loopback: {len(names)}")
        except Exception as e:
            self.log(f"Ошибка списка устройств: {e}")
            messagebox.showerror("Ошибка", f"Не удалось получить устройства:\n{e}")

    def on_connect(self):
        self.save_settings()

        if not self.devices:
            messagebox.showwarning("Нет устройств", "Сначала обнови список устройств")
            return

        sel = self.device_combo.current()
        if sel < 0:
            return

        dev = self.devices[sel]

        host = self.host.get().strip()
        port = self.port.get().strip()
        password = self.password.get()
        bitrate = self.bitrate.get()
        name = self.name.get().strip() or "Radio"
        genre = self.genre.get().strip() or "Various"
        url = self.url.get().strip() or "http://localhost"
        title = self.title.get().strip() or "Live"

        if not host or not port or not password:
            messagebox.showwarning("Ошибка", "Заполни хост, порт и пароль")
            return

        self.btn_connect.config(state="disabled")
        self.btn_disconnect.config(state="normal")

        self.streamer.start(
            host, port, password, bitrate,
            name, genre, url, title,
            dev["index"], dev["rate"], dev["channels"]
        )

    def on_disconnect(self):
        self.streamer.stop()
        self.btn_connect.config(state="normal")
        self.btn_disconnect.config(state="disabled")
        self.update_level(0)

    def set_status(self, text, color):
        self.status_label.config(text=text, foreground=color)

    def update_level(self, value):
        self.level["value"] = value

    def log(self, msg):
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"{time.strftime('%H:%M:%S')}  {msg}\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.mainloop()

    def on_close(self):
        self.save_settings()
        self.streamer.stop()
        self.root.destroy()


if __name__ == "__main__":
    App().run()