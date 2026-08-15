"""QSC-Bench: quantum stability-contract benchmarking."""

from .config import BenchmarkConfig, load_config
from .runner import run_suite

__all__ = ["BenchmarkConfig", "load_config", "run_suite"]
__version__ = "1.0.0"
