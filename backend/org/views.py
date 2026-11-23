"""
Organization Views

Handles org admin functionality including claim request management.
"""

from typing import Any
from uuid import uuid4

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser, PositionsModel, ProfileClaimRequest, Team
from draft.models import DraftRound
from draft.services.hero_chat import repoint_chat_attribution
from events.ledger import ActorRole, SignupActor, SignupMeans
from events.merge import merge_user_signups
from events.models import Event
from events.staff import dedupe_host_helpers
from league.models import LeagueLog, LeagueUser
from league.models_rating import LeagueMatchParticipant, LeagueRating
from org.accounts import repoint_org_attribution
from org.mmr import merge_org_mmrs
from org.models import OrgLog, OrgUser, PromoSend
from org.permissions import IsOrgStaff
from org.promotion.services import demote_colliding_earning_sends
from org.serializers import ProfileClaimRequestSerializer
from org.standing import api as standing
from steam.models import LeaguePlayerStats, PlayerMatchStats
from telemetry.logging import get_logger

log = get_logger(__name__)


class ClaimRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing profile claim requests.

    Org staff can list, approve, or reject claim requests for their organization.
    """

    serializer_class = ProfileClaimRequestSerializer
    permission_classes = [IsAuthenticated, IsOrgStaff]

    def get_queryset(self) -> QuerySet[ProfileClaimRequest]:
        """Filter to requests for organizations the user is staff of."""
        user = self.request.user

        if user.is_superuser:
            return ProfileClaimRequest.objects.all()

        admin_org_ids = set(user.admin_organizations.values_list("pk", flat=True))
        staff_org_ids = set(user.staff_organizations.values_list("pk", flat=True))
        org_ids = admin_org_ids | staff_org_ids
        return ProfileClaimRequest.objects.filter(organization_id__in=org_ids)

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """List claim requests, optionally filtered by status."""
        queryset = self.get_queryset()

        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        org_id = request.query_params.get("organization")
        if org_id:
            queryset = queryset.filter(organization_id=org_id)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def approve(self, request: Request, pk: str | None = None) -> Response:
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

        if target_user is None or target_user.discordId:
            reason = (
                "Target profile no longer exists"
                if target_user is None
                else "Target profile now has a Discord account linked"
            )
            if not self._mark_reviewed(
                claim_request,
                ProfileClaimRequest.Status.REJECTED,
                request.user,
                rejection_reason=reason,
            ):
                return self._already_reviewed()
            return Response({"error": reason}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            if not self._mark_reviewed(
                claim_request, ProfileClaimRequest.Status.APPROVED, request.user
            ):
                return self._already_reviewed()

            target_pk = target_user.pk
            target_steamid = target_user.steamid

            self._merge_profiles(
                claimer,
                target_user,
                actor=SignupActor(
                    user=request.user,
                    role=ActorRole.STAFF,
                    means=SignupMeans.WEB,
                    correlation_id=f"claim-{uuid4().hex[:12]}",
                ),
            )

            OrgLog.objects.create(
                organization=claim_request.organization,
                actor=request.user,
                action="approve_claim",
                target_user=claimer,
                details={
                    "merged_profile_id": target_pk,
                    "merged_steamid": target_steamid,
                },
            )

            log.info(
                "claim_approved",
                system="org",
                subsystem="views",
                user_id=claimer.pk,
                target_user_id=target_pk,
                target_steamid=target_steamid,
            )

        return Response(
            {"message": "Claim approved. Profiles have been merged."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def reject(self, request: Request, pk: str | None = None) -> Response:
        """Reject a claim request."""
        claim_request = self.get_object()

        if claim_request.status != ProfileClaimRequest.Status.PENDING:
            return Response(
                {"error": f"Request is already {claim_request.status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reason = request.data.get("reason", "")

        if not self._mark_reviewed(
            claim_request,
            ProfileClaimRequest.Status.REJECTED,
            request.user,
            rejection_reason=reason,
        ):
            return self._already_reviewed()

        OrgLog.objects.create(
            organization=claim_request.organization,
            actor=request.user,
            action="reject_claim",
            target_user=claim_request.claimer,
            details={
                "target_profile_id": claim_request.target_user_id,
                "reason": reason,
            },
        )

        return Response(
            {"message": "Claim request rejected."},
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _mark_reviewed(
        claim_request: ProfileClaimRequest,
        new_status: ProfileClaimRequest.Status,
        reviewer: CustomUser,
        rejection_reason: str | None = None,
    ) -> bool:
        fields: dict[str, Any] = {
            "status": new_status,
            "reviewed_by": reviewer,
            "reviewed_at": timezone.now(),
        }
        if rejection_reason is not None:
            fields["rejection_reason"] = rejection_reason
        updated = ProfileClaimRequest.objects.filter(
            pk=claim_request.pk, status=ProfileClaimRequest.Status.PENDING
        ).update(**fields)
        if not updated:
            return False
        for name, value in fields.items():
            setattr(claim_request, name, value)
        return True

    @staticmethod
    def _already_reviewed() -> Response:
        return Response(
            {"error": "Request was already reviewed"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def _merge_profiles(
        self, claimer: CustomUser, target_user: CustomUser, *, actor: SignupActor
    ) -> None:
        """
        Merge target_user's profile into claimer.

        Transfers:
        - Steam ID and profile data
        - All foreign key references
        - Then deletes target_user
        """
        # Copy Friend ID from target to claimer
        claimer.steam_account_id = target_user.steam_account_id

        if target_user.nickname and not claimer.nickname:
            claimer.nickname = target_user.nickname
        if target_user.avatar and not claimer.avatar:
            claimer.avatar = target_user.avatar

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
        pairs: list[tuple[OrgUser, OrgUser]] = []
        for org_user in OrgUser.objects.filter(user=target_user):
            existing = OrgUser.objects.filter(
                user=claimer, organization=org_user.organization
            ).first()
            if existing:
                merge_org_mmrs(org_user, existing)
                pairs.append((org_user, existing))
            else:
                org_user.user = claimer
                org_user.save()
        standing.merge_users(target_user, claimer, member_pairs=pairs)
        repoint_org_attribution(target_user, claimer)
        repoint_chat_attribution(target_user, claimer)
        for org_user, _ in pairs:
            org_user.delete()

        staffed = Event.objects.nocache().filter(
            Q(host=target_user) | Q(helpers=target_user)
        )
        staffed_ids = set(staffed.values_list("pk", flat=True))
        stale_events = list(Event.objects.nocache().filter(pk__in=staffed_ids))
        Event.objects.filter(host=target_user).update(host=claimer)
        for event in list(Event.objects.nocache().filter(helpers=target_user)):
            event.helpers.add(claimer)
            event.helpers.remove(target_user)
        dedupe_host_helpers(claimer)
        if staffed_ids:
            invalidate_after_commit(
                *stale_events,
                *Event.objects.nocache().filter(pk__in=staffed_ids),
            )

        merge_user_signups(target_user, claimer, actor=actor)

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

        # Teams before tournaments: removing target_user from tournament.users
        # cascades to team.members and would run succession first.
        for team in (
            Team.objects.nocache()
            .filter(
                Q(members=target_user)
                | Q(captain=target_user)
                | Q(deputy_captain=target_user)
            )
            .distinct()
        ):
            team.replace_member(target_user, claimer)

        # Tournament participations (M2M)
        for tournament in target_user.tournaments.all():
            if claimer not in tournament.users.all():
                tournament.users.add(claimer)
            tournament.users.remove(target_user)

        # Draft rounds captained
        DraftRound.objects.filter(captain=target_user).update(captain=claimer)

        # HeroDraftEvent is tied to draft_team, not a user; nothing to move

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
        PlayerMatchStats.objects.filter(user=target_user).invalidated_update(
            user=claimer
        )

        # League player stats
        for stats in LeaguePlayerStats.objects.filter(user=target_user):
            existing = LeaguePlayerStats.objects.filter(
                user=claimer, league_id=stats.league_id
            ).first()
            if existing:
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

        demote_colliding_earning_sends(claimer, target_user)
        PromoSend.objects.filter(sender=target_user).update(sender=claimer)
        PromoSend.objects.filter(recipient=target_user).update(recipient=claimer)

        for org in list(target_user.promoter_organizations.all()):
            org.promoters.add(claimer)
            org.promoters.remove(target_user)
            invalidate_after_commit(org)

        # Free the unique steam_account_id before claimer.save() takes it
        target_user.steam_account_id = None
        target_user.steamid = None
        target_user.save(update_fields=["steam_account_id", "steamid"])

        claimer.save()
        target_user.delete()
