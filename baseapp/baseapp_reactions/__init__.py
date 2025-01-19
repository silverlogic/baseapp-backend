import warnings

from baseapp.reactions import *  # noqa

warnings.warn(
    "Importing from baseapp_reactions is deprecated. Use baseapp.reactions instead.",
    DeprecationWarning,
    stacklevel=2,
)
