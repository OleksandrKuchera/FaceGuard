"""
apps/persons/models.py — Person, PersonPhoto, FaceEncoding, Department
"""
from __future__ import annotations

import pickle
from typing import TYPE_CHECKING

import numpy as np
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

from apps.core.models import TimestampedModel

if TYPE_CHECKING:
    from numpy.typing import NDArray

ENCODING_DIM = 128


# ─── Helper functions ────────────────────────────────────────────────


def encrypt_encoding(encoding: NDArray[np.float64]) -> bytes:
    """
    Серіалізує numpy-вектор через pickle та шифрує через Fernet.

    Fernet — це готовий механізм симетричного шифрування з автентифікацією.
    Використовує AES-128-CBC + HMAC-SHA256, гарантує цілісність даних.

    Args:
        encoding: numpy.ndarray форми (128,) з float64.

    Returns:
        Зашифровані байти (token Fernet).

    Raises:
        TypeError: якщо encoding не є numpy.ndarray.
        ValueError: якщо розмірність не дорівнює 128.
    """
    if not isinstance(encoding, np.ndarray):
        raise TypeError(
            f"Очікується numpy.ndarray, отримано {type(encoding).__name__}"
        )
    if encoding.shape != (ENCODING_DIM,):
        raise ValueError(
            f"Очікується вектор розмірності ({ENCODING_DIM},), отримано {encoding.shape}"
        )

    raw = pickle.dumps(encoding, protocol=pickle.HIGHEST_PROTOCOL)
    fernet = Fernet(settings.BIOMETRIC_ENCRYPTION_KEY)
    return fernet.encrypt(raw)


def decrypt_encoding(encrypted_data: bytes) -> NDArray[np.float64]:
    """
    Дешифрує Fernet-токен та десеріалізує numpy-вектор.

    Args:
        encrypted_data: зашифровані байти (Fernet token).

    Returns:
        numpy.ndarray форми (128,) з float64.

    Raises:
        cryptography.fernet.InvalidToken: якщо дані пошкоджені або ключ неправильний.
        pickle.UnpicklingError: якщо дані не є валідним pickle.
    """
    fernet = Fernet(settings.BIOMETRIC_ENCRYPTION_KEY)
    raw = fernet.decrypt(encrypted_data)
    obj = pickle.loads(raw)  # noqa: S301 — дані контрольовані

    if not isinstance(obj, np.ndarray):
        raise TypeError(
            f"Десеріалізований об'єкт не є numpy.ndarray: {type(obj).__name__}"
        )
    if obj.shape != (ENCODING_DIM,):
        raise ValueError(
            f"Неправильна форма вектора: {obj.shape}, очікується ({ENCODING_DIM},)"
        )
    return obj


# ─── Django models ───────────────────────────────────────────────────


class Department(models.Model):
    name = models.CharField(max_length=200, verbose_name="Назва")
    code = models.CharField(max_length=20, unique=True, verbose_name="Код")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )

    class Meta:
        verbose_name = "Підрозділ"
        verbose_name_plural = "Підрозділи"
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class Person(TimestampedModel):
    ROLE_CHOICES = [
        ("staff", "Персонал"),
        ("visitor", "Відвідувач"),
        ("contractor", "Підрядник"),
        ("unknown", "Невідомий"),
    ]

    # Ідентифікація
    first_name = models.CharField(max_length=100, verbose_name="Ім'я")
    last_name = models.CharField(max_length=100, verbose_name="Прізвище")
    middle_name = models.CharField(max_length=100, blank=True, verbose_name="По батькові")
    person_id = models.CharField(
        max_length=50, unique=True, verbose_name="ID (табельний номер)"
    )

    # Роль
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="staff")
    department = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="persons",
    )

    # Статус
    is_active = models.BooleanField(default=True, verbose_name="Активний")
    access_level = models.IntegerField(default=1, verbose_name="Рівень доступу (1-5)")

    # Фото обкладинки
    primary_photo = models.ImageField(
        upload_to="persons/", null=True, blank=True, verbose_name="Основне фото"
    )

    # GDPR
    consent_given = models.BooleanField(default=False)
    consent_date = models.DateTimeField(null=True, blank=True)
    deletion_requested = models.BooleanField(default=False)
    deletion_date = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Особа"
        verbose_name_plural = "Особи"
        indexes = [models.Index(fields=["person_id"])]
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.last_name} {self.first_name} ({self.person_id})"

    @property
    def full_name(self):
        parts = [self.last_name, self.first_name, self.middle_name]
        return " ".join(p for p in parts if p)


class PersonPhoto(models.Model):
    person = models.ForeignKey(Person, related_name="photos", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="persons/training/", verbose_name="Фото")

    # ML статус
    is_processed = models.BooleanField(default=False)
    face_detected = models.BooleanField(null=True)  # None = не перевірено
    encoding = models.BinaryField(null=True, blank=True)  # pickle(numpy 128-dim)

    quality_score = models.FloatField(null=True, blank=True)
    landmarks_json = models.JSONField(null=True, blank=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Фото особи"
        verbose_name_plural = "Фото осіб"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"Photo #{self.pk} of {self.person}"


class FaceEncoding(models.Model):
    """
    Зберігає 128-вимірний вектор ознак обличчя у зашифрованому вигляді.

    encoding_data — BinaryField, який містить Fernet-зашифрований pickle numpy-масиву.
    BinaryField підходить для цього, оскільки зашифровані дані є довільними байтами
    без текстової структури, і PostgreSQL ефективно зберігає їх у TOAST-таблиці.
    """

    person = models.ForeignKey(
        Person, related_name="encodings", on_delete=models.CASCADE
    )
    encoding_data = models.BinaryField(
        verbose_name="Зашифрований вектор ознак",
    )
    model_version = models.CharField(
        max_length=50,
        default="resnet_v1",
        verbose_name="Версія моделі",
    )
    is_primary = models.BooleanField(
        default=False,
        verbose_name="Основний encoding",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата створення",
    )

    class Meta:
        verbose_name = "Face Encoding"
        verbose_name_plural = "Face Encodings"
        indexes = [models.Index(fields=["person", "is_primary"])]

    def set_encoding(self, encoding: NDArray[np.float64]) -> None:
        """
        Валідує, серіалізує та шифрує 128D вектор ознак.

        Args:
            encoding: numpy.ndarray форми (128,) з float64.

        Raises:
            TypeError: якщо encoding не є numpy.ndarray.
            ValueError: якщо розмірність не дорівнює 128.
        """
        self.encoding_data = encrypt_encoding(encoding)

    def get_encoding(self) -> NDArray[np.float64]:
        """
        Дешифрує та десеріалізує 128D вектор ознак.

        Returns:
            numpy.ndarray форми (128,) з float64.

        Raises:
            InvalidToken: якщо дані пошкоджені або ключ неправильний.
        """
        return decrypt_encoding(bytes(self.encoding_data))

    def __str__(self) -> str:
        return f"Encoding #{self.pk} [{self.model_version}] — {self.person}"
