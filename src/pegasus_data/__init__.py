"""pegasus_data — a queryable, self-describing data lake over DATASUS."""

from .config import Settings, load_settings

__version__ = "0.1.0"
__all__ = ["Settings", "load_settings", "__version__"]
