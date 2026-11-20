"""Lightweight organization serializer and view for SSR meta tags."""

from rest_framework import serializers
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny

from org.models import Organization


class OrganizationSerializerSSR(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["pk", "name", "description", "logo"]


class OrganizationSSRView(RetrieveAPIView):
    serializer_class = OrganizationSerializerSSR
    permission_classes = [AllowAny]
    queryset = Organization.objects.all()
