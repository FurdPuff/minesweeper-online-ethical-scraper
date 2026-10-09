# Minesweeper.online scraper

**created for educational purposes only**

The program scrapes minesweeper.online for minesweeper losses. Game data is outputted via JSON files in "losses" folder and can be read using read_json and read_game_data functions within game.py.

Credit to use the program is not required but is appreciated. I am not responsible for misuse of this software.

Using the program requires downloading Playwright: https://playwright.dev/python/docs/intro
To use, run
``python scrape.py [losses limit] [losses folder] [--retry-attempted]``
and log into minesweeper.online in the browser window. Return to the terminal
and press Enter to save the session before scraping starts. You can also
continue as a guest if login is not required. Add ``--retry-attempted`` to
recheck IDs from previous runs (except games already saved as loss JSON files).
