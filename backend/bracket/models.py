import logging
import math

from django.db import models

from app.models import TOURNAMNET_TYPE_CHOICES, CustomUser, Game, Team, Tournament

log = logging.getLogger(__name__)

# Create your models here.
# TODO Move tournament related stuff to here
STATUS_CHOICES = (
    ("pending", "Pending"),
    ("in_progress", "In Progress"),
    ("completed", "Completed"),
)


class TournamentBracket(models.Model):
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name="brackets"
    )

    max_rounds = models.PositiveIntegerField(default=4, blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    type = models.CharField(
        max_length=20, choices=TOURNAMNET_TYPE_CHOICES, default="double_elimination"
    )

    class Meta:
        verbose_name_plural = "Tournament Brackets"

    def __str__(self):
        return f"Bracket for {self.tournament.name} - Round {self.max_rounds}"

    def generate_double_elimination_bracket(self):
        """
        Generates a double elimination bracket structure for a number of teams
        that is a power of 2 (4, 8, 16).
        This function creates all the necessary BracketSlot and Game objects.

        The structure is a standard double-elimination bracket with a
        Winners' Bracket and a Losers' Bracket, culminating in a Grand Final.
        """
        if not self.tournament:
            log.error("No Tournament")
            return
        if not self.tournament.teams.exists():
            log.error("No Teams in Tournament")
            return

        teams = list(self.tournament.teams.all())

        num_teams = len(teams)

        if num_teams not in [4, 8, 16] or (
            num_teams & (num_teams - 1) != 0 and num_teams != 0
        ):
            raise ValueError("This function currently only supports 4, 8, or 16 teams.")

        self.slots.all().delete()
        if not self.max_rounds:
            self.max_rounds = 4

        wb_rounds = int(math.log2(num_teams))
        lb_rounds = 2 * wb_rounds - 2

        wb_slots = [[] for _ in range(wb_rounds)]
        lb_slots = [[] for _ in range(lb_rounds)]

        # --- Winners' Bracket ---
        # Round 1
        for i in range(num_teams // 2):
            game = Game.objects.create(tournament=self.tournament)
            slot1 = BracketSlot.objects.create(bracket=self, max_rounds=1, game=game)
            slot2 = BracketSlot.objects.create(bracket=self, max_rounds=1, game=game)
            wb_slots[0].extend([slot1, slot2])

        # Assign teams
        for i in range(num_teams):
            wb_slots[0][i].participant = teams[i]
            wb_slots[0][i].save()

        # Subsequent Winners' Bracket Rounds
        for r in range(1, wb_rounds):
            num_matches_in_round = len(wb_slots[r - 1]) // 2
            for i in range(num_matches_in_round):
                game = Game.objects.create(tournament=self.tournament)
                slot1 = BracketSlot.objects.create(
                    bracket=self,
                    max_rounds=r + 1,
                    game=game,
                    winners_source=wb_slots[r - 1][i * 2],
                )
                slot2 = BracketSlot.objects.create(
                    bracket=self,
                    max_rounds=r + 1,
                    game=game,
                    winners_source=wb_slots[r - 1][i * 2 + 1],
                )
                wb_slots[r].extend([slot1, slot2])

        # --- Losers' Bracket ---
        # LB has two "sequences" of rounds.
        # Sequence 1: Losers from a WB round play each other.
        # Sequence 2: Losers from a WB round play winners from a previous LB round.
        lb_round_counter = 1
        for r in range(wb_rounds - 1):
            # Sequence 1
            num_matches = len(wb_slots[r]) // 4
            round_slots = []
            for i in range(num_matches):
                game = Game.objects.create(tournament=self.tournament)
                slot1 = BracketSlot.objects.create(
                    bracket=self,
                    max_rounds=lb_round_counter,
                    is_losers_bracket=True,
                    game=game,
                    losers_source=wb_slots[r][i * 2],
                )
                slot2 = BracketSlot.objects.create(
                    bracket=self,
                    max_rounds=lb_round_counter,
                    is_losers_bracket=True,
                    game=game,
                    losers_source=wb_slots[r][i * 2 + 1],
                )
                round_slots.extend([slot1, slot2])
            lb_slots[lb_round_counter - 1] = round_slots
            lb_round_counter += 1

            # Sequence 2
            prev_lb_round_slots = round_slots
            num_matches = len(prev_lb_round_slots) // 2
            round_slots = []
            for i in range(num_matches):
                game = Game.objects.create(tournament=self.tournament)
                slot1 = BracketSlot.objects.create(
                    bracket=self,
                    max_rounds=lb_round_counter,
                    is_losers_bracket=True,
                    game=game,
                    losers_source=wb_slots[r + 1][i],
                )
                slot2 = BracketSlot.objects.create(
                    bracket=self,
                    max_rounds=lb_round_counter,
                    is_losers_bracket=True,
                    game=game,
                    winners_source=prev_lb_round_slots[i * 2],
                )
                round_slots.extend([slot1, slot2])
            lb_slots[lb_round_counter - 1] = round_slots
            lb_round_counter += 1

        # --- Grand Final ---
        game = Game.objects.create(tournament=self.tournament)
        final_slot1 = BracketSlot.objects.create(
            bracket=self, max_rounds=200, game=game, winners_source=wb_slots[-1][0]
        )
        # The winner of the last LB round advances.
        final_slot2 = BracketSlot.objects.create(
            bracket=self, max_rounds=200, game=game, winners_source=lb_slots[-1][0]
        )

        # Add all slots to the bracket
        all_slots = [slot for round_slots in wb_slots for slot in round_slots]
        all_slots.extend(
            [slot for round_slots in lb_slots if round_slots for slot in round_slots]
        )
        all_slots.extend([final_slot1, final_slot2])
        self.slots.add(*all_slots)
        self.save()


class BracketSlot(models.Model):
    SOURCE_TYPE_CHOICES = (
        ("winner", "Winner"),
        ("loser", "Loser"),
    )
    max_rounds = models.PositiveIntegerField()
    is_losers_bracket = models.BooleanField(default=False)
    bracket = models.ForeignKey(
        TournamentBracket, on_delete=models.CASCADE, related_name="slots"
    )
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="matches")

    participant = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="match_slots",
    )
    winners_source = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="winners_slot",
    )
    losers_source = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="losers_slot",
    )
