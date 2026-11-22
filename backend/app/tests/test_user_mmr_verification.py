"""Tests for League Rating system and user MMR verification."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser


class CustomUserMMRVerificationTest(TestCase):
    """Test CustomUser MMR verification fields."""

    def test_user_has_mmr_verification_fields(self):
        """CustomUser should have MMR verification tracking fields."""
        user = CustomUser.objects.create_user(
            username="testuser", password="testpass123"
        )

        self.assertFalse(user.has_active_dota_mmr)
        self.assertIsNone(user.dota_mmr_last_verified)

    def test_user_can_set_mmr_verified(self):
        """Can set MMR verification status and timestamp."""
        user = CustomUser.objects.create_user(
            username="testuser", password="testpass123"
        )

        user.has_active_dota_mmr = True
        user.dota_mmr_last_verified = timezone.now()
        user.save()

        user.refresh_from_db()
        self.assertTrue(user.has_active_dota_mmr)
        self.assertIsNotNone(user.dota_mmr_last_verified)

    def test_needs_mmr_verification_property(self):
        """needs_mmr_verification should be True if verified > 30 days ago."""
        user = CustomUser.objects.create_user(
            username="testuser", password="testpass123"
        )

        # No active MMR = no verification needed
        user.has_active_dota_mmr = False
        self.assertFalse(user.needs_mmr_verification)

        # Active MMR, never verified = needs verification
        user.has_active_dota_mmr = True
        user.dota_mmr_last_verified = None
        self.assertTrue(user.needs_mmr_verification)

        # Active MMR, verified recently = no verification needed
        user.dota_mmr_last_verified = timezone.now()
        self.assertFalse(user.needs_mmr_verification)

        # Active MMR, verified > 30 days ago = needs verification
        user.dota_mmr_last_verified = timezone.now() - timedelta(days=31)
        self.assertTrue(user.needs_mmr_verification)
