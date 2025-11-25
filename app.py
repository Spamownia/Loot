#!/usr/bin/env python3
import os
import threading
import time
import random
import ftplib
import json
import requests
from flask import Flask, jsonify
from datetime import datetime
import pytz
import traceback

# ---------------- CONFIG ----------------
FTP_HOST = "195.179.226.218"
FTP_PORT = 56421
FTP_USER = "gpftp37275281717442833"
FTP_PASS = "LXNdGShY"
REMOTE_DIR = "/SCUM/Saved/Config/WindowsServer/Loot"

VARIANTS = [f"GeneralZoneModifiers_{i}.json" for i in range(1, 92)]

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1439377206999646208/0WUe3Vl_75zTQtzBCSvC9uDXJdylvEt9VKB0Bes6NviupWMqzcZElGXiMsbg2N6rL5iU"

# Godziny odpaleń: 03:55, 09:55, 15:55, 21:55
RUN_TIMES = [(3, 55), (9, 55), (15, 55), (21, 55)]

TMP_REMOTE_NAME = "._tmp_upload.json"
TARGET_REMOTE_NAME = "GeneralZoneModifiers.json"
# ----------------------------------------

app = Flask(__name__)
_worker_thread = None
_worker_stop = threading.Event()
_last_chosen = None
_lock = threading.Lock()

# Śledzimy ostatnie uruchomienia dla każdego harmonogramu (key = (hour, minute))
_last_runs = {}  # {(hour, minute): datetime_of_last_run}

def choose_variant():
    return random.choice(VARIANTS)


def upload_to_ftp(local_file: str) -> bool:
    try:
        print(f"[FTP] Connecting to {FTP_HOST}:{FTP_PORT} ...")
        with ftplib.FTP() as ftp:
            ftp.connect(FTP_HOST, FTP_PORT, timeout=20)
            ftp.login(FTP_USER, FTP_PASS)
            ftp.cwd(REMOTE_DIR)
            with open(local_file, "rb") as f:
                print(f"[FTP] Uploading temp file {TMP_REMOTE_NAME} ...")
                ftp.storbinary(f"STOR {TMP_REMOTE_NAME}", f)
            # usuń docelowy jeśli istnieje (ignorujemy błąd jeśli nie istnieje)
            try:
                ftp.delete(TARGET_REMOTE_NAME)
            except Exception:
                pass
            # poprawiona nazwa zmiennej TMP_REMOTE_NAME
            ftp.rename(TMP_REMOTE_NAME, TARGET_REMOTE_NAME)
            print("[FTP] Upload and rename successful.")
        return True
    except Exception as e:
        print("[FTP] Error during FTP upload:", e)
        traceback.print_exc()
        return False


def send_discord_notification(chosen_file: str):
    print("[Discord] Preparing notification...")
    try:
        with open(chosen_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        modifiers = data.get("Modifiers", [])
        zone_names = []
        for mod in modifiers:
            zones = mod.get("Zones", [])
            for z in zones:
                name = z.get("Name")
                if name:
                    zone_names.append(name)
        if zone_names:
            content = f"🎲 **Active Double Loot Zones:** {', '.join(zone_names)}"
        else:
            content = f"🎲 **Wariant loot-u wybrany:** {chosen_file}"
    except Exception as e:
        content = f"🎲 **Wariant loot-u wybrany (błąd odczytu JSON):** {chosen_file} ({e})"

    timestamp = int(time.time())
    content += f"\n⏱ Last draw: <t:{timestamp}:R>"

    try:
        print("[Discord] Sending message:", content)
        r = requests.post(DISCORD_WEBHOOK, json={"content": content}, timeout=15)
        print(f"[Discord] Response: {r.status_code} {r.text}")
    except Exception as e:
        print("[Discord] Error while sending webhook:", e)
        traceback.print_exc()


def run_cycle():
    global _last_chosen
    try:
        with _lock:
            chosen = choose_variant()
            # unikamy powtórki identycznego wariantu względem ostatniego, kilka prób
            if _last_chosen is not None and len(VARIANTS) > 1:
                attempts = 0
                while chosen == _last_chosen and attempts < 5:
                    chosen = choose_variant()
                    attempts += 1
            _last_chosen = chosen

        if not os.path.isfile(chosen):
            print(f"[Cycle] ERROR: local variant file not found: {chosen}")
            return

        print(f"[Cycle] Selected variant: {chosen}")
        ok = upload_to_ftp(chosen)
        if ok:
            send_discord_notification(chosen)
            print(f"[Cycle] Completed successfully for variant: {chosen}")
        else:
            print(f"[Cycle] Upload failed for variant: {chosen}")
    except Exception as e:
        print("[Cycle] Unexpected exception in run_cycle:", e)
        traceback.print_exc()


# ------------------- NEW SCHEDULING SYSTEM ---------------------
def should_run_now():
    """
    Sprawdza czy lokalny czas (Europe/Warsaw) odpowiada któremuś z RUN_TIMES
    i czy dla tego konkretnego (hour, minute) nie wykonaliśmy już cyklu w tej samej minucie.
    Zwraca True jeżeli należy uruchomić cykl teraz.
    """
    tz = pytz.timezone("Europe/Warsaw")
    now = datetime.now(tz)
    current_hm = (now.hour, now.minute)

    if current_hm not in RUN_TIMES:
        return False

    last_run_dt = _last_runs.get(current_hm)
    # jeśli nie było uruchomienia dla tej pary (hour,minute), albo ostatnie uruchomienie
    # nie było w tej samej minucie (np. inny dzień / inna minuta) -> można uruchomić
    if last_run_dt is None or not (last_run_dt.date() == now.date() and last_run_dt.hour == now.hour and last_run_dt.minute == now.minute):
        # zapisujemy czas uruchomienia, aby nie powtórzyć w tej samej minucie
        _last_runs[current_hm] = now
        return True

    # już uruchomione w tej minucie -> nie uruchamiać ponownie
    return False


def background_worker():
    print("[Worker] Scheduler worker started.")
    try:
        while not _worker_stop.is_set():
            try:
                if should_run_now():
                    print("[Scheduler] Scheduled time hit — running cycle.")
                    run_cycle()
            except Exception as e:
                print("[Worker] Exception in schedule check:", e)
                traceback.print_exc()

            # sprawdzamy co 15 sekund (tolerancja wystarczająca przy sprawdzaniu minut)
            time.sleep(15)
    except Exception as e:
        print("[Worker] Fatal exception in background_worker:", e)
        traceback.print_exc()
    finally:
        print("[Worker] Scheduler worker stopped.")
# ---------------------------------------------------------------


def start_background_thread():
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _worker_stop.clear()
        _worker_thread = threading.Thread(target=background_worker, daemon=True)
        _worker_thread.start()
        print("[Main] Background worker thread started.")


# --- Flask routes ---
@app.route("/", methods=["GET"])
def index():
    return "Loot automation: running", 200


@app.route("/run-now", methods=["POST", "GET"])
def run_now():
    def _runner():
        print("[RunNow] Manual trigger started.")
        run_cycle()
        print("[RunNow] Manual trigger finished.")
    threading.Thread(target=_runner, daemon=True).start()
    return jsonify({"ok": True, "message": "Cycle started in background"}), 202


@app.route("/status", methods=["GET"])
def status():
    # lista dostępnych wariantów (lokalnie)
    available = [f for f in VARIANTS if os.path.isfile(f)]
    return jsonify({
        "service": "loot-automation",
        "run_times": RUN_TIMES,
        "variants_available": available,
        "last_runs": {f"{h:02d}:{m:02d}": (_last_runs.get((h, m)).isoformat() if _last_runs.get((h, m)) else None) for (h, m) in RUN_TIMES}
    }), 200


def stop_background_thread():
    _worker_stop.set()
    if _worker_thread is not None:
        _worker_thread.join(timeout=5)


# --- Start scheduled worker immediately ---
start_background_thread()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"[Main] Starting Flask on 0.0.0.0:{port}")
    # threaded=True aby Flask nie blokował wątków (bezpieczniej na Render)
    app.run(host="0.0.0.0", port=port, threaded=True)
