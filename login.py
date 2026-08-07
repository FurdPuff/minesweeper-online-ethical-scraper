# run to begin session

from playwright.sync_api import sync_playwright

AUTH_STATE_PATH = "auth.json"

def run_login():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://minesweeper.online/")

        print("Log into minesweeper.online, then press enter")

        context.storage_state(path=AUTH_STATE_PATH)
        print(f"Session saved to {AUTH_STATE_PATH}")

        browser.close()


if __name__ == "__main__":
    run_login()