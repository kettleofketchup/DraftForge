from typing import Any

from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.views import APIView

from org.api_tokens.auth import OrgApiTokenAuthentication
from org.integration.errors import integration_exception_handler
from org.integration.parsers import IntegrationJSONParser


class IntegrationAPIView(APIView):
    """Base for integration routes: bearer app tokens only, strict JSON in,
    contract failure envelope out.

    No session, Discord Activity or internal-service authentication is
    accepted. Handlers still call ``gate_token_request`` with their operation
    and read POST bodies through ``parsers.json_body``.
    """

    authentication_classes = [OrgApiTokenAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [IntegrationJSONParser]
    renderer_classes = [JSONRenderer]

    def get_exception_handler(self) -> Any:
        return integration_exception_handler
