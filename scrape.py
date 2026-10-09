import argparse
import random
import time
import json
import os
import sys
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import (
    sync_playwright,
    Page,
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
)
from game import Game
from login import run_login

MIN_ID = 1_000_000_000
MAX_ID = 6_000_000_000

GUARD = 10_000_000

AUTH_STATE_PATH = "auth.json"
NAV_TIMEOUT_MS = 8_000
CELL_WAIT_TIMEOUT_MS = 8_000
DELAY_SECONDS = 1.5

def fetch_losses(limit: int, folder: str, guard: int = GUARD,
                  auth_state: str = AUTH_STATE_PATH,
                  retry_attempted: bool = False) -> tuple[set[int], set[int], set[int]]:
    """downloads player losses from minesweeper.online

    Args:
        limit (int): desired/maximum amount of losses stored
        folder (str): losses folder path
        guard (int, optional): _description_. Defaults to GUARD.
        auth_state (str, optional): authorization path. Defaults to AUTH_STATE_PATH.

    Returns:
        tuple[set[int], set[int], set[int]]: attempted game ids, valid game ids, loss ids
    """
    l = 0  # limit tracker
    g = 0  # guard tracker

    os.makedirs(folder, exist_ok=True)
    attempted_ids_path = "attempted_ids.txt"

    loss_file_ids = {int(file.stem) for file in Path(folder).glob("*.json")}
    attempted_file_ids = load_attempted_ids(attempted_ids_path)
    attempted_ids = loss_file_ids | attempted_file_ids
    retry_ids = iter(sorted(attempted_file_ids - loss_file_ids))

    valid_game_ids = set()
    loss_ids = set()
    page_load_failures = 0
    pages_checked = 0
    unrecognized_pages = 0
    parse_failures: dict[str, int] = {}

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

        auth_status = page.evaluate(
            """() => ({
                sessionLoaded: Boolean(window.localStorage.getItem('_session')),
                authenticatedUi: Boolean(document.querySelector('.auth-required:not(.hide)')),
                guestUi: Boolean(document.querySelector('.auth-free:not(.hide)')),
            })"""
        )
        session_loaded = auth_status["sessionLoaded"]
        if has_auth and not session_loaded:
            print(
                f"\n[warning] '{auth_state}' did not load a Minesweeper session. "
                "Log in again and press Enter after the site shows your account."
            )
        else:
            print(
                "\n[info] Authentication status: "
                f"session token loaded={session_loaded}, "
                f"account UI visible={auth_status['authenticatedUi']}, "
                f"guest login UI visible={auth_status['guestUi']}."
            )

        if loss_file_ids:
            reference_id = max(loss_file_ids)
            reference_url = f"https://minesweeper.online/game/{reference_id}"
            time.sleep(DELAY_SECONDS)
            reference_html = load_game_page(page, reference_url)
            if reference_html is None:
                print(
                    f"[diagnostic] Could not load previously saved game {reference_id}; "
                    f"final_url={page.url!r}"
                )
            else:
                reference_game, reference_error = parse_game(reference_html)
                if reference_game is None:
                    print(
                        f"[diagnostic] Previously saved game {reference_id} "
                        f"did not parse ({reference_error}); "
                        f"title={page.title()!r}, final_url={page.url!r}, "
                        f"{describe_game_page(reference_html)}"
                    )
                else:
                    print(
                        f"[diagnostic] Previously saved game {reference_id} parsed "
                        f"successfully ({reference_game.width}x{reference_game.height})."
                    )
            time.sleep(DELAY_SECONDS)

        try:
            last_request_time = time.perf_counter() - DELAY_SECONDS

            while l < limit and g < guard:
                g += 1  # catch infinite loop

                game_id = next(retry_ids, None) if retry_attempted else None
                if game_id is None:
                    game_id = random.randint(MIN_ID, MAX_ID)
                    if game_id in attempted_ids:
                        continue

                print(
                    f"\rLosses: {l}/{limit} | "
                    f"Attempts: {g} | "
                    f"Valid: {len(valid_game_ids)} | "
                    f"Current ID: {game_id}",
                    end="",
                    flush=True,
                )

                url = f"https://minesweeper.online/game/{game_id}"

                elapsed = time.perf_counter() - last_request_time
                remaining = DELAY_SECONDS - elapsed
                if remaining > 0:
                    time.sleep(remaining)
                last_request_time = time.perf_counter()

                html = load_game_page(page, url)

                if html is None:
                    page_load_failures += 1
                    continue

                pages_checked += 1
                attempted_ids.add(game_id)
                attempted_ids_file.write(f"{game_id}\n")
                attempted_ids_file.flush()

                game, parse_error = parse_game(html)
                if game is None:
                    unrecognized_pages += 1
                    assert parse_error is not None
                    parse_failures[parse_error] = parse_failures.get(parse_error, 0) + 1
                    if unrecognized_pages <= 3:
                        print(
                            f"\n[diagnostic] Game {game_id} was not recognized "
                            f"({parse_error}); title={page.title()!r}, "
                            f"final_url={page.url!r}, "
                            f"{describe_game_page(html)}"
                        )
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

    print(f"\nPage load failures (eligible for retry): {page_load_failures:,}")
    print(f"Pages checked this run: {pages_checked:,}")
    print(f"Pages without a recognized game board: {unrecognized_pages:,}")
    if parse_failures:
        print("Parser rejection reasons:")
        for reason, count in sorted(parse_failures.items()):
            print(f"  {reason}: {count:,}")
    if pages_checked:
        print(f"Validity rate this run: {len(valid_game_ids) / pages_checked:.2%}")

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
                    continue
    return ids

def load_game_page(page: Page, url: str) -> str | None:
    try:
        page.goto(url, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
    except PlaywrightTimeoutError:
        print(
            f"\n[warning] Navigation timed out for {url}; checking the loaded page.",
            file=sys.stderr,
        )
    except PlaywrightError as exc:
        print(f"\n[warning] Could not load {url}: {exc}", file=sys.stderr)
        return None

    try:
        page.wait_for_selector(".cell", timeout=CELL_WAIT_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        pass

    time.sleep(0.3) # settle time
    try:
        return page.content()
    except PlaywrightError as exc:
        print(f"\n[warning] Could not read page content for {url}: {exc}", file=sys.stderr)
        return None

def parse_game(html: str) -> tuple[Game | None, str | None]:
    """Parse a game and return a rejection reason when the page has no board."""
    soup = BeautifulSoup(html, "html.parser")

    cells = soup.find_all(class_="cell")
    if not cells:
        return None, "no .cell elements"

    max_x = 0
    max_y = 0

    for cell in cells:
        try:
            x = int(cell["data-x"])
            y = int(cell["data-y"])
        except (KeyError, TypeError, ValueError):
            return None, "board cell has missing or invalid coordinates"
        max_x = max(max_x, x)
        max_y = max(max_y, y)

    width = max_x + 1
    height = max_y + 1

    minecount = 0
    for i in range(3):
        zeros = "0" * i
        mines_div = soup.find(id=f"top_area_mines_1{zeros}")
        if mines_div is None:
            return None, f"missing mine counter #top_area_mines_1{zeros}"
        for cls in mines_div.get("class", []):
            if cls.startswith("hd_top-area-num"):
                try:
                    value = int(cls.removeprefix("hd_top-area-num"))
                except ValueError:
                    continue
                if 0 <= value <= 9:
                    minecount += value * 10 ** i
                break

    game = Game(width, height, minecount)

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

    return game, None


def get_game(html: str) -> Game | None:
    """Returns game given minesweeper.online html and returns None if invalid."""
    game, _ = parse_game(html)
    return game


def describe_game_page(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    counter_ids = ("top_area_mines_1", "top_area_mines_10", "top_area_mines_100")
    counters = [counter_id for counter_id in counter_ids if soup.find(id=counter_id)]
    cells = soup.find_all(class_="cell")
    return (
        f"cells={len(cells)}, mine counters={counters}"
    )

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
    parser = argparse.ArgumentParser(description="Find and save Minesweeper loss games.")
    parser.add_argument("limit", nargs="?", type=int, default=100, help="number of losses to save")
    parser.add_argument("folder", nargs="?", default="losses", help="folder for saved loss games")
    parser.add_argument(
        "--retry-attempted",
        action="store_true",
        help="recheck previously attempted IDs that do not already have saved loss files",
    )
    args = parser.parse_args()

    run_login()

    attempted_ids, valid_game_ids, loss_ids = fetch_losses(
        limit=args.limit,
        folder=args.folder,
        retry_attempted=args.retry_attempted,
    )

    print("\nFinished!")
    print(f"Attempted IDs (cached): {len(attempted_ids):,}")
    print(f"Valid games this run : {len(valid_game_ids):,}")
    print(f"Losses saved this run: {len(loss_ids):,}")

    if valid_game_ids:
        print(f"Loss rate this run   : {len(loss_ids) / len(valid_game_ids):.2%}")
