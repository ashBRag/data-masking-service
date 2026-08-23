"""JWT verification helper, decoupled from any specific settings object.

Takes the secret/algorithm as arguments instead of importing app config
directly, so it can be reused as-is in another project.
"""

import jwt


def verify_token(token: str, secret_key: str, algorithm: str = "HS256") -> dict | None:
    """Decode and verify a JWT, returning its payload.

    Args:
        token: The raw bearer token (without the "Bearer " prefix).
        secret_key: Shared secret used to sign/verify the token.
        algorithm: JWT signing algorithm (must match how the token was issued).

    Raises:
        ValueError: If `token` isn't a non-empty string (a caller bug, not an
            untrusted-input problem - malformed/expired/invalid *tokens* are
            handled by returning None, not raising).

    Returns:
        The decoded claims dict, or None if the token is invalid/expired/tampered.
    """
    if not token or not isinstance(token, str):
        raise ValueError("Token must be a non-empty string")

    try:
        return jwt.decode(token, secret_key, algorithms=[algorithm])
    except jwt.PyJWTError:
        return None
