from django.shortcuts import render


from rest_framework import viewsets
from dtx.serializers import UserSerializer, DiscordAuthSerializer
from .models import User
from django.shortcuts import render
from rest_framework import status
from rest_framework.response import Response
from rest_framework.generics import GenericAPIView
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
# Create your views here.

@permission_classes((AllowAny, ))
class UserView(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    queryset = User.objects.all()

    permission_classes =[IsAdminUser]



@permission_classes((AllowAny, ))
class DiscordSocialAuthView(GenericAPIView):
    serializer_class = DiscordAuthSerializer
    def post(self, request):
        """
        POST with "auth_token"
        Send an accesstoken as from discord to get user information
        """
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = ((serializer.validated_data)['auth_token'])
        return Response(data, status=status.HTTP_200_OK)