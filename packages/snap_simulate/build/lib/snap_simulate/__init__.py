try:
    import gsd
except ImportError as e:
    raise ImportError(
        "The 'gsd' package is required but could not be found. "
        "Please install it via Conda before using this package: "
        "conda install -c conda-forge gsd"
    ) from e

from . import system
from . import hoomd
