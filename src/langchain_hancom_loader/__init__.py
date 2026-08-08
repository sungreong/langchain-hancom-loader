"""LangChain-compatible loaders for documents converted by Hancom Data Loader."""

from importlib.metadata import PackageNotFoundError, version

from .loader import (
    HancomAPIError,
    HancomConversionError,
    HancomDataLoader,
    HancomDataLoaderError,
    HancomJobTimeoutError,
)

try:
    __version__ = version("langchain-hancom-loader")
except PackageNotFoundError:  # pragma: no cover - source tree without installation
    __version__ = "0+unknown"

__all__ = [
    "__version__",
    "HancomAPIError",
    "HancomConversionError",
    "HancomDataLoader",
    "HancomDataLoaderError",
    "HancomJobTimeoutError",
]
