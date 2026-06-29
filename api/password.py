import hashlib
import secrets

from django.contrib.auth.hashers import check_password as django_check_password
from django.contrib.auth.hashers import make_password as django_make_password


def hash_device_password(raw_password):
    """Hash a device password using Django's password hashing framework.

    Uses PBKDF2 by default (same algorithm Django uses for user passwords).
    Each call generates a unique salt, so the same password produces
    different hashes every time.
    """
    if not raw_password:
        raise ValueError("Password cannot be empty")
    return django_make_password(raw_password)


def verify_device_password(raw_password, hashed_password):
    """Verify a device password against its hash.

    Supports both legacy plaintext passwords (for backward compatibility
    during migration) and hashed passwords. Legacy plaintext matches
    are automatically upgraded to hashed on successful verification.
    """
    if not raw_password or not hashed_password:
        return False, False

    if is_hashed(hashed_password):
        return django_check_password(raw_password, hashed_password), False

    is_valid = secrets.compare_digest(raw_password, hashed_password)
    return is_valid, is_valid


def is_hashed(password):
    """Check if a password is already hashed (vs legacy plaintext).

    Django hashed passwords follow the algorithm$salt$hash format.
    """
    if not password:
        return False
    return password.startswith(('pbkdf2_sha256$', 'pbkdf2_sha1$', 'argon2', 'bcrypt', 'scrypt'))
