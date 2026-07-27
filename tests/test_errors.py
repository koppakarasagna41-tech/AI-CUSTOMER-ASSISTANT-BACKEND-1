from app.core.exceptions import AppException


def test_api_error_serializes_consistently():
    error = AppException(message="bad request", error_code="BAD_REQUEST")

    assert error.error_code == "BAD_REQUEST"
    assert str(error) == "bad request"
