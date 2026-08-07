# Minesweeper.online scraper

**created for educational purposes only**

The program scrapes minesweeper.online for lost games from players. Game data is outputted via JSON in "losses" folder and can be read using from_dict function in game class. 

Credit to use the program is not required but is appreciated. I am not responsible for misuse of this software.

Using the program requires downloading Playwright: https://playwright.dev/python/docs/intro
To use, run
``python scrape.py [losses limit] [losses folder]``
and login if prompted, or simply login as a guest
