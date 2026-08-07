import json
from dataclasses import dataclass

@dataclass
class Cell:
    x: int
    y: int
    number: int | None = None
    opened: bool = False
    mine: bool = False
    flag: bool = False
    incorrect: bool = False

    def to_dict(self) -> dict:
            return vars(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Cell":
        return cls(**data)

class Game:
    def __init__(self, width: int, height: int, minecount: int):
        self.width = width
        self.height = height
        self.minecount = minecount
        self.grid = [[Cell(x, y) for x in range(width)] for y in range(height)]

    def out_of_bounds(self, x: int, y: int) -> bool:
        return x < 0 or x >= self.width or y < 0 or y >= self.height

    def at(self, x: int, y: int) -> Cell | None:
        if self.out_of_bounds(x,y):
            return None
        return self.grid[y][x]

    def add(self, x: int, y: int, number: int | None, opened: bool,
            mine: bool, flag: bool, incorrect: bool):
        if self.out_of_bounds(x, y):
            return
        self.grid[y][x] = Cell(x, y, number, opened, mine, flag, incorrect)

    def loss_trigger(self) -> Cell | None:
        for y in range(self.height):
            for x in range(self.width):
                cur = self.grid[y][x]
                if cur.incorrect and cur.mine:
                    return cur
        return None

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "minecount": self.minecount,
            "grid": [[cell.to_dict() for cell in row] for row in self.grid]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Game":
        game = cls(
            width=data["width"], 
            height=data["height"],
            minecount=data["minecount"]
        )
        game.grid = [
            [Cell.from_dict(cell_data) for cell_data in row]
            for row in data["grid"]
        ]
        return game

def read_json(path: str):
    """reads in game json returns game id, game url, and game"""
    with open(path) as f:
        return read_game_data(json.load(f))

def read_game_data(data: dict) -> tuple[int | None, str, Game]:
    """reads in game data and returns game id, game url, and game"""
    game = Game.from_dict(data["game"])

    try:
        game_id = int(data["id"])
    except (KeyError, ValueError, TypeError):
        game_id = None
    
    return game_id, data["url"], game
