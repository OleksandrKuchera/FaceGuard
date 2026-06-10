"""
apps/persons/serializers.py
"""
from rest_framework import serializers
from apps.persons.models import Person, PersonPhoto, FaceEncoding, Department


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "code", "parent"]


class PersonPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonPhoto
        fields = ["id", "image", "is_processed", "face_detected", "quality_score", "uploaded_at"]
        read_only_fields = ["is_processed", "face_detected", "quality_score", "uploaded_at"]


class PersonListSerializer(serializers.ModelSerializer):
    """List serializer — includes edit-form fields so the frontend doesn't need a detail fetch."""
    full_name = serializers.CharField(read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)

    class Meta:
        model = Person
        fields = [
            "id", "first_name", "last_name", "middle_name",
            "full_name", "person_id", "role",
            "department", "department_name",
            "access_level", "is_active", "consent_given",
            "primary_photo", "notes", "created_at",
        ]


class PersonDetailSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    department = DepartmentSerializer(read_only=True)
    department_id = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), source="department", write_only=True, required=False
    )
    photos = PersonPhotoSerializer(many=True, read_only=True)
    encoding_count = serializers.SerializerMethodField()

    class Meta:
        model = Person
        fields = [
            "id", "full_name", "first_name", "last_name", "middle_name",
            "person_id", "role", "department", "department_id",
            "access_level", "is_active", "primary_photo",
            "consent_given", "consent_date", "notes",
            "encoding_count", "photos", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_encoding_count(self, obj):
        return obj.encodings.count()


class PersonShortSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Person
        fields = ["id", "full_name", "person_id", "role"]
