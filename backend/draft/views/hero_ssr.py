from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny

from draft.models import HeroDraft
from draft.serializers.hero_ssr import HeroDraftSerializerSSR


class HeroDraftSSRView(RetrieveAPIView):
    serializer_class = HeroDraftSerializerSSR
    permission_classes = [AllowAny]
    queryset = HeroDraft.objects.select_related(
        "game__tournament__league__organization"
    ).prefetch_related("draft_teams__tournament_team")
