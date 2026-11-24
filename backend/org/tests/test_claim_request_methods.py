from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser
from org.models import Organization
from tests.cache import flush_run_cache
from user.models import ProfileClaimRequest


class ClaimRequestMethodsTests(TestCase):
    def setUp(self) -> None:
        flush_run_cache()
        self.staff = CustomUser.objects.create_user(
            username="claim_methods_staff", password="testpass"
        )
        self.org = Organization.objects.create(name="Claim Methods Org")
        self.org.staff.add(self.staff)
        self.claimer = CustomUser.objects.create_user(
            username="claim_methods_claimer", password="testpass"
        )
        self.target = CustomUser.objects.create_user(
            username="claim_methods_target", password="testpass"
        )
        self.claim = ProfileClaimRequest.objects.create(
            claimer=self.claimer,
            target_user=self.target,
            organization=self.org,
            status=ProfileClaimRequest.Status.PENDING,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        self.detail_url = f"/api/claim-requests/{self.claim.pk}/"

    def test_create_not_allowed(self) -> None:
        response = self.client.post(
            "/api/claim-requests/",
            {"target_user": self.target.pk, "organization": self.org.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 405, response.content)

    def test_put_not_allowed(self) -> None:
        response = self.client.put(
            self.detail_url, {"status": "approved"}, format="json"
        )
        self.assertEqual(response.status_code, 405, response.content)

    def test_patch_not_allowed(self) -> None:
        response = self.client.patch(
            self.detail_url, {"status": "approved"}, format="json"
        )
        self.assertEqual(response.status_code, 405, response.content)

    def test_delete_not_allowed(self) -> None:
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, 405, response.content)
        self.assertTrue(
            ProfileClaimRequest.objects.nocache().filter(pk=self.claim.pk).exists()
        )

    def test_list_still_works(self) -> None:
        response = self.client.get("/api/claim-requests/", {"status": "pending"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([row["id"] for row in response.json()], [self.claim.pk])

    def test_retrieve_still_works(self) -> None:
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["id"], self.claim.pk)

    def test_reject_still_works(self) -> None:
        response = self.client.post(
            f"{self.detail_url}reject/", {"reason": "nope"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ProfileClaimRequest.Status.REJECTED)
