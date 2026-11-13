from django.db import models


class FeatureKey(models.TextChoices):
    CONTRIBUTIONS = "contributions", "Contributions"
    PROMOTION = "promotion", "Promotion"
