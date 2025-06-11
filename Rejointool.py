import requests
import subprocess
import urllib.parse
import time
import os
import json
import psutil
from threading import Thread

CONFIG_FILE = "rejoin_config.json"

# === Загрузка и сохранение конфигурации ===
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "CHECK_INTERVAL": 15,
        "CUSTOM_TITLE": "SORA_",
        "accounts": []
    }

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

config = load_config()

def get_csrf_token(session):
    r = session.post("https://auth.roblox.com/v2/logout")
    return r.headers.get("x-csrf-token")

def get_user(session):
    r = session.get("https://users.roblox.com/v1/users/authenticated")
    return r.json() if r.ok else None

def get_ticket(session):
    r = session.post("https://auth.roblox.com/v1/authentication-ticket/")
    return r.headers.get("rbx-authentication-ticket") if r.status_code == 200 else None

def get_presence(session, uid):
    r = session.post("https://presence.roblox.com/v1/presence/users", json={"userIds": [uid]})
    return r.json()["userPresences"][0] if r.ok else None

def launch_roblox(ticket, place_id, username, private_url=None):
    timestamp = int(time.time() * 1000)
    url = (
        f"https://assetgame.roblox.com/game/PlaceLauncher.ashx?request=RequestGame&"
        f"browserTrackerId=1337&placeId={place_id}&isPlayTogetherGame=false"
    )
    if private_url:
        url += f"&linkCode={urllib.parse.quote(private_url.split('code=')[1].split('&')[0])}"
    encoded = urllib.parse.quote(url, safe="")
    uri = (
        f"roblox-player:1+launchmode:play+gameinfo:{ticket}+launchtime:{timestamp}"
        f"+placelauncherurl:{encoded}+browsertrackerid:1337+robloxLocale:ru_ru+gameLocale:ru_ru"
    )
    title = f"{config['CUSTOM_TITLE']}{username}"
    print(f"[*] Запуск Roblox: {title}")
    subprocess.Popen(["cmd", "/c", "start", f"""{title}""", uri], shell=True)

def kill_window_by_title(title):
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if 'RobloxPlayerBeta' in proc.info['name']:
                if title.lower() in ' '.join(proc.cmdline()).lower():
                    proc.kill()
                    print(f"[x] Убито окно: {title}")
        except:
            continue

def worker(account):
    session = requests.Session()
    session.cookies['.ROBLOSECURITY'] = account['Cookie']
    session.headers.update({"Content-Type": "application/json"})

    csrf = get_csrf_token(session)
    if not csrf:
        print(f"❌ Не удалось получить CSRF для {account['name']}")
        return
    session.headers['X-CSRF-TOKEN'] = csrf

    while True:
        pres = get_presence(session, account['id'])
        if pres and pres['userPresenceType'] == 2 and pres.get('placeId') == int(account['PlaceId']):
            print(f"[✓] {account['name']} уже в нужной игре")
        else:
            print(f"[!] {account['name']} не в игре или в другой, перезапуск...")
            kill_window_by_title(f"{config['CUSTOM_TITLE']}{account['name']}")
            ticket = get_ticket(session)
            if ticket:
                launch_roblox(ticket, account['PlaceId'], account['name'], account.get("PrivatSr"))
        time.sleep(config['CHECK_INTERVAL'])

def terminal():
    while True:
        print("\nМеню:")
        print("1. Запуск Rejoin Tool")
        print("2. Добавить аккаунт")
        print("3. Настройки")
        print("4. Выход")
        choice = input("Выбор: ").strip()

        if choice == "1":
            for acc in config['accounts']:
                Thread(target=worker, args=(acc,), daemon=True).start()

        elif choice == "2":
            cookie = input("Введите .ROBLOSECURITY: ").strip()
            place_id = input("Введите placeId: ").strip()
            private = input("(Необязательно) Вставьте ссылку на приват сервер: ").strip()

            session = requests.Session()
            session.cookies['.ROBLOSECURITY'] = cookie
            session.headers.update({"Content-Type": "application/json"})
            session.headers['X-CSRF-TOKEN'] = get_csrf_token(session)
            user = get_user(session)

            if not user:
                print("[!] Ошибка получения пользователя")
                continue

            new_acc = {
                "id": user["id"],
                "name": user["name"],
                "displayName": user["displayName"],
                "Cookie": cookie,
                "PlaceId": place_id,
                "PrivatSr": private if private else None
            }
            config['accounts'].append(new_acc)
            save_config(config)
            print(f"[+] Аккаунт {user['name']} добавлен.")

        elif choice == "3":
            try:
                interval = int(input(f"Интервал проверки (текущий: {config['CHECK_INTERVAL']}): "))
                title = input(f"Кастомный префикс (текущий: {config['CUSTOM_TITLE']}): ")
                config['CHECK_INTERVAL'] = interval
                config['CUSTOM_TITLE'] = title
                save_config(config)
                print("[✓] Настройки сохранены")
            except:
                print("[!] Ошибка ввода")

        elif choice == "4":
            print("Выход...")
            os._exit(0)

        else:
            print("Неверный выбор.")

if __name__ == "__main__":
    terminal()
