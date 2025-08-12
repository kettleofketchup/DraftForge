from rest_framework import serializers

from .models import Match, PlayerMatchStats


class PlayerMatchStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlayerMatchStats
        exclude = ["match"]  # Exclude the direct link to the match to avoid redundancy


class MatchSerializer(serializers.ModelSerializer):
    players = PlayerMatchStatsSerializer(many=True, read_only=True)

    class Meta:
        model = Match
        fields = "__all__"
