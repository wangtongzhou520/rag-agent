"""M1 认证纯函数测试。"""

from app.framework.exceptions import ClientException
from app.system.auth.jwt import decode_token, encode_token
from app.system.auth.password import hash_password, verify_password


def test_password_hash_round_trip() -> None:
    encoded = hash_password("correct horse")
    assert encoded != "correct horse"
    assert verify_password("correct horse", encoded)
    assert not verify_password("wrong", encoded)


def test_jwt_round_trip_and_signature_rejection() -> None:
    secret_a = "a" * 32
    secret_b = "b" * 32
    token, jti = encode_token(42, secret_a, 60)
    assert decode_token(token, secret_a) == (42, jti)
    try:
        decode_token(token, secret_b)
    except ClientException as exc:
        assert "未登录" in exc.message
    else:
        raise AssertionError("expected ClientException")
