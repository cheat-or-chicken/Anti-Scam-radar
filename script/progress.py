"""Structured progress without URLs, page content, credentials or SDK exception text."""

import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path

request_id = ContextVar("radar_request_id", default="-")
logger = logging.getLogger("radar.progress")


def configure_logging(path="var/backend.log"):
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch(mode=0o600, exist_ok=True)
    target.chmod(0o600)
    output = RotatingFileHandler(target, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    output.setFormatter(formatter)
    logger.addHandler(output)


def event(stage, status, *, elapsed_ms=None):
    suffix = "" if elapsed_ms is None else f" elapsed_ms={elapsed_ms}"
    logger.info("request=%s stage=%s status=%s%s", request_id.get(), stage, status, suffix)


@contextmanager
def phase(name):
    start = time.monotonic()
    event(name, "started")
    try:
        yield
    except BaseException:
        event(name, "failed", elapsed_ms=round((time.monotonic() - start) * 1000))
        raise
    else:
        event(name, "finished", elapsed_ms=round((time.monotonic() - start) * 1000))
