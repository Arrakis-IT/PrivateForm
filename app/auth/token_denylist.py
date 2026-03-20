# =============================================================================
# PrivateForm - Token Denylist
# =============================================================================
# In-memory store for revoked JWT tokens.
# Entries are automatically cleaned up once the token's natural expiry passes.
# =============================================================================

# PrivateForm - Privacy-first medical forms
# Copyright (C) 2026 Juan Manuel SUÁREZ - Arrakis IT Services
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# See LICENSE file for full terms.

import time


class TokenDenylist:
    def __init__(self):
        # {token: exp_unix_timestamp}
        self._denied: dict[str, float] = {}

    def _clean_expired(self) -> None:
        """Removes tokens that have already expired (no longer a threat)."""
        now = time.time()
        self._denied = {t: exp for t, exp in self._denied.items() if exp > now}

    def add(self, token: str, exp: float) -> None:
        """Adds a token to the denylist until its expiry timestamp."""
        self._clean_expired()
        self._denied[token] = exp

    def is_denied(self, token: str) -> bool:
        """Returns True if the token has been explicitly revoked."""
        self._clean_expired()
        return token in self._denied


# Singleton — shared across all requests
denylist = TokenDenylist()
