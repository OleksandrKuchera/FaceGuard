"""
apps/persons/tests/test_face_encoding.py — Unit tests for FaceEncoding model.

Тести перевіряють:
  - шифрування/дешифрування encoding;
  - відсутність відкритих даних у базі;
  - валідацію типу та розмірності;
  - обробку пошкоджених даних.
"""
import pickle

import numpy as np
import pytest
from cryptography.fernet import Fernet, InvalidToken

from apps.persons.models import (
    ENCODING_DIM,
    FaceEncoding,
    decrypt_encoding,
    encrypt_encoding,
)


@pytest.mark.django_db
class TestEncryptEncoding:
    """Тести функції encrypt_encoding."""

    def test_encodes_valid_128d_array(self, sample_encoding, db_encryption_key):
        """Валідний 128D вектор успішно шифрується."""
        result = encrypt_encoding(sample_encoding)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_raises_type_error_for_non_ndarray(self, db_encryption_key):
        """Не-numpy.ndarray викликає TypeError."""
        with pytest.raises(TypeError, match="Очікується numpy.ndarray"):
            encrypt_encoding([0.1] * 128)  # type: ignore[arg-type]

    def test_raises_type_error_for_list(self, db_encryption_key):
        """Python list викликає TypeError."""
        with pytest.raises(TypeError):
            encrypt_encoding([0.0] * ENCODING_DIM)  # type: ignore[arg-type]

    def test_raises_value_error_for_wrong_shape(self, db_encryption_key):
        """Неправильна розмірність викликає ValueError."""
        wrong = np.random.rand(64).astype(np.float64)
        with pytest.raises(ValueError, match="Очікується вектор розмірності"):
            encrypt_encoding(wrong)

    def test_raises_value_error_for_2d_array(self, db_encryption_key):
        """2D масив викликає ValueError."""
        wrong = np.random.rand(1, 128).astype(np.float64)
        with pytest.raises(ValueError):
            encrypt_encoding(wrong)


@pytest.mark.django_db
class TestDecryptEncoding:
    """Тести функції decrypt_encoding."""

    def test_roundtrip_encrypt_decrypt(self, sample_encoding, db_encryption_key):
        """Encoding успішно шифрується і відновлюється."""
        encrypted = encrypt_encoding(sample_encoding)
        decrypted = decrypt_encoding(encrypted)

        assert isinstance(decrypted, np.ndarray)
        assert decrypted.shape == (ENCODING_DIM,)
        np.testing.assert_array_almost_equal(decrypted, sample_encoding)

    def test_raises_invalid_token_for_corrupted_data(self, db_encryption_key):
        """Пошкоджені encrypted_data викликають InvalidToken."""
        corrupted = b"corrupted-data-that-is-not-a-valid-fernet-token"
        with pytest.raises(InvalidToken):
            decrypt_encoding(corrupted)

    def test_raises_invalid_token_for_wrong_key(self, sample_encoding):
        """Дешифрування неправильним ключем викликає InvalidToken."""
        wrong_key = Fernet.generate_key()
        encrypted = encrypt_encoding(sample_encoding)

        # Temporarily use wrong key for decryption
        from django.conf import settings
        original_key = settings.BIOMETRIC_ENCRYPTION_KEY
        settings.BIOMETRIC_ENCRYPTION_KEY = wrong_key

        try:
            with pytest.raises(InvalidToken):
                decrypt_encoding(encrypted)
        finally:
            settings.BIOMETRIC_ENCRYPTION_KEY = original_key


@pytest.mark.django_db
class TestFaceEncodingModel:
    """Тести моделі FaceEncoding."""

    def test_set_and_get_encoding(self, face_encoding, sample_encoding):
        """set_encoding/get_encoding коректно працюють через модель."""
        retrieved = face_encoding.get_encoding()
        assert isinstance(retrieved, np.ndarray)
        assert retrieved.shape == (ENCODING_DIM,)
        np.testing.assert_array_almost_equal(retrieved, sample_encoding)

    def test_encrypted_data_not_plaintext(self, face_encoding, sample_encoding):
        """Після шифрування у базі не лежить відкритий numpy-вектор."""
        raw_bytes = bytes(face_encoding.encoding_data)
        pickled = pickle.dumps(sample_encoding, protocol=pickle.HIGHEST_PROTOCOL)

        # Зашифровані дані не повинні містити сирий pickle
        assert pickled not in raw_bytes
        # Fernet token починається з версії (0x80) і timestamp
        assert raw_bytes[0] == 0x80

    def test_set_encoding_wrong_type(self, person, db_encryption_key):
        """set_encoding з неправильним типом викликає TypeError."""
        enc = FaceEncoding(person=person)
        with pytest.raises(TypeError):
            enc.set_encoding([0.1] * 128)  # type: ignore[arg-type]

    def test_set_encoding_wrong_dimension(self, person, db_encryption_key):
        """set_encoding з неправильною розмірністю викликає ValueError."""
        enc = FaceEncoding(person=person)
        wrong = np.random.rand(64).astype(np.float64)
        with pytest.raises(ValueError):
            enc.set_encoding(wrong)

    def test_get_encoding_corrupted_data(self, person, db_encryption_key):
        """get_encoding з пошкодженими даними викликає InvalidToken."""
        enc = FaceEncoding(person=person)
        enc.encoding_data = b"not-valid-encrypted-data"
        enc.save()

        with pytest.raises(InvalidToken):
            enc.get_encoding()

    def test_multiple_encodings_same_person(self, person, sample_encoding, db_encryption_key):
        """Одна особа може мати кілька encoding."""
        enc1 = FaceEncoding(person=person, is_primary=True)
        enc1.set_encoding(sample_encoding)
        enc1.save()

        enc2 = FaceEncoding(person=person, is_primary=False)
        enc2.set_encoding(sample_encoding + 0.01)
        enc2.save()

        assert person.encodings.count() == 2
        np.testing.assert_array_almost_equal(enc1.get_encoding(), sample_encoding)

    def test_encodings_differ_for_different_inputs(self, person, db_encryption_key):
        """Різні вхідні вектори дають різні зашифровані дані."""
        enc1 = np.random.rand(128).astype(np.float64)
        enc2 = np.random.rand(128).astype(np.float64)

        fe1 = FaceEncoding(person=person)
        fe1.set_encoding(enc1)
        fe1.save()

        fe2 = FaceEncoding(person=person)
        fe2.set_encoding(enc2)
        fe2.save()

        # Зашифровані байти різні
        assert bytes(fe1.encoding_data) != bytes(fe2.encoding_data)
        # Дешифровані значення відповідають оригіналам
        np.testing.assert_array_almost_equal(fe1.get_encoding(), enc1)
        np.testing.assert_array_almost_equal(fe2.get_encoding(), enc2)
