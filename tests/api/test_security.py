from tradingagents.api.security import (
    generate_csrf_token,
    generate_session_id,
    hash_password,
    verify_password,
)


def test_hash_password_roundtrip():
    h = hash_password("correct horse battery")
    assert h.startswith("scrypt$")
    assert verify_password("correct horse battery", h) is True
    assert verify_password("wrong", h) is False


def test_hash_password_uses_unique_salt():
    a = hash_password("same")
    b = hash_password("same")
    assert a != b
    assert verify_password("same", a)
    assert verify_password("same", b)


def test_verify_password_rejects_garbage():
    assert verify_password("anything", "") is False
    assert verify_password("anything", "not-a-real-hash") is False
    assert verify_password("anything", "scrypt$bad$format") is False


def test_session_and_csrf_tokens_have_expected_prefix_and_entropy():
    sid = generate_session_id()
    csrf = generate_csrf_token()
    assert sid.startswith("sid_")
    assert len(sid) >= 36
    assert len(csrf) >= 32
    assert sid != generate_session_id()
    assert csrf != generate_csrf_token()
