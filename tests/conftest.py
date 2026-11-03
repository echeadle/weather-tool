"""Let tests import weather_tool without a real config.py (it's gitignored)."""

import sys
import types

try:
    import config  # noqa: F401
except ImportError:
    sys.modules["config"] = types.SimpleNamespace(
        HOME_LAT=0.0, HOME_LON=0.0, USER_AGENT_CONTACT="test@example.com"
    )
