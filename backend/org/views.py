"""
Organization Views

Handles org admin functionality including claim request management.
"""

import logging

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from app.models import (
    DraftRound,
    HeroDraftEvent,
    LeagueLog,
    LeagueMatchParticipant,
    LeagueRating,
    OrgLog,
    PositionsModel,
    ProfileClaimRequest,
    Team,
)
from app.permissions_org import IsOrgAdmin
from league.models import LeagueUser
from org.models import OrgUser
from org.serializers import ProfileClaimRequestSerializer
from steam.models import LeaguePlayerStats, PlayerMatchStats

log = logging.getLogger(__name__)


class ClaimRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing profile claim requests.

    Org admins can list, approve, or reject claim requests for their organization.
    """

    serializer_class = ProfileClaimRequestSerializer
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    def get_queryset(self):
        """Filter to requests for organizations the user is admin of."""
        user = self.request.user

        # Site admins can see all
        if user.is_superuser:
            return ProfileClaimRequest.objects.all()

        # Org admins see requests for their organizations
        # related_name is "admin_organizations" from Organization.admins field
        admin_org_ids = user.admin_organizations.values_list("pk", flat=True)
        return ProfileClaimRequest.objects.filter(organization_id__in=admin_org_ids)

    def list(self, request, *args, **kwargs):
        """List claim requests, optionally filtered by status."""
        queryset = self.get_queryset()

        # Filter by status if provided
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by organization if provided
        org_id = request.query_params.get("organization")
        if org_id:
            queryset = queryset.filter(organization_id=org_id)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """
        Approve a claim request and perform the profile merge.

        This transfers all data and references from target_user to claimer,
        then deletes target_user.
        """
        claim_request = self.get_object()

        if claim_request.status != ProfileClaimRequest.Status.PENDING:
            return Response(
                {"error": f"Request is already {claim_request.status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        claimer = claim_request.claimer
        target_user = claim_request.target_user

        # Verify target still meets requirements
        if target_user.discordId:
            claim_request.status = ProfileClaimRequest.Status.REJECTED
            claim_request.rejection_reason = (
                "Target profile now has a Discord account linked"
            )
            claim_request.reviewed_by = request.user
            claim_request.reviewed_at = timezone.now()
            claim_request.save()
            return Response(
                {"error": "Target profile now has a Discord account linked"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            # Store target info before merge (target_user will be deleted)
            target_pk = target_user.pk
            target_steamid = target_user.steamid

            # Update the claim request BEFORE merge (target_user will be deleted by merge)
            claim_request.status = ProfileClaimRequest.Status.APPROVED
            claim_request.reviewed_by = request.user
            claim_request.reviewed_at = timezone.now()
            claim_request.save()

            # Perform the merge (this deletes target_user)
            self._merge_profiles(claimer, target_user)

            # Log the action
            OrgLog.objects.create(
                organization=claim_request.organization,
                actor=request.user,
                action="approve_claim",
                target_user=claimer,
                details={
                    "merged_profile_id": target_user.pk,
                    "merged_steamid": target_user.steamid,
                },
            )

            log.info(
                f"Claim approved: {claimer.username} claimed profile {target_user.pk} "
                f"(steamid={target_user.steamid})"
            )

        return Response(
            {"message": "Claim approved. Profiles have been merged."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Reject a claim request."""
        claim_request = self.get_object()

        if claim_request.status != ProfileClaimRequest.Status.PENDING:
            return Response(
                {"error": f"Request is already {claim_request.status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reason = request.data.get("reason", "")

        claim_request.status = ProfileClaimRequest.Status.REJECTED
        claim_request.rejection_reason = reason
        claim_request.reviewed_by = request.user
        claim_request.reviewed_at = timezone.now()
        claim_request.save()

        # Log the action
        OrgLog.objects.create(
            organization=claim_request.organization,
            actor=request.user,
            action="reject_claim",
            target_user=claim_request.claimer,
            details={
                "target_profile_id": claim_request.target_user.pk,
                "reason": reason,
            },
        )

        return Response(
            {"message": "Claim request rejected."},
            status=status.HTTP_200_OK,
        )

    def _merge_profiles(self, claimer, target_user):
        """
        Merge target_user's profile into claimer.

        Transfers:
        - Steam ID and profile data
        - All foreign key references
        - Then deletes target_user
        """
        # Copy Steam ID from target to claimer
        claimer.steamid = target_user.steamid

        # Copy other fields from target if claimer doesn't have them
        if target_user.nickname and not claimer.nickname:
            claimer.nickname = target_user.nickname
        if target_user.mmr and (not claimer.mmr or claimer.mmr == 0):
            claimer.mmr = target_user.mmr
        if target_user.avatar and not claimer.avatar:
            claimer.avatar = target_user.avatar

        # Copy positions if target has them and claimer doesn't
        if target_user.positions and not claimer.positions:
            positions_data = {
                "carry": target_user.positions.carry,
                "mid": target_user.positions.mid,
                "offlane": target_user.positions.offlane,
                "soft_support": target_user.positions.soft_support,
                "hard_support": target_user.positions.hard_support,
            }
            claimer.positions = PositionsModel.objects.create(**positions_data)

        # ============================================================
        # Transfer all foreign key references from target to claimer
        # ============================================================

        # OrgUser memberships
        for org_user in OrgUser.objects.filter(user=target_user):
            existing = OrgUser.objects.filter(
                user=claimer, organization=org_user.organization
            ).first()
            if existing:
                # Keep the one with higher MMR
                if org_user.mmr > existing.mmr:
                    existing.mmr = org_user.mmr
                    existing.save()
                org_user.delete()
            else:
                org_user.user = claimer
                org_user.save()

        # LeagueUser memberships
        for league_user in LeagueUser.objects.filter(user=target_user):
            existing = LeagueUser.objects.filter(
                user=claimer, league=league_user.league
            ).first()
            if existing:
                # Keep the one with higher MMR
                if league_user.mmr > existing.mmr:
                    existing.mmr = league_user.mmr
                    existing.save()
                league_user.delete()
            else:
                league_user.user = claimer
                league_user.save()

        # Tournament participations (M2M)
        for tournament in target_user.tournaments.all():
            if claimer not in tournament.users.all():
                tournament.users.add(claimer)
            tournament.users.remove(target_user)

        # Team memberships (M2M)
        for team in target_user.teams_as_member.all():
            if claimer not in team.members.all():
                team.members.add(claimer)
            team.members.remove(target_user)

        # Team captain/deputy roles
        Team.objects.filter(captain=target_user).update(captain=claimer)
        Team.objects.filter(deputy_captain=target_user).update(deputy_captain=claimer)

        # Draft rounds captained
        DraftRound.objects.filter(captain=target_user).update(captain=claimer)

        # HeroDraft events - HeroDraftEvent doesn't have actor, events are tied to draft_team
        # Skip this - events are associated with teams, not users directly

        # League ratings
        for rating in LeagueRating.objects.filter(player=target_user):
            existing = LeagueRating.objects.filter(
                player=claimer, league=rating.league
            ).first()
            if existing:
                rating.delete()
            else:
                rating.player = claimer
                rating.save()

        # League match participations
        LeagueMatchParticipant.objects.filter(player=target_user).update(player=claimer)

        # Steam match stats
        PlayerMatchStats.objects.filter(user=target_user).update(user=claimer)

        # League player stats
        for stats in LeaguePlayerStats.objects.filter(user=target_user):
            existing = LeaguePlayerStats.objects.filter(
                user=claimer, league_id=stats.league_id
            ).first()
            if existing:
                # Merge stats
                existing.games_played += stats.games_played
                existing.wins += stats.wins
                existing.losses += stats.losses
                existing.total_kills += stats.total_kills
                existing.total_deaths += stats.total_deaths
                existing.total_assists += stats.total_assists
                existing.total_gpm += stats.total_gpm
                existing.total_xpm += stats.total_xpm
                existing.recalculate_averages()
                existing.save()
                stats.delete()
            else:
                stats.user = claimer
                stats.save()

        # Audit logs
        OrgLog.objects.filter(actor=target_user).update(actor=claimer)
        OrgLog.objects.filter(target_user=target_user).update(target_user=claimer)
        LeagueLog.objects.filter(actor=target_user).update(actor=claimer)
        LeagueLog.objects.filter(target_user=target_user).update(target_user=claimer)

        # Clear steamid from target before saving claimer (to avoid UNIQUE constraint)
        target_user.steamid = None
        target_user.save(update_fields=["steamid"])

        # Save claimer and delete target
        claimer.save()
        target_user.delete()
