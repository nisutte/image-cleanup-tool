import logging
from rich.logging import RichHandler

def configure_logging(level: int = logging.INFO, enable_rich: bool = False) -> None:
    """
    Configure the root logger with a basic format.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[RichHandler(rich_tracebacks=True)]
    )

def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger (after logging is configured).
    """
    return logging.getLogger(name)
