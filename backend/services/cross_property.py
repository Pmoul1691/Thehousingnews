"""Cross-property bridge to ultradianpartners.com for auto-grant on sign-in."""
import os
import logging
import requests

logger = logging.getLogger(__name__)

BRIDGE_URL = os.environ.get("PARTNERS_BRIDGE_URL", "https://www.ultradianpartners.com/api/network/user-status")
NETWORK_API_KEY = os.environ.get("NETWORK_API_KEY", "")


def get_user_status(email: str) -> dict:
    """Call the partners bridge. Returns the response dict or empty dict on failure."""
    if not NETWORK_API_KEY:
        return {}
    try:
        r = requests.get(
            BRIDGE_URL,
            params={"email": email},
            headers={"X-Network-Api-Key": NETWORK_API_KEY},
            timeout=10,
        )
        if r.status_code != 200:
            logger.info("Partners bridge non-200 for %s: %s", email, r.status_code)
            return {}
        return r.json()
    except Exception as e:
        logger.warning("Partners bridge call failed: %s", e)
        return {}
