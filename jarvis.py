import os
import json
import queue
import threading
import time
import datetime
import platform
import tempfile
import asyncio
import webbrowser

import psutil
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

print("API Loaded:", GROQ_API_KEY is not None)

try:
    import speech_recognition as sr
except ImportError:
    sr = None

try:
    import edge_tts
except ImportError:
    edge_tts = None

try:
    import pygame
except ImportError:
    pygame = None

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    import AppOpener
except ImportError:
    AppOpener = None

try:
    from groq import Groq
except ImportError:
    Groq = None

IS_WINDOWS = platform.system() == "Windows"


GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = (
    Groq(api_key=GROQ_API_KEY)
    if Groq and GROQ_API_KEY
    else None
)

text_queue = queue.Queue()
tts_queue = queue.Queue()
is_speaking = threading.Event()
stop_event = threading.Event()
current_state = {"mode": "offline"}          # listening | thinking | speaking | offline
display_text = {"user": "", "jarvis": ""}

_threads_started = False
_threads_lock = threading.Lock()

# ══════════════════════════════════════════════
#  MEMORY SYSTEM
# ══════════════════════════════════════════════
MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_memory.json")
MAX_MEMORY = 50
memory_lock = threading.Lock()


def load_memory() -> list:
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []


def save_memory(history: list):
    with memory_lock:
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Memory] Save error: {e}")


def add_to_memory(history: list, role: str, content: str) -> list:
    history.append({"role": role, "content": content})
    if len(history) > MAX_MEMORY:
        history = history[-MAX_MEMORY:]
    return history


def clear_memory():
    global conversation_history
    conversation_history = []
    save_memory([])
    log("Memory cleared")


conversation_history: list = load_memory()

# ──────────────────────────────────────────────
#  ACTIVITY LOG
# ──────────────────────────────────────────────
activity_log = []
MAX_LOG = 14


def log(msg: str):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    activity_log.insert(0, f"[{ts}] {msg}")
    if len(activity_log) > MAX_LOG:
        activity_log.pop()


log(f"Memory loaded: {len(conversation_history)} messages")

# ──────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────
def _process_is_running(name: str) -> bool:
    """Best-effort check for whether something matching `name` is still running."""
    needle = name.lower().split()[0]
    for p in psutil.process_iter(["name"]):
        pname = (p.info.get("name") or "").lower()
        if needle and needle in pname:
            return True
    return False


def _windows_only(result_if_supported_fn, feature_name):
    if not IS_WINDOWS:
        return f"{feature_name} is only available on Windows."
    return result_if_supported_fn()


# ──────────────────────────────────────────────
#  COMPUTER CONTROL — apps
# ──────────────────────────────────────────────
def open_app(name: str) -> str:
    if not AppOpener:
        return "App control isn't available (AppOpener not installed)."
    try:
        AppOpener.open(name, match_closest=True, throw_error=True)
        return f"Opening {name}"
    except Exception:
        return f"I couldn't find an app called {name}"


def close_app(name: str) -> str:
    """Closes an app and verifies it, instead of always reporting success."""
    if not AppOpener:
        return "App control isn't available (AppOpener not installed)."
    try:
        AppOpener.close(name, match_closest=True, throw_error=True)
    except Exception:
        return f"I couldn't find {name} to close"

    time.sleep(1.2)
    if _process_is_running(name):
        return f"I tried closing {name}, but it still looks like it's running"
    return f"Closed {name}"


# ──────────────────────────────────────────────
#  COMPUTER CONTROL — volume
#  Sets an explicit level/state instead of blindly tapping media keys, and
#  reports which device it actually changed.
# ──────────────────────────────────────────────
def _get_windows_volume_interface():
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume = cast(interface, POINTER(IAudioEndpointVolume))
    return volume, devices


def _default_device_name() -> str:
    try:
        from pycaw.pycaw import AudioUtilities
        dev = AudioUtilities.GetSpeakers()
        return dev.FriendlyName or "default device"
    except Exception:
        return "default device"


def set_volume(percent: int) -> str:
    percent = max(0, min(100, percent))

    def _do():
        try:
            volume, _ = _get_windows_volume_interface()
            volume.SetMasterVolumeLevelScalar(percent / 100.0, None)
            return f"Volume set to {percent}% on {_default_device_name()}"
        except Exception:
            # Fallback: nudge with media keys if pycaw/comtypes isn't available
            if pyautogui:
                key = "volumeup" if percent >= 50 else "volumedown"
                for _ in range(5):
                    pyautogui.press(key)
                return f"Adjusted volume (install pycaw for exact levels)"
            return "Volume control isn't available."

    return _windows_only(_do, "Precise volume control")


def volume_up() -> str:
    def _do():
        try:
            volume, _ = _get_windows_volume_interface()
            cur = volume.GetMasterVolumeLevelScalar()
            new = min(1.0, cur + 0.10)
            volume.SetMasterVolumeLevelScalar(new, None)
            return f"Volume increased to {round(new*100)}% on {_default_device_name()}"
        except Exception:
            if pyautogui:
                for _ in range(5):
                    pyautogui.press("volumeup")
                return "Volume increased"
            return "Volume control isn't available."
    return _windows_only(_do, "Volume control")


def volume_down() -> str:
    def _do():
        try:
            volume, _ = _get_windows_volume_interface()
            cur = volume.GetMasterVolumeLevelScalar()
            new = max(0.0, cur - 0.10)
            volume.SetMasterVolumeLevelScalar(new, None)
            return f"Volume decreased to {round(new*100)}% on {_default_device_name()}"
        except Exception:
            if pyautogui:
                for _ in range(5):
                    pyautogui.press("volumedown")
                return "Volume decreased"
            return "Volume control isn't available."
    return _windows_only(_do, "Volume control")


def mute_volume() -> str:
    """Explicitly mutes (sets state, doesn't toggle blindly)."""
    def _do():
        try:
            volume, _ = _get_windows_volume_interface()
            volume.SetMute(1, None)
            return f"Muted {_default_device_name()}"
        except Exception:
            if pyautogui:
                pyautogui.press("volumemute")
                return "Toggled mute (install pycaw for a reliable mute)"
            return "Volume control isn't available."
    return _windows_only(_do, "Mute control")


def unmute_volume() -> str:
    def _do():
        try:
            volume, _ = _get_windows_volume_interface()
            volume.SetMute(0, None)
            return f"Unmuted {_default_device_name()}"
        except Exception:
            return "Couldn't unmute — install pycaw for reliable mute control."
    return _windows_only(_do, "Mute control")


def list_audio_devices() -> str:
    """Lists playback devices so the user can see which one is 'default'
    (this is the one volume commands and media keys both affect)."""
    def _do():
        try:
            from pycaw.pycaw import AudioUtilities
            names = [d.FriendlyName for d in AudioUtilities.GetAllDevices()
                      if getattr(d, "FriendlyName", None)]
            current = _default_device_name()
            return f"Default output is {current}. Devices seen: " + ", ".join(names[:6])
        except Exception:
            return "Install pycaw to list audio devices."
    return _windows_only(_do, "Audio device listing")


# ──────────────────────────────────────────────
#  COMPUTER CONTROL — system
# ──────────────────────────────────────────────
def take_screenshot():
    if not pyautogui:
        return "Screenshots aren't available (pyautogui not installed)."
    p = os.path.expanduser("~/Desktop/screenshot.png")
    pyautogui.screenshot().save(p)
    return "Screenshot saved to Desktop"


def open_website(url):
    webbrowser.open(url)
    return f"Opening {url}"


def shutdown_pc():
    return _windows_only(lambda: (os.system("shutdown /s /t 5"), "Shutting down in 5 seconds")[1],
                          "Shutdown")


def restart_pc():
    return _windows_only(lambda: (os.system("shutdown /r /t 5"), "Restarting in 5 seconds")[1],
                          "Restart")


def lock_pc():
    return _windows_only(lambda: (os.system("rundll32.exe user32.dll,LockWorkStation"), "PC locked")[1],
                          "Lock")


def sleep_pc():
    return _windows_only(
        lambda: (os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0"), "Going to sleep")[1],
        "Sleep")


def get_battery():
    b = psutil.sensors_battery()
    return f"Battery at {int(b.percent)}%" if b else "Battery unavailable"


def get_time():
    return f"The time is {datetime.datetime.now().strftime('%I:%M %p')}"


def get_date():
    return f"Today is {datetime.datetime.now().strftime('%B %d, %Y')}"


def handle_command(text):
    if "open youtube" in text:
        return open_website("https://youtube.com")
    if "open google" in text:
        return open_website("https://google.com")
    if "open instagram" in text:
        return open_website("https://instagram.com")
    if "open twitter" in text or "open x" in text:
        return open_website("https://x.com")
    if "search" in text and "youtube" in text:
        q = text.replace("search", "").replace("on youtube", "").replace("youtube", "").strip()
        return open_website(f"https://www.youtube.com/results?search_query={q.replace(' ', '+')}")
    if "search" in text and "google" in text:
        q = text.replace("search", "").replace("on google", "").replace("google", "").strip()
        return open_website(f"https://www.google.com/search?q={q.replace(' ', '+')}")
    if "list audio devices" in text or "what's my audio device" in text:
        return list_audio_devices()
    if "unmute" in text:
        return unmute_volume()
    if "mute" in text:
        return mute_volume()
    if "volume up" in text or "increase volume" in text:
        return volume_up()
    if "volume down" in text or "decrease volume" in text:
        return volume_down()
    if "set volume to" in text:
        digits = "".join(ch for ch in text.split("set volume to")[-1] if ch.isdigit())
        if digits:
            return set_volume(int(digits))
    if "screenshot" in text:
        return take_screenshot()
    if "shutdown" in text or "shut down" in text:
        return shutdown_pc()
    if "restart" in text:
        return restart_pc()
    if "lock" in text:
        return lock_pc()
    if "sleep" in text:
        return sleep_pc()
    if "battery" in text:
        return get_battery()
    if "time" in text:
        return get_time()
    if "date" in text:
        return get_date()
    if "open" in text:
        return open_app(text.replace("open", "").strip())
    if "close" in text:
        return close_app(text.replace("close", "").strip())
    return None


# ──────────────────────────────────────────────
#  TTS
# ──────────────────────────────────────────────
def tts_worker():
    if not (pygame and edge_tts):
        log("TTS unavailable (pygame/edge_tts not installed)")
        return
    pygame.mixer.init()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    while not stop_event.is_set():
        try:
            text = tts_queue.get(timeout=1)
        except queue.Empty:
            continue
        if text is None:
            break
        is_speaking.set()
        current_state["mode"] = "speaking"
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                tmp = f.name
            loop.run_until_complete(
                edge_tts.Communicate(text, voice="en-GB-RyanNeural").save(tmp))
            pygame.mixer.music.load(tmp)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and not stop_event.is_set():
                time.sleep(0.1)
            pygame.mixer.music.unload()
        except Exception as e:
            print(f"TTS: {e}")
        finally:
            is_speaking.clear()
            if not stop_event.is_set():
                current_state["mode"] = "listening"
            if tmp:
                try:
                    os.remove(tmp)
                except Exception:
                    pass
        tts_queue.task_done()
    try:
        pygame.mixer.quit()
    except Exception:
        pass
    loop.close()
    log("TTS worker stopped")


def speak(t):
    tts_queue.put(t)


# ──────────────────────────────────────────────
#  AI — full conversation memory
# ──────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are Jarvis, a smart, loyal, and witty AI assistant inspired by Iron Man. "
    "You remember everything the user has told you across all sessions. "
    "Keep responses concise, clear, and conversational. "
    "When the user refers to something from earlier in the conversation, "
    "use that context naturally without being asked."
)


def ask_ai(prompt: str) -> str:
    global conversation_history
    if not client:
        return "AI isn't configured — set the GROQ_API_KEY environment variable."
    try:
        conversation_history = add_to_memory(conversation_history, "user", prompt)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history

        r = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        )
        reply = r.choices[0].message.content

        conversation_history = add_to_memory(conversation_history, "assistant", reply)
        save_memory(conversation_history)

        log(f"Memory: {len(conversation_history)} msgs stored")
        return reply
    except Exception as e:
        return f"AI Error: {e}"


# ──────────────────────────────────────────────
#  LISTEN / PROCESS
#  Both loops now poll with a short timeout and check stop_event, so they
#  exit within ~1 second of stop_assistant() being called instead of
#  blocking forever (the old code could only be killed with os._exit).
# ──────────────────────────────────────────────
def listen():
    if not sr:
        log("Speech recognition unavailable (speech_recognition not installed)")
        return
    rec = sr.Recognizer()
    rec.dynamic_energy_threshold = True
    rec.pause_threshold = 0.8
    try:
        mic = sr.Microphone()
    except Exception as e:
        log(f"No microphone available: {e}")
        return

    with mic as src:
        rec.adjust_for_ambient_noise(src, duration=2)
        current_state["mode"] = "listening"
        log("Listening started")
        while not stop_event.is_set():
            if is_speaking.is_set():
                is_speaking.wait(timeout=1)
                continue
            try:
                audio = rec.listen(src, timeout=1, phrase_time_limit=7)
            except sr.WaitTimeoutError:
                continue
            except Exception:
                continue
            try:
                text_queue.put(rec.recognize_google(audio).lower())
            except Exception:
                pass
    log("Listening stopped")


def process_text():
    while not stop_event.is_set():
        try:
            text = text_queue.get(timeout=1)
        except queue.Empty:
            continue

        display_text["user"] = text
        log(f"Heard: {text[:40]}")

        if "stop listening" in text:
            display_text["jarvis"] = "Goodbye. Shutting down."
            speak("Goodbye. Shutting down.")
            tts_queue.join()
            stop_assistant()
            break

        if "jarvis" in text and "clear" in text and "memory" in text:
            clear_memory()
            r = "Memory cleared. I've forgotten our previous conversations."
            display_text["jarvis"] = r
            speak(r)
            continue

        if "jarvis" in text and "remember" in text and "how" in text:
            r = f"I currently have {len(conversation_history)} messages in memory."
            display_text["jarvis"] = r
            speak(r)
            continue

        if "jarvis" in text:
            prompt = text.replace("jarvis", "").strip()
            if not prompt:
                r = "Yes? How can I help you?"
                display_text["jarvis"] = r
                speak(r)
                continue

            result = handle_command(prompt)
            if result:
                display_text["jarvis"] = result
                speak(result)
                log(f"CMD: {result[:40]}")
            else:
                current_state["mode"] = "thinking"
                display_text["jarvis"] = "Thinking..."
                log("Querying AI with memory…")
                reply = ask_ai(prompt)
                display_text["jarvis"] = reply
                speak(reply)
                log(f"AI reply: {reply[:40]}…")
    log("Command processor stopped")


# ──────────────────────────────────────────────
#  START / STOP — call these from the Streamlit app
# ──────────────────────────────────────────────
def start_assistant():
    global _threads_started
    with _threads_lock:
        if _threads_started:
            return False
        stop_event.clear()
        threading.Thread(target=tts_worker, daemon=True).start()
        threading.Thread(target=listen, daemon=True).start()
        threading.Thread(target=process_text, daemon=True).start()
        _threads_started = True
        log("Assistant started")
        return True


def stop_assistant():
    """Cleanly stops all background threads without killing the process
    that's hosting Streamlit. Safe to call more than once."""
    global _threads_started
    with _threads_lock:
        stop_event.set()
        tts_queue.put(None)
        try:
            if pygame:
                pygame.mixer.music.stop()
        except Exception:
            pass
        current_state["mode"] = "offline"
        _threads_started = False
        log("Assistant stopped")
        return True


def is_running() -> bool:
    return _threads_started