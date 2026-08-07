import random
import time
import json
import os
import requests
from requests import Response
from bs4 import BeautifulSoup
from game import Game

MIN_ID = 1000000000
MAX_ID = 6000000000

GUARD = 50

def fetch_losses(limit: int, folder: str, guard: int = GUARD):
    l = 0 # limit tracker
    g = 0 # guard tracker

    attempted_ids = set()
    valid_game_ids = set()
    loss_ids = set()

    session = requests.Session()

    while (l < limit and g < guard):
        g += 1 # catch infinite loop

        game_id = random.randint(MIN_ID, MAX_ID)
        if game_id in attempted_ids: 
            continue
        attempted_ids.add(game_id)

        print(
            f"\rLosses: {l}/{limit} | "
            f"Attempts: {g} | "
            f"Valid: {len(valid_game_ids)} | "
            f"Current ID: {game_id}",
            end="",
            flush=True,
        )

        url = 'http://minesweeper.online/game/' + str(game_id)

        try:
            response = session.get(
                url,
                timeout = 10,
                headers = { "User-Agent": "Mozilla/5.0" }
            )
        except requests.RequestException:
            continue

        time.sleep(1.5)

        game = get_game(response)
        if game is None:
            continue
        valid_game_ids.add(game_id)

        if is_loss(game):
            download(game, url, folder)
            loss_ids.add(game_id)

            l += 1
    session.close()

    return attempted_ids, valid_game_ids, loss_ids

def get_game(res: Response) -> Game | None:
    if res.status_code != requests.codes.ok:
        print(f"\n[DEBUG] Bad status: {res.status_code} for {res.url}")
        return None
    
    soup = BeautifulSoup(res.text, "html.parser")
    area_block = soup.find("div", id="AreaBlock")
    if area_block is None:
        print(f"\n[DEBUG] No AreaBlock. Response length: {len(res.text)}")
        print(f"[DEBUG] Title: {soup.title.string if soup.title else 'none'}")
        print(f"[DEBUG] Snippet: {res.text[:300]}")
        return None
    
    cells = soup.find_all("div", class_="cell")
    if not cells:
        print(f"\n[DEBUG] AreaBlock found but no cells")
        return None

    max_x = 0
    max_y = 0

    for cell in cells:
        x = int(cell["data-x"])
        y = int(cell["data-y"])
        max_x = max(max_x, x)
        max_y = max(max_y, y)

    width = max_x + 1
    height = max_y + 1

    game = Game(width, height)
    for cell in cells:
        x = int(cell["data-x"])
        y = int(cell["data-y"])

        number = None
        opened = False
        mine = False
        flag = False
        incorrect = False

        if "hdd_type10" in cell.get("class", []):
            mine = True
        elif "hdd_flag" in cell.get("class", []):
            flag = True
        elif "hdd_type11" in cell.get("class", []):
            mine = True
            opened = True
            incorrect = True
        elif "hdd_type12" in cell.get("class", []):
            flag = True
            opened = True
            incorrect = True
        else:
            for cls in cell.get('class', []):
                if cls.startswith('hdd_type'):
                    value = cls.replace('hdd_type', '')
                    number = int(value)
                    opened = True
        game.add(x, y, number, opened, mine, flag, incorrect)

    return game

def is_loss(game: Game) -> bool:
    return game.loss_trigger() is not None

def download(game: Game, url: str, folder: str):
    os.makedirs(folder, exist_ok=True)

    game_id = url.rstrip("/").split("/")[-1]
    path = os.path.join(folder, f"{game_id}.json")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "id": game_id,
                "url": url,
                "game": game.to_dict()
            },
            f,
            indent=2
        )

if __name__ == "__main__":
    attempted_ids, valid_game_ids, loss_ids = fetch_losses(
        limit=5000,
        folder="losses",
    )

    print("\nFinished!")
    print(f"Attempted IDs : {len(attempted_ids):,}")
    print(f"Valid games   : {len(valid_game_ids):,}")
    print(f"Losses saved  : {len(loss_ids):,}")

    if attempted_ids:
        print(f"Validity rate : {len(valid_game_ids) / len(attempted_ids):.2%}")

    if valid_game_ids:
        print(f"Loss rate     : {len(loss_ids) / len(valid_game_ids):.2%}")
