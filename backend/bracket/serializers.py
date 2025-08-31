from rest_framework import serializers

from .models import BracketSlot, TournamentBracket


class BracketSlotSerializer(serializers.ModelSerializer):

    class Meta:
        model = BracketSlot
        fields = "__all__"

        exclude = ["match"]  # Exclude the direct link to the match to avoid redundancy


class TournamentBracketSerializer(serializers.ModelSerializer):
    slots = BracketSlotSerializer(many=True, read_only=True)

    class Meta:
        model = TournamentBracket
        fields = "__all__"
