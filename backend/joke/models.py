from django.conf import settings
from django.db import models


class Joke(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="joke"
    )
    tangoes_purchased = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "app_joke"
        verbose_name = "Joke"
        verbose_name_plural = "Jokes"

    def __str__(self) -> str:
        return f"{self.user.username} - {self.tangoes_purchased} tangoes"
