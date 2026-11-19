"""MSK_core package initialization.

Delegates all environment detection and path resolution to Utils.env
(the single source of truth) and re-exports for backward compatibility.
"""
from .Utils.env import (
    is_frozen as _is_frozen,
    get_base_path,
    get_resource_path,
    init_exe_environment,
)

# Run environment init on package import (same behavior as before)
init_exe_environment()
