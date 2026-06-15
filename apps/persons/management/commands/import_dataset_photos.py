"""
python manage.py import_dataset_photos --dataset /path/to/dataset

Імпортує фото з датасету як фото осіб для розпізнавання.
За замовчуванням групує фото по префіксу імені файлу:
    burdun_1.jpeg, burdun_2.jpeg -> person_id=burdun
    olesia_1.png, olesia_2.png   -> person_id=olesia

Можна також імпортувати одну особу:
    python manage.py import_dataset_photos --dataset /path/to/dataset --person-id burdun
"""
import logging
import re
from collections import defaultdict
from pathlib import Path

import face_recognition
import numpy as np
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


class Command(BaseCommand):
    help = "Імпортує фото з датасету як фото особи для розпізнавання"

    def add_arguments(self, parser):
        parser.add_argument("--dataset", type=str, required=True, help="Шлях до папки з фото")
        parser.add_argument(
            "--person-id",
            type=str,
            default=None,
            help="ID однієї особи для імпорту (якщо не вказано — імпортує всі групи з dataset)",
        )
        parser.add_argument(
            "--person-name",
            type=str,
            default=None,
            help="ПІБ/мітка для однієї особи (лише для single-person mode)",
        )

    def handle(self, *args, **options):
        dataset_dir = Path(options["dataset"])
        person_id = options["person_id"]
        person_name = options["person_name"] or person_id

        if not dataset_dir.is_dir():
            self.stderr.write(f"Директорія не існує: {dataset_dir}")
            return

        image_files = sorted(
            f for f in dataset_dir.rglob("*")
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        )

        if not image_files:
            self.stderr.write("Не знайдено зображень")
            return

        # Готуємо групи: person_id -> [files]
        grouped_files = defaultdict(list)
        for img_path in image_files:
            file_pid = self._infer_person_id(img_path, dataset_dir)
            if person_id and file_pid != person_id:
                continue
            grouped_files[file_pid].append(img_path)

        if person_id and person_id not in grouped_files:
            self.stderr.write("Не знайдено фото для цієї особи")
            return

        if not grouped_files:
            self.stderr.write("Не знайдено фото для імпорту")
            return

        from apps.persons.models import Person, PersonPhoto, FaceEncoding

        total_added = 0
        total_skipped = 0
        total_people = 0

        for current_pid, current_files in sorted(grouped_files.items()):
            current_name = person_name if person_id and current_pid == person_id and person_name else current_pid
            first_name, last_name = self._infer_name_parts(current_name)

            person, created = Person.objects.get_or_create(
                person_id=current_pid,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "role": "staff",
                    "is_active": True,
                },
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Створено особу: {current_pid}"))
            else:
                self.stdout.write(f"Особа вже існує: {current_pid} (id={person.id})")

            changed_fields = []
            if not person.consent_given:
                person.consent_given = True
                person.consent_date = timezone.now()
                changed_fields.extend(["consent_given", "consent_date"])
            if not person.first_name or person.first_name.casefold() == person.person_id.casefold():
                person.first_name = first_name
                changed_fields.append("first_name")
            if not person.last_name or person.last_name.casefold() == person.person_id.casefold():
                person.last_name = last_name
                changed_fields.append("last_name")
            if not person.is_active:
                person.is_active = True
                changed_fields.append("is_active")
            if changed_fields:
                person.save(update_fields=changed_fields)

            added = 0
            skipped = 0
            for img_path in current_files:
                if PersonPhoto.objects.filter(person=person, image__endswith=img_path.name).exists():
                    self.stdout.write(f"  Вже є: {img_path.name}")
                    skipped += 1
                    continue

                try:
                    image = face_recognition.load_image_file(str(img_path))
                    face_locations = face_recognition.face_locations(image, model="hog")

                    if len(face_locations) != 1:
                        self.stdout.write(f"  Пропуск ({len(face_locations)} облич): {img_path.name}")
                        skipped += 1
                        continue

                    encodings = face_recognition.face_encodings(image, known_face_locations=face_locations)
                    if not encodings:
                        self.stdout.write(f"  Пропуск (encoding failed): {img_path.name}")
                        skipped += 1
                        continue

                    from django.core.files import File
                    import io
                    from PIL import Image as PILImage

                    pil_img = PILImage.fromarray(image)
                    img_io = io.BytesIO()
                    pil_img.save(img_io, format="JPEG")
                    img_io.seek(0)

                    photo = PersonPhoto(
                        person=person,
                        image=File(img_io, name=f"dataset_imports/{current_pid}/{img_path.name}"),
                        face_detected=True,
                        is_processed=True,
                    )
                    photo.save()

                    fe = FaceEncoding(person=person)
                    fe.set_encoding(np.array(encodings[0], dtype=np.float64))
                    fe.is_primary = (person.encodings.count() == 0)
                    fe.save()

                    added += 1
                    self.stdout.write(self.style.SUCCESS(f"  Додано: {img_path.name}"))

                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"  Помилка: {img_path.name} — {e}"))
                    skipped += 1

            total_people += 1
            total_added += added
            total_skipped += skipped
            self.stdout.write(f"  Підсумок {current_pid}: додано {added}, пропущено {skipped}")
            self.stdout.write("")

        self.stdout.write(self.style.SUCCESS(
            f"Готово: осіб {total_people}, додано {total_added}, пропущено {total_skipped}"
        ))

        from apps.recognition.state import get_pipeline
        pipeline = get_pipeline()
        if pipeline:
            pipeline.reload_encodings()
            self.stdout.write(f"Encodings перезавантажено: {len(pipeline._encoding_cache)} записів")

    @staticmethod
    def _infer_person_id(img_path: Path, dataset_root: Path) -> str:
        relative = img_path.relative_to(dataset_root)
        if len(relative.parts) > 1:
            return Command._sanitize_key(relative.parts[0])

        stem = img_path.stem
        match = re.match(r"^(.+?)_\d+$", stem)
        raw = match.group(1) if match else stem
        return Command._sanitize_key(raw)

    @staticmethod
    def _sanitize_key(value: str) -> str:
        value = value.strip()
        value = re.sub(r"[^0-9A-Za-z_-]+", "_", value)
        return value[:50] or "unknown"

    @staticmethod
    def _infer_name_parts(value: str) -> tuple[str, str]:
        cleaned = value.replace("_", " ").replace("-", " ").strip()
        cleaned = re.sub(r"(?<=[a-zа-я])(?=[A-ZА-Я])", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        parts = [part for part in cleaned.split(" ") if part]

        def prettify(token: str) -> str:
            return token[:1].upper() + token[1:] if token else token

        if not parts:
            return ("Unknown", "Unknown")
        if len(parts) == 1:
            pretty = prettify(parts[0])
            return (pretty, pretty)
        if len(parts) == 2:
            return (prettify(parts[0]), prettify(parts[1]))
        return (prettify(" ".join(parts[:-1])), prettify(parts[-1]))
