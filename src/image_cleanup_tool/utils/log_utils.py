import logging

def configure_logging(level: int = logging.INFO) -> None:
    """
    Configure the root logger with a basic format.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger (after logging is configured).
    """
    return logging.getLogger(name)
