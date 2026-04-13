"""Helpers for authenticating admin and scheduler-triggered API requests."""
from __future__ import annotations


def is_authorized_admin_request(
    expected_secret: str,
    *,
    header_secret: str | None = None,
    authorization: str | None = None,
    query_secret: str | None = None,
) -> bool:
    """Return True when any supported admin credential matches the expected secret."""
    if not expected_secret:
        return False

    if header_secret == expected_secret:
        return True

    if query_secret == expected_secret:
        return True

    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token == expected_secret:
            return True

    return False