from django.db import models


class FeatureKey(models.TextChoices):
    CONDUCT = "conduct", "Conduct"
    CONTRIBUTIONS = "contributions", "Contributions"
    PROMOTION = "promotion", "Promotion"
