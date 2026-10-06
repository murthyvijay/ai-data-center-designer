"""Silicon-to-Data-Hall deterministic compiler for AI data center designs."""

from .catalog import load_catalog
from .compiler import compile_design
from .schema import DesignSpec

__all__ = ["DesignSpec", "compile_design", "load_catalog"]
__version__ = "0.1.0"
