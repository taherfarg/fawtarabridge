"""Webhook signature scheme: HMAC-SHA256 over the raw body, hex in X-ASP-Signature.

# SPEC-CHECK: real ASPs bring their own signing scheme (often HMAC or mTLS);
# this module is the single place to adapt when the sandbox docs arrive.
"""

import hashlib
import hmac


def compute_signature(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    return hmac.compare_digest(compute_signature(secret, body), signature)
