import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "logs/app.log"


class ModelConfig(BaseModel):
    openai_chat: str = "gpt-4o-mini"
    openai_fallback: str = "gpt-4o-mini"


class DefaultsConfig(BaseModel):
    news_feed: str = "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"
    max_news: int = 10
    default_stock_suffix: str = ".NS"


class AppConfig(BaseModel):
    env: str = "dev"
    logging: LoggingConfig = LoggingConfig()
    models: ModelConfig = ModelConfig()
    defaults: DefaultsConfig = DefaultsConfig()


class Settings(BaseModel):
    openai_api_key: str
    config: AppConfig
    config_path: Path


def _load_yaml_config(config_path: Path) -> AppConfig:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found at {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    try:
        return AppConfig(**raw)
    except ValidationError as exc:
        raise RuntimeError(f"Invalid config file: {exc}") from exc


def _load_openai_key() -> str:
    load_dotenv()
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise EnvironmentError("OPENAI_API_KEY missing. Set it in .env or environment.")
    return key.strip()


@lru_cache(maxsize=1)
def get_settings(config_path: Optional[str] = None) -> Settings:
    path = Path(config_path or "app/config/config.yaml")
    app_config = _load_yaml_config(path)
    openai_key = _load_openai_key()
    return Settings(openai_api_key=openai_key, config=app_config, config_path=path)


def configure_logging(logging_config: LoggingConfig) -> None:
    log_path = Path(logging_config.file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, logging_config.level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )
