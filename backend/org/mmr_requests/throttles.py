from django.conf import settings
from rest_framework.request import Request
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView


class MmrRequestCreateThrottle(UserRateThrottle):
    scope = "mmr_request_create"
    rate = "10/hour"

    def allow_request(self, request: Request, view: APIView) -> bool:
        if getattr(settings, "TEST", False) and not getattr(
            settings, "MMR_THROTTLE_IN_TESTS", False
        ):
            return True
        return super().allow_request(request, view)
