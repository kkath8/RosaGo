"""Shared local policy for creating passwords; never applied to login."""
import re


PASSWORD_RULES = (
    dict(key='length', minimum=8, label='At least 8 characters',
         message='Password must be at least 8 characters.'),
    dict(key='uppercase', pattern='[A-Z]', label='At least one uppercase letter (A–Z)',
         message='Password must contain at least one uppercase letter.'),
    dict(key='lowercase', pattern='[a-z]', label='At least one lowercase letter (a–z)',
         message='Password must contain at least one lowercase letter.'),
    dict(key='number', pattern='[0-9]', label='At least one number (0–9)',
         message='Password must contain at least one number.'),
    # All printable ASCII punctuation; excludes whitespace, letters and digits.
    dict(key='special', pattern=r'[\x21-\x2f\x3a-\x40\x5b-\x60\x7b-\x7e]',
         label='At least one special character (e.g. ! @ # $ %)',
         message='Password must contain at least one special character.'),
)


def password_error(password):
    """Return the first unmet requirement, without changing the password."""
    for rule in PASSWORD_RULES:
        valid = (len(password) >= rule['minimum'] if 'minimum' in rule
                 else re.search(rule['pattern'], password) is not None)
        if not valid:
            return rule['message']
    return ''
