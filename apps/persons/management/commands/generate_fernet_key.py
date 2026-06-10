"""
Generate a new Fernet encryption key for biometric data.

Usage:
    python manage.py generate_fernet_key

Add the output to .env as BIOMETRIC_ENCRYPTION_KEY=<key>
"""
from django.core.management.base import BaseCommand
from cryptography.fernet import Fernet


class Command(BaseCommand):
    help = "Generate a new Fernet encryption key for biometric data"

    def handle(self, *args, **options):
        key = Fernet.generate_key().decode()
        self.stdout.write(self.style.SUCCESS("Новий Fernet-ключ згенеровано:"))
        self.stdout.write("")
        self.stdout.write(f"  BIOMETRIC_ENCRYPTION_KEY={key}")
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "Скопіюйте цей ключ у .env файл. "
                "Не втрачайте його — без нього неможливо дешифрувати збережені біометричні дані."
            )
        )
