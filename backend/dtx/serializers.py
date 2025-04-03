from rest_framework import serializers
from .models import User
from rest_framework import serializers
from dtx.lib import discord
from dtx.lib.register import register_social_user
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('name', 'steamid', 'mmr', )
        

class DiscordAuthSerializer(serializers.Serializer):
    """Handles serialization of discord related data"""
    auth_token = serializers.CharField()
    def validate_auth_token(self, auth_token):
        user_data =  discord.Discord.validate(auth_token)
        try:
            email = user_data['email']
            provider = 'discord'
        except:
            raise serializers.ValidationError(
                'The token  is invalid or expired. Please login again.'
            )
        return register_social_user(
            provider=provider, user_id=None, email=email, name=None)