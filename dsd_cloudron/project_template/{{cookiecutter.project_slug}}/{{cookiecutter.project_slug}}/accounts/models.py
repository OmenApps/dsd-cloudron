from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Custom user model so the project can evolve auth without a migration break."""
