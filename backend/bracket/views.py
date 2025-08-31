from django.shortcuts import render

# Create your views here.
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from app.permissions import IsStaff

from .models import BracketSlot, TournamentBracket
from .serializers import BracketSlotSerializer, TournamentBracketSerializer


@permission_classes((IsStaff,))
class TournamentBracketView(viewsets.ModelViewSet):
    serializer_class = TournamentBracketSerializer
    queryset = TournamentBracket.objects.all()
    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "trace",
    ]

    @permission_classes((IsStaff,))
    def patch(self, request, *args, **kwargs):
        print(request.data)
        return self.partial_update(request, *args, **kwargs)

    def get_permissions(self):
        self.permission_classes = [IsStaff]
        if self.request.method == "GET":
            self.permission_classes = [AllowAny]
        return super(TournamentBracketView, self).get_permissions()


@permission_classes((IsStaff,))
class BracketSlotView(viewsets.ModelViewSet):
    serializer_class = BracketSlotSerializer
    queryset = BracketSlot.objects.all()
    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "trace",
    ]

    @permission_classes((IsStaff,))
    def patch(self, request, *args, **kwargs):
        print(request.data)
        return self.partial_update(request, *args, **kwargs)

    def get_permissions(self):
        self.permission_classes = [IsStaff]
        if self.request.method == "GET":
            self.permission_classes = [AllowAny]
        return super(BracketSlotView, self).get_permissions()
