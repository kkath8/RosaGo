"""Bounded, authenticated per-record codec; no environment or network access."""
import base64
from dataclasses import asdict, is_dataclass
import json
import re
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from session_realms import SessionStorageUnavailable
from normal_auth_store import NormalAuthSession, RefreshReservation
from recovery_helpers import PendingRecovery, RecoveryGrant
from email_verification import PendingEmail


TYPES = {t.__name__: t for t in (NormalAuthSession, RefreshReservation,
         PendingRecovery, RecoveryGrant, PendingEmail)}


def pack(value):
    if is_dataclass(value):
        return {'type': type(value).__name__, 'value': pack(asdict(value))}
    if isinstance(value, dict):
        return {'dict': [[pack(k), pack(v)] for k, v in value.items()]}
    if isinstance(value, tuple):
        return {'tuple': [pack(v) for v in value]}
    if isinstance(value, list):
        return [pack(v) for v in value]
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise ValueError('Unsupported session value.')


def unpack(value):
    if isinstance(value, list):
        return [unpack(v) for v in value]
    if isinstance(value, dict):
        if set(value) == {'dict'}:
            return {unpack(k): unpack(v) for k, v in value['dict']}
        if set(value) == {'tuple'}:
            return tuple(unpack(v) for v in value['tuple'])
        if set(value) == {'type', 'value'} and value['type'] in TYPES:
            return TYPES[value['type']](**unpack(value['value']))
        raise ValueError('Invalid session document.')
    return value


class SessionCipher:
    def __init__(self, keyring, current):
        if current not in keyring or not keyring:
            raise ValueError('Invalid session keyring.')
        if any(not re.fullmatch(r'[a-zA-Z0-9_-]{1,32}', k) or len(v) != 32
               for k, v in keyring.items()):
            raise ValueError('Invalid session keyring.')
        self.keys = {k: AESGCM(v) for k, v in keyring.items()}
        self.current = current

    def encrypt(self, value, aad):
        try:
            plain = json.dumps(pack(value), separators=(',', ':'), allow_nan=False).encode()
        except (ValueError, TypeError, RecursionError):
            raise SessionStorageUnavailable('Unsupported or oversized session state.') from None
        if len(plain) > 32768:
            raise SessionStorageUnavailable('Session capacity exceeded.')
        nonce = secrets.token_bytes(12)
        key = self.current.encode()
        return key + b'.' + base64.urlsafe_b64encode(nonce + self.keys[self.current].encrypt(nonce, plain, aad + b':' + key))

    def decrypt(self, value, aad):
        try:
            if len(value) > 45000:
                raise ValueError('Oversized session ciphertext.')
            key, encoded = value.split(b'.', 1)
            data = base64.b64decode(encoded, altchars=b'-_', validate=True)
            plain = self.keys[key.decode()].decrypt(data[:12], data[12:], aad + b':' + key)
            return unpack(json.loads(plain))
        except Exception:
            raise SessionStorageUnavailable('Invalid encrypted session state.') from None


