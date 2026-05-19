from django.http import JsonResponse


def ping(request):
    """Placeholder to verify URL wiring. Replaced by MeProfileView in Task 8."""
    return JsonResponse({"ok": True})
