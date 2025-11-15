#!/usr/bin/env python3
import os
import threading
import time
import random
import ftplib
import json
import requests
from flask import Flask, jsonify

# ---------------- CONFIG ----------------
FTP_HOST = "195.179.226.218"
FTP_PORT = 56421
FTP_USER = "gpftp37275281717442833"
FTP_PASS = "LXNdGShY"
REMOTE_DIR = "/SCUM/Saved/Config/WindowsServer/Loot"

VARIANTS = [
    "variants/GeneralZoneModifiers_1.json",
    "variants/GeneralZoneModifiers_2.json",
    "variants/GeneralZoneModifiers_3.json",
    "variants/GeneralZoneModifiers_4.json"
]

INTERVAL_SECONDS = 4 * 3600
TMP_REMOTE_NAME = "._tmp_upload.json"
TARGET_REMOTE_NAME = "GeneralZoneModifiers.json"

app = Flask(__name__)
_last_chosen = None
_last_run_timestamp = 0
_lock = threading.Lock()
_clock_text = "Czekam na pierwsze losowanie..."


def choose_variant():
    return random.choice(VARIANTS)


def upload_to_ftp(local_file: str) -> bool:
    try:
        with ftplib.FTP() as ftp:
            ftp.connect(FTP_HOST, FTP_PORT, timeout=20)
            ftp.login(FTP_USER, FTP_PASS)
            ftp.cwd(REMOTE_DIR)
            with open(local_file, "rb") as f:
                ftp.storbinary(f"STOR {TMP_REMOTE_NAME}", f)
            try:
                ftp.delete(TARGET_REMOTE_NAME)
            except Exception:
                pass
            ftp.rename(TMP_REMOTE_NAME, TARGET_REMOTE_NAME)
        return True
    except Exception as e:
        print("[FTP]", e)
        return False


def run_cycle():
    global _last_chosen, _last_run_timestamp, _clock_text
    with _lock:
        chosen = choose_variant()
        if _last_chosen is not None and len(VARIANTS) > 1:
            attempts = 0
            while chosen == _last_chosen and attempts < 5:
                chosen = choose_variant()
                attempts += 1
        _last_chosen = chosen
        _last_run_timestamp = time.time()
        _clock_text = "Czekam na pierwsze losowanie..."

    ok = upload_to_ftp(chosen)
    return {"ok": ok, "file": chosen}


def background_worker():
    while True:
        run_cycle()
        slept = 0
        while slept < INTERVAL_SECONDS:
            time.sleep(1)
            slept += 1


def clock_worker():
    global _clock_text
    while True:
        if _last_run_timestamp != 0:
            elapsed = int(time.time() - _last_run_timestamp)
            h = elapsed // 3600
            m = (elapsed % 3600) // 60
            s = elapsed % 60
            _clock_text = f"Czas od ostatniego losowania: {h:02d}:{m:02d}:{s:02d}"
        time.sleep(1)


# --- Flask endpoints ---
@app.route("/", methods=["GET"])
def index():
    return "Loot automation: running", 200

@app.route("/run-now", methods=["POST", "GET"])
def run_now():
    threading.Thread(target=run_cycle, daemon=True).start()
    return jsonify({"ok": True}), 202

@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "service": "loot-automation",
        "interval_hours": INTERVAL_SECONDS // 3600,
        "variants_available": [f for f in VARIANTS if os.path.isfile(f)]
    }), 200

@app.route("/clock", methods=["GET"])
def clock_status():
    return _clock_text, 200


# --- Start background threads ---
threading.Thread(target
