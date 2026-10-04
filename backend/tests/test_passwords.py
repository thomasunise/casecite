from app.services.passwords import hash_password, verify_password


def test_hash_password_format_and_verify_roundtrip():
    password = "S3cure-Passw0rd!"
    stored = hash_password(password)

    assert stored.startswith("pbkdf2_sha256$")
    assert verify_password(password, stored)


def test_verify_password_rejects_wrong_or_malformed_hash():
    stored = hash_password("correct-password")

    assert not verify_password("wrong-password", stored)
    assert not verify_password("anything", "not-a-valid-hash")
    assert not verify_password("", stored)
    assert not verify_password("password", None)
