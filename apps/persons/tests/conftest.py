"""
apps/persons/tests/conftest.py — Pytest fixtures for persons app
"""
import pytest
import numpy as np
from cryptography.fernet import Fernet

from apps.persons.models import Person, FaceEncoding


@pytest.fixture
def encryption_key():
    """Generate a test Fernet key."""
    return Fernet.generate_key()


@pytest.fixture
def db_encryption_key(settings, encryption_key):
    """Override BIOMETRIC_ENCRYPTION_KEY in Django settings for tests."""
    settings.BIOMETRIC_ENCRYPTION_KEY = encryption_key
    return encryption_key


@pytest.fixture
def sample_encoding():
    """Generate a random 128D numpy array simulating a face encoding."""
    return np.random.rand(128).astype(np.float64)


@pytest.fixture
def person(db):
    """Create a test Person."""
    return Person.objects.create(
        first_name="Test",
        last_name="Person",
        person_id="TEST-001",
    )


@pytest.fixture
def face_encoding(db, person, sample_encoding, db_encryption_key):
    """Create a FaceEncoding record with encrypted data."""
    enc = FaceEncoding(person=person, model_version="resnet_v1")
    enc.set_encoding(sample_encoding)
    enc.save()
    return enc
