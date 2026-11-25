from rest_framework import serializers

from app.models import Joke


class JokeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Joke
        fields = ["tangoes_purchased"]
        read_only_fields = ["tangoes_purchased"]
