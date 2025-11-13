# upload_loot_variant.py
# Autor: GPT-5
# Działanie: losowo wybiera wariant pliku lootów i wysyła go na serwer SCUM przez FTP.
# Uruchomienie np. przez cron lub web service Rendera.

import ftplib
import random
import os
import sys

# ------- USTAWIENIA -------
FTP_HOST = "195.179.226.218"
FTP_PORT = 56421
FTP_USER = "gpftp37275281717442833"
FTP_PASS = "LXNdGShY"
REMOTE_DIR = "/SCUM/Saved/Config/WindowsServer/Loot"

# Lista dostępnych wariantów pliku (muszą znajdować się lokalnie)
VARIANTS = [
    "GeneralZoneModifiers_1.json",
    "GeneralZoneModifiers_2.json",
    "GeneralZoneModifiers_3.json"
]
# ---------------------------


def choose_variant():
    """Losowo wybiera plik wariantu."""
    return random.choice(VARIANTS)


def upload(local_file, remote_path):
    """Łączy się przez FTP, wysyła plik i podmienia GeneralZoneModifiers.json."""
    try:
        with ftplib.FTP() as ftp:
            ftp.connect(FTP_HOST, FTP_PORT, timeout=15)
            ftp.login(FTP_USER, FTP_PASS)
            ftp.cwd(remote_path)

            tmp_name = "._tmp_upload.json"

            print(f"⏫ Wysyłanie pliku {local_file}...")
            with open(local_file, "rb") as f:
                ftp.storbinary(f"STOR {tmp_name}", f)

            try:
                ftp.delete("GeneralZoneModifiers.json")
            except Exception:
                pass

            ftp.rename(tmp_name, "GeneralZoneModifiers.json")
            print("✅ Wgrano i podmieniono GeneralZoneModifiers.json na serwerze.")

    except Exception as e:
        print("❌ Błąd FTP:", e)
        sys.exit(1)


if __name__ == "__main__":
    chosen = choose_variant()
    if not os.path.isfile(chosen):
        print(f"❌ Brak pliku lokalnego: {chosen}")
        sys.exit(1)

    print("🎲 Wybrano wariant:", chosen)
    upload(chosen, REMOTE_DIR)
    print("ℹ️  Upload zakończony. Teraz wykonaj restart serwera z panelu G-Portal.")
