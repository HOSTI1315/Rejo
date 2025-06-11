import requests
import re
import subprocess
import urllib.parse
import time
import os
import json
import psutil
import win32event
import win32api
import winerror
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
        "accounts": [],
        "games": {}
    }

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

config = load_config()

def enable_multi_roblox():
    try:
        mutex = win32event.CreateMutex(None, True, "ROBLOX_singletonMutex")
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            print("⚠️ Roblox уже запущен. Закрой все клиенты перед активацией MultiRoblox.")
            return False
        print("✅ MultiRoblox активирован.")
        return True
    except Exception as e:
        print(f"❌ Не удалось активировать MultiRoblox: {e}")
        return False

def get_csrf_token(session):
    r = session.post("https://auth.roblox.com/v2/logout")
    return r.headers.get("x-csrf-token")

def get_user(session):
    r = session.get("https://users.roblox.com/v1/users/authenticated")
    return r.json() if r.ok else None

def get_ticket(session):
    # Adding the referer header matches the behaviour of the simple prototype
    # and prevents 403 errors when requesting an authentication ticket
    headers = {
        "Referer": "https://www.roblox.com/games/1/Any"
    }
    r = session.post("https://auth.roblox.com/v1/authentication-ticket/", headers=headers, json={})
    if r.status_code == 200:
        return r.headers.get("rbx-authentication-ticket")
    print(f"[!] Ошибка получения тикета: {r.status_code}")
    print(r.text)
    return None

def get_presence(session, uid):
    r = session.post("https://presence.roblox.com/v1/presence/users", json={"userIds": [uid]})
    return r.json()["userPresences"][0] if r.ok else None

def get_universe_id_from_place(place_id):
    try:
        r = requests.get(f"https://apis.roblox.com/universes/v1/places/{place_id}/universe")
        if r.ok:
            return r.json()["universeId"]
    except:
        pass
    return None

def extract_link_code(url):
    match = re.search(r"(?:code|privateServerLinkCode)=([a-zA-Z0-9]+)", url)
    return match.group(1) if match else None

def convert_share_link_to_legacy(url, place_id):
    code = extract_link_code(url)
    if code:
        return f"https://www.roblox.com/games/{place_id}/Game?privateServerLinkCode={code}"
    return None

def launch_roblox(ticket, place_id, username, private_url=None):
    timestamp = int(time.time() * 1000)
    launcher_url = (
        f"https://assetgame.roblox.com/game/PlaceLauncher.ashx?request=RequestGame"
        f"&browserTrackerId=1337&placeId={place_id}&isPlayTogetherGame=false"
    )

    if private_url:
        code = extract_link_code(private_url)
        if code:
            launcher_url += f"&linkCode={urllib.parse.quote(code)}"
        else:
            print(f"[!] Невалидная ссылка приватного сервера: {private_url}")
            return

    encoded_launcher = urllib.parse.quote(launcher_url, safe="")

    uri = (
        f"roblox-player:1+launchmode:play+gameinfo:{ticket}"
        f"+launchtime:{timestamp}"
        f"+placelauncherurl:{encoded_launcher}"
        f"+browsertrackerid:1337+robloxLocale:ru_ru+gameLocale:ru_ru"
    )

    title = f"{config['CUSTOM_TITLE']}{username}"
    print(f"[*] Запуск Roblox: {title}")
    subprocess.Popen(f'start \"{title}\" \"{uri}\"', shell=True)

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
        if pres and pres['userPresenceType'] == 2 and (
            str(pres.get('placeId')) == str(account['PlaceId']) or
            str(pres.get('universeId')) == str(account.get('UniverseId'))
        ):
            print(f"[✓] {account['name']} в нужной игре")
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
        print("3. Посмотреть аккаунты")
        print("4. Настройки")
        print("5. Выход")
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

            try:
                game_info = requests.get(f"https://games.roblox.com/v1/games?universeIds={user['id']}")
                data = game_info.json().get("data", [])
                if data:
                    config.setdefault("games", {})[place_id] = data[0]["name"]
            except:
                pass

            if not user:
                print("[!] Ошибка получения пользователя")
                continue

            new_acc = {
                    "id": user["id"],
                    "name": user["name"],
                    "displayName": user["displayName"],
                    "Cookie": cookie,
                    "PlaceId": place_id,
                    "UniverseId": get_universe_id_from_place(place_id),
                    "PrivatSr": convert_share_link_to_legacy(private, place_id) if private else None
                    }
            
            config['accounts'].append(new_acc)
            save_config(config)
            print(f"[+] Аккаунт {user['name']} добавлен.")

        elif choice == "3":
            print("==== Аккаунты ====")
            for i, acc in enumerate(config['accounts'], 1):
                name = acc['name']
                uid = acc['id']
                place = acc['PlaceId']
                game_name = config.get("games", {}).get(str(place), "❓ Unknown Game")
                private = acc.get("PrivatSr")
                private_mark = "✅" if private else "❌"

                print(f"{i}. {name}")
                print(f"| ID: {uid}")
                print(f"| PlaceId: {place}")
                print(f"| Name: {game_name}")
                print(f"| P.S: {private_mark}")
                print("--------------------")


        elif choice == "4":
            try:
                interval = int(input(f"Интервал проверки (текущий: {config['CHECK_INTERVAL']}): "))
                title = input(f"Кастомный префикс (текущий: {config['CUSTOM_TITLE']}): ")
                config['CHECK_INTERVAL'] = interval
                config['CUSTOM_TITLE'] = title
                save_config(config)
                print("[✓] Настройки сохранены")
            except:
                print("[!] Ошибка ввода")

        elif choice == "5":
            print("Выход...")
            os._exit(0)

        else:
            print("Неверный выбор.")

if __name__ == "__main__":
    enable_multi_roblox()
    terminal()
