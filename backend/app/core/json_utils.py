"""Shared JSON utilities — numpy-safe serialization."""
from __future__ import annotations

import json
from typing import Any


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that converts numpy scalars to native Python types."""

    def default(self, obj: Any) -> Any:
        try:
            import numpy as np
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.bool_):
                return bool(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
        except ImportError:
            pass
        return super().default(obj)


def safe_json_dumps(obj: Any, **kwargs: Any) -> str:
    """json.dumps with numpy scalar support."""
    return json.dumps(obj, cls=NumpyEncoder, **kwargs)
