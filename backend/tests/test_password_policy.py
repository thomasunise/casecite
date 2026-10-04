"""Tests for backend/app/services/password_policy.py"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

import pytest
from app.services.password_policy import validate_password


class TestValidatePassword:
    """Tests for validate_password returning error lists."""

    def test_valid_password_no_errors(self):
        errors = validate_password("MyStr0ng!Pass")
        assert errors == []

    def test_too_short(self):
        errors = validate_password("Abc1!")
        assert any("12" in e or "at least" in e.lower() for e in errors)

    def test_missing_uppercase(self):
        errors = validate_password("mystrongpass1!")
        assert len(errors) > 0
        assert any("upper" in e.lower() for e in errors)

    def test_missing_lowercase(self):
        errors = validate_password("MYSTRONGPASS1!")
        assert len(errors) > 0
        assert any("lower" in e.lower() for e in errors)

    def test_missing_digit(self):
        errors = validate_password("MyStrongPass!!")
        assert len(errors) > 0
        assert any("digit" in e.lower() or "number" in e.lower() for e in errors)

    def test_missing_special_char(self):
        errors = validate_password("MyStr0ngPasswd")
        assert len(errors) > 0
        assert any("special" in e.lower() or "character" in e.lower() for e in errors)

    def test_consecutive_identical_chars(self):
        errors = validate_password("MyStr0aaaaPass!")
        assert len(errors) > 0
        assert any("consecutive" in e.lower() or "repeat" in e.lower() for e in errors)

    def test_multiple_violations(self):
        errors = validate_password("abc")
        assert len(errors) >= 2

    def test_valid_long_password(self):
        errors = validate_password("C0mplex!Passw0rd#2024")
        assert errors == []

    def test_exactly_minimum_length(self):
        errors = validate_password("Abcdefgh1j!k")
        assert errors == []


class TestCommonPasswords:
    """Passwords that pass the complexity rules but are trivially guessable."""

    @pytest.mark.parametrize(
        "password",
        [
            "Password123!",
            "P@ssw0rd1234!",
            "Welcome2024!!",
            "Admin@123456",
            "WelcomeSummer2024!",
            "PasswordPassword1!",
            "1Password2024!",
        ],
    )
    def test_decorated_common_password_rejected(self, password):
        errors = validate_password(password)
        assert any("common" in e.lower() for e in errors), errors

    @pytest.mark.parametrize(
        "password",
        ["MyStr0ng!Pass", "Correct-Horse-Battery-9", "Tr0ub4dor&3xyz!", "S3cure-Passw0rd!"],
    )
    def test_uncommon_password_accepted(self, password):
        assert validate_password(password) == []
