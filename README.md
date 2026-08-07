# Minesweeper.online scraper

**created for educational purposes only**

The program scrapes minesweeper.online for minesweeper losses. Game data is outputted via JSON files in "losses" folder and can be read using read_json and read_game_data functions within game.py.

Credit to use the program is not required but is appreciated. I am not responsible for misuse of this software.

Using the program requires downloading Playwright: https://playwright.dev/python/docs/intro
To use, run
``python scrape.py [losses limit] [losses folder]``
and login if prompted, or simply login as a guest
