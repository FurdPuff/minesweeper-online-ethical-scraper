import random
import time
import json
import os
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError
from game import Game

MIN_ID = 1_000_000_000
MAX_ID = 6_000_000_000

GUARD = 10_000_000

AUTH_STATE_PATH = "auth.json"
NAV_TIMEOUT_MS = 8_000
CELL_WAIT_TIMEOUT_MS = 8_000
DELAY_SECONDS = 1.5

def fetch_losses(limit: int, folder: str, guard: int = GUARD,
                  auth_state: str = AUTH_STATE_PATH):
    l = 0  # limit tracker
    g = 0  # guard tracker

    os.makedirs(folder, exist_ok=True)
    attempted_ids_path = os.path.join(folder, "attempted_ids.txt")

    loss_file_ids = {int(file.stem) for file in Path(folder).glob("*.json")}
    attempted_file_ids = load_attempted_ids(attempted_ids_path)
    attempted_ids = loss_file_ids | attempted_file_ids

    valid_game_ids = set()
    loss_ids = set()

    has_auth = os.path.exists(auth_state)
    if not has_auth:
        print(
            f"[warning] No saved session found at '{auth_state}'. "
            f"Proceeding as an anonymous/guest session.\n"
            f"          If every game comes back invalid, run `python login.py` "
            f"first and re-run this script.\n"
        )

    with sync_playwright() as p, open(attempted_ids_path, "a", encoding="utf-8") as attempted_ids_file:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=auth_state if has_auth else None,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        try:
            page.goto("https://minesweeper.online/", timeout=NAV_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            pass

        try:
            # Allow the very first request to fire immediately.
            last_request_time = time.perf_counter() - DELAY_SECONDS

            while l < limit and g < guard:
                g += 1  # catch infinite loop

                game_id = random.randint(MIN_ID, MAX_ID)
                if game_id in attempted_ids:
                    continue
                attempted_ids.add(game_id)
                attempted_ids_file.write(f"{game_id}\n")
                attempted_ids_file.flush()

                print(
                    f"\rLosses: {l}/{limit} | "
                    f"Attempts: {g} | "
                    f"Valid: {len(valid_game_ids)} | "
                    f"Current ID: {game_id}",
                    end="",
                    flush=True,
                )

                url = f"https://minesweeper.online/game/{game_id}"

                # Minimum-interval throttle, no busy-wait: sleep only for
                # whatever time is still owed since the last request. If the
                # previous iteration's network/parsing work already ate up
                # more than DELAY_SECONDS, this is a no-op -- the loop
                # always keeps moving, it just never fires requests to the
                # site faster than DELAY_SECONDS apart.
                elapsed = time.perf_counter() - last_request_time
                remaining = DELAY_SECONDS - elapsed
                if remaining > 0:
                    time.sleep(remaining)
                last_request_time = time.perf_counter()

                html = load_game_page(page, url)

                if html is None:
                    continue

                game = get_game(html)
                if game is None:
                    continue
                valid_game_ids.add(game_id)

                if not is_loss(game):
                    continue

                download(game, url, folder)
                loss_ids.add(game_id)
                l += 1

        finally:
            context.close()
            browser.close()

    return attempted_ids, valid_game_ids, loss_ids


def load_attempted_ids(path: str) -> set[int]:
    if not os.path.exists(path):
        return set()
    ids = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    ids.add(int(line))
                except ValueError:
                    continue  # skip any corrupted/partial line
    return ids

def load_game_page(page: Page, url: str) -> str | None:
    try:
        page.goto(url, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
    except PlaywrightTimeoutError:
        return None
    except Exception:
        return None

    try:
        page.wait_for_selector(".cell", timeout=CELL_WAIT_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        return None

    time.sleep(0.3) # settle time
    return page.content()

def get_game(html: str) -> Game | None:
    soup = BeautifulSoup(html, "html.parser")

    area_block = soup.find("div", id="AreaBlock")
    if area_block is None:
        return None

    cells = soup.find_all("div", class_="cell")
    if not cells:
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

        classes = cell.get("class", [])

        opened = "hd_opened" in classes
        mine = "hd_type10" in classes or "hd_type11" in classes
        flag = "hd_flag" in classes or "hd_type12" in classes
        incorrect = "hd_type11" in classes or "hd_type12" in classes

        for cls in classes:
            if cls.startswith("hd_type"):
                value = int(cls.replace("hd_type", ""))
                if 0 <= value <= 8:
                    number = value
                    opened = True
                break

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
