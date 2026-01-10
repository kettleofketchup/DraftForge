from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class LeagueConfig(BaseModel):
    id: int
    name: str
    default: bool = False


class AppConfig(BaseSettings):
    leagues: list[LeagueConfig] = []

    @classmethod
    def from_yaml(cls, path: Path) -> "AppConfig":
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)

    @property
    def default_league_id(self) -> int | None:
        for league in self.leagues:
            if league.default:
                return league.id
        return self.leagues[0].id if self.leagues else None

    @property
    def league_choices(self) -> list[tuple[int, str]]:
        return [(league.id, league.name) for league in self.leagues]


# Load configuration at module level
CONFIG_PATH = Path(__file__).parent / "leagues.yaml"
app_config = AppConfig.from_yaml(CONFIG_PATH)
