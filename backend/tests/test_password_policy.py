"""Tests for backend/app/services/password_policy.py"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

import pytest
from app.services.password_policy import (
    PasswordPolicyError,
    check_password_strength,
    validate_password,
)


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


class TestCheckPasswordStrength:
    """Tests for check_password_strength returning strength analysis."""

    def test_weak_password(self):
        result = check_password_strength("abc")
        assert result["score"] <= 2
        assert result["strength"] in ("weak", "very_weak")
        assert result["valid"] is False

    def test_fair_password(self):
        result = check_password_strength("Abcdefghijkl")
        assert isinstance(result["score"], int)
        assert isinstance(result["strength"], str)

    def test_strong_password(self):
        result = check_password_strength("MyStr0ng!Pass")
        assert result["score"] >= 4
        assert result["valid"] is True

    def test_very_strong_password(self):
        result = check_password_strength("V3ry$ecure!Long#Pass2024")
        assert result["score"] >= 5
        assert result["strength"] in ("strong", "very_strong")
        assert result["valid"] is True

    def test_result_has_required_keys(self):
        result = check_password_strength("test")
        assert "strength" in result
        assert "score" in result
        assert "max_score" in result
        assert "errors" in result
        assert "valid" in result

    def test_valid_field_true(self):
        result = check_password_strength("MyStr0ng!Pass")
        assert result["valid"] is True

    def test_valid_field_false(self):
        result = check_password_strength("weak")
        assert result["valid"] is False

    def test_errors_list_for_invalid(self):
        result = check_password_strength("abc")
        assert isinstance(result["errors"], list)
        assert len(result["errors"]) > 0

    def test_feedback_field_present(self):
        result = check_password_strength("test")
        assert "feedback" in result


class TestPasswordPolicyError:
    """Tests for the PasswordPolicyError exception."""

    def test_exception_has_errors(self):
        err = PasswordPolicyError(errors=["Too short", "Missing digit"])
        assert hasattr(err, "errors")
        assert len(err.errors) == 2

    def test_exception_is_exception(self):
        err = PasswordPolicyError(errors=["test"])
        assert isinstance(err, Exception)

    def test_can_be_raised(self):
        with pytest.raises(PasswordPolicyError):
            raise PasswordPolicyError(errors=["Password too weak"])
