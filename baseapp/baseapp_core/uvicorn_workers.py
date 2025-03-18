from typing import Any, Dict

from uvicorn.workers import UvicornWorker as BaseUvicornWorker


class UvicornWorkerLifespanOff(BaseUvicornWorker):
    CONFIG_KWARGS: Dict[str, Any] = {"loop": "auto", "http": "auto", "lifespan": "off"}
