from django.db import models


class FeatureKey(models.TextChoices):
    CONDUCT = "conduct", "Conduct"
    CONTRIBUTIONS = "contributions", "Contributions"
    LEADERSHIP = "leadership", "Leadership"
    MMR_SYNC = "mmr_sync", "MMR sync API"
    PROMOTION = "promotion", "Promotion"
