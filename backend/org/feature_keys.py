from django.db import models


class FeatureKey(models.TextChoices):
    CONDUCT = "conduct", "Conduct"
    CONTRIBUTIONS = "contributions", "Contributions"
    LEADERSHIP = "leadership", "Leadership"
    PROMOTION = "promotion", "Promotion"
