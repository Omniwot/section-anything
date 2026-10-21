"""Browser bridge (from `section_anything.bridge`) and the app's registry of open bridges.

The registry is in memory and per process: run the API with one worker for browser runs.
"""

from section_anything.bridge import BROWSER_PREFIX, BridgeError, BridgeTimeout, BrowserBridge

__all__ = ["BRIDGES", "BROWSER_PREFIX", "BridgeError", "BridgeTimeout", "BrowserBridge"]

BRIDGES: dict[int, BrowserBridge] = {}  # run id -> bridge
