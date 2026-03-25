from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory


class InternalServiceAuthTest(TestCase):
    def test_valid_token_authenticates(self):
        from app.auth import InternalServiceAuth, InternalServiceUser

        factory = APIRequestFactory()
        request = factory.get("/", HTTP_X_INTERNAL_TOKEN="test-secret")
        with override_settings(INTERNAL_SERVICE_TOKEN="test-secret"):
            result = InternalServiceAuth().authenticate(request)
            self.assertIsNotNone(result)
            self.assertIsInstance(result[0], InternalServiceUser)
            self.assertTrue(result[0].is_authenticated)
            self.assertFalse(result[0].is_staff)
            self.assertEqual(result[0].pk, -1)

    def test_missing_token_returns_none(self):
        from app.auth import InternalServiceAuth

        factory = APIRequestFactory()
        request = factory.get("/")
        with override_settings(INTERNAL_SERVICE_TOKEN="test-secret"):
            self.assertIsNone(InternalServiceAuth().authenticate(request))

    def test_wrong_token_returns_none(self):
        from app.auth import InternalServiceAuth

        factory = APIRequestFactory()
        request = factory.get("/", HTTP_X_INTERNAL_TOKEN="wrong")
        with override_settings(INTERNAL_SERVICE_TOKEN="correct"):
            self.assertIsNone(InternalServiceAuth().authenticate(request))

    def test_empty_env_token_rejects_all(self):
        from app.auth import InternalServiceAuth

        factory = APIRequestFactory()
        request = factory.get("/", HTTP_X_INTERNAL_TOKEN="anything")
        with override_settings(INTERNAL_SERVICE_TOKEN=""):
            self.assertIsNone(InternalServiceAuth().authenticate(request))

    def test_token_with_whitespace_fails(self):
        from app.auth import InternalServiceAuth

        factory = APIRequestFactory()
        request = factory.get("/", HTTP_X_INTERNAL_TOKEN=" test-secret ")
        with override_settings(INTERNAL_SERVICE_TOKEN="test-secret"):
            self.assertIsNone(InternalServiceAuth().authenticate(request))


class IsInternalServiceTest(TestCase):
    def test_allows_internal_user(self):
        from app.auth import InternalServiceUser, IsInternalService

        class FakeRequest:
            user = InternalServiceUser()

        self.assertTrue(IsInternalService().has_permission(FakeRequest(), None))

    def test_rejects_regular_user(self):
        from app.auth import IsInternalService

        class FakeRequest:
            class user:
                is_authenticated = True

        self.assertFalse(IsInternalService().has_permission(FakeRequest(), None))

    def test_rejects_staff_user(self):
        """Staff users should NOT pass IsInternalService — service tokens only."""
        from app.auth import IsInternalService

        class FakeRequest:
            class user:
                is_authenticated = True
                is_staff = True

        self.assertFalse(IsInternalService().has_permission(FakeRequest(), None))
