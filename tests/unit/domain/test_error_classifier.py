"""ErrorClassifier domain service tests."""
from src.domain.services.error_classifier import ErrorClassifier
from src.domain.value_objects.publish_error import (
    PublishErrorType,
    RecoveryAction,
)


class TestErrorClassifier:
    def setup_method(self):
        self.classifier = ErrorClassifier()

    def test_quota_exceeded_detection(self):
        error = self.classifier.classify("최대 15개까지 발행 가능합니다")
        assert error.error_type == PublishErrorType.QUOTA_EXCEEDED
        assert error.recoverable is True
        assert error.action == RecoveryAction.AUTO_RESET

    def test_network_timeout_detection(self):
        error = self.classifier.classify("Connection timed out after 30s")
        assert error.error_type == PublishErrorType.NETWORK_TIMEOUT
        assert error.recoverable is True
        assert error.action == RecoveryAction.AUTO_RETRY

    def test_auth_failure_detection(self):
        error = self.classifier.classify("로그인 세션 만료")
        assert error.error_type == PublishErrorType.AUTH_FAILURE
        assert error.recoverable is False
        assert error.action == RecoveryAction.MANUAL

    def test_api_error_detection(self):
        error = self.classifier.classify("API error: 500 Internal Server Error")
        assert error.error_type == PublishErrorType.API_ERROR
        assert error.recoverable is True
        assert error.action == RecoveryAction.RETRY_THEN_MANUAL

    def test_validation_error_detection(self):
        error = self.classifier.classify("HTML 검증 실패: 본문 길이 부족")
        assert error.error_type == PublishErrorType.VALIDATION
        assert error.recoverable is False
        assert error.action == RecoveryAction.MARK_REVISION

    def test_unknown_error_detection(self):
        error = self.classifier.classify("Something completely unexpected happened")
        assert error.error_type == PublishErrorType.UNKNOWN
        assert error.recoverable is False
        assert error.action == RecoveryAction.MANUAL

    def test_empty_message(self):
        error = self.classifier.classify("")
        assert error.error_type == PublishErrorType.UNKNOWN
        assert error.original_message == ""

    def test_should_auto_recover_property(self):
        quota_err = self.classifier.classify("daily limit exceeded")
        assert quota_err.should_auto_recover is True

        auth_err = self.classifier.classify("login failed")
        assert auth_err.should_auto_recover is False
