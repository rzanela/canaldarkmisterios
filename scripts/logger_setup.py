"""
Logger configurado para o Canal Dark.
"""
import sys
from loguru import logger
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "dados" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
)
logger.add(
    LOG_DIR / "canal-dark-{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="30 days",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} | {message}"
)

def get_logger(name: str):
    return logger.bind(name=name)
