"""
apps/persons/admin.py
"""
from django.contrib import admin
from apps.persons.models import Person, PersonPhoto, FaceEncoding, Department


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "parent"]
    search_fields = ["name", "code"]


class PersonPhotoInline(admin.TabularInline):
    model = PersonPhoto
    extra = 0
    readonly_fields = ["is_processed", "face_detected", "quality_score", "uploaded_at"]


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ["person_id", "full_name", "role", "department", "access_level", "is_active"]
    list_filter = ["role", "is_active", "department"]
    search_fields = ["first_name", "last_name", "person_id"]
    inlines = [PersonPhotoInline]

    def full_name(self, obj):
        return obj.full_name


@admin.register(FaceEncoding)
class FaceEncodingAdmin(admin.ModelAdmin):
    list_display = ["person", "model_version", "is_primary", "created_at"]
    list_filter = ["model_version", "is_primary"]
