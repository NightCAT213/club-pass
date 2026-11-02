from app.security import make_pass, new_nonce, read_pass

KEY = "test-key-not-used-in-production-" * 3


def test_pass_roundtrip() -> None:
    nonce = new_nonce()
    payload = make_pass(nonce, KEY)
    assert read_pass(payload, KEY) == nonce
    assert "123456" not in payload


def test_forged_or_modified_pass_is_rejected() -> None:
    payload = make_pass(new_nonce(), KEY)
    chunks = payload.split(".")
    edited_nonce = ("A" if chunks[1][0] != "A" else "B") + chunks[1][1:]
    assert read_pass(f"bc1.{edited_nonce}.{chunks[2]}", KEY) is None
    assert read_pass(payload, "completely-different-key" * 3) is None
    assert read_pass(payload[:-1] + ("A" if payload[-1] != "A" else "B"), KEY) is None
    assert read_pass("bc1.123", KEY) is None
    assert read_pass("", KEY) is None
