"""
Password Policy Enforcement

Provides strong password validation for enterprise legal platform.
Requirements: 12+ characters, uppercase, lowercase, digit, special character,
and not a decorated variant of a commonly used password.
"""

import re

# Base words behind the passwords that satisfy "12+ chars, mixed classes" while
# being among the first things an attacker tries ("Password123!",
# "Welcome2024!!", "P@ssw0rd1234"). Compared against the password's
# de-leetspeaked letters, so decoration with digits/symbols does not help.
_COMMON_PASSWORD_WORDS = frozenset(
    {
        "password",
        "passwort",
        "passphrase",
        "welcome",
        "letmein",
        "changeme",
        "changeit",
        "qwerty",
        "qwertyuiop",
        "qwertyui",
        "asdfghjkl",
        "zxcvbnm",
        "admin",
        "administrator",
        "root",
        "login",
        "secret",
        "default",
        "temporary",
        "temppassword",
        "newpassword",
        "mypassword",
        "iloveyou",
        "sunshine",
        "princess",
        "football",
        "baseball",
        "basketball",
        "superman",
        "batman",
        "dragon",
        "monkey",
        "master",
        "shadow",
        "michael",
        "jennifer",
        "trustno",
        "starwars",
        "summer",
        "winter",
        "spring",
        "autumn",
        "january",
        "february",
        "october",
        "november",
        "december",
        "monday",
        "friday",
        "abc",
        "abcd",
        "abcdef",
        "abcdefgh",
        "test",
        "testing",
        "casecite",
        "lawyer",
        "attorney",
        "paralegal",
        "lawfirm",
        "legal",
        "company",
        "office",
    }
)

_LEET = str.maketrans(
    {"@": "a", "4": "a", "0": "o", "1": "l", "!": "i", "3": "e", "$": "s", "5": "s", "7": "t"}
)


def _is_common_password(password: str) -> bool:
    """True if the password is a common word (or two) dressed up to pass complexity."""
    # Trailing digits/symbols are decoration ("Password" + "123!"); strip them
    # before undoing leetspeak so "1234" is not read as letters.
    core = re.sub(r"^[^A-Za-z]+|[^A-Za-z]+$", "", password).lower().translate(_LEET)
    letters = re.sub(r"[^a-z]", "", core)
    if not letters:
        return True  # nothing but digits/symbols, e.g. "1234567890!@"
    if letters in _COMMON_PASSWORD_WORDS:
        return True
    # A common word repeated ("PasswordPassword1!") or two of them joined
    # ("WelcomeSummer2024!").
    for i in range(1, len(letters)):
        if letters[:i] in _COMMON_PASSWORD_WORDS and letters[i:] in _COMMON_PASSWORD_WORDS:
            return True
    return False


def validate_password(password: str) -> list[str]:
    """
    Validate password against policy. Returns list of errors (empty = valid).

    Policy:
    - Minimum 12 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    - No more than 3 consecutive identical characters
    - Not a commonly used password (or a decorated variant of one)
    """
    errors = []

    if len(password) < 12:
        errors.append("Password must be at least 12 characters")

    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter")

    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter")

    if not re.search(r"\d", password):
        errors.append("Password must contain at least one digit")

    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?`~]", password):
        errors.append("Password must contain at least one special character")

    if re.search(r"(.)\1{3,}", password):
        errors.append("Password must not contain more than 3 consecutive identical characters")

    if _is_common_password(password):
        errors.append("Password is too common; choose something less predictable")

    return errors
