#!/usr/bin/env python3
"""
Експеримент 1: Верифікація облич — розподіл евклідових відстаней

Підтверджує принцип роботи dlib/face_recognition:
  - вирівняне обличчя → CNN → 128D вектор
  - евклідова відстань між векторами однієї особи < між різними особами

Датасет (flat, без підпапок):
  dataset/
    ivanenko_01.jpg
    ivanenko_02.jpg
    petrenko_01.jpg
    petrenko_02.jpg

Ім'я особи визначається з імені файлу: все до останнього _ перед числом.
"""

import argparse
import csv
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import face_recognition
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray

matplotlib.use("Agg")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class FaceRecord:
    person_name: str
    image_path: str
    encoding: NDArray[np.float64]


@dataclass
class PairResult:
    person_a: str
    image_a: str
    person_b: str
    image_b: str
    label: str
    distance: float


@dataclass
class Stats:
    valid_photos: int = 0
    skipped_photos: int = 0
    same_pairs: int = 0
    different_pairs: int = 0
    same_distances: list[float] = field(default_factory=list)
    different_distances: list[float] = field(default_factory=list)


def extract_person_name(filename: str) -> str:
    """
    Витягує ім'я особи з імені файлу.

    Формат: {person_name}_{number}.ext
    Наприклад: ivanenko_01.jpg → "ivanenko"
    """
    stem = Path(filename).stem
    match = re.match(r"^(.+?)_\d+$", stem)
    if match:
        return match.group(1)
    return stem


def load_dataset(dataset_dir: Path) -> tuple[list[FaceRecord], int]:
    if not dataset_dir.is_dir():
        logger.error("Директорія датасету не існує: %s", dataset_dir)
        sys.exit(1)

    image_files = sorted(
        f for f in dataset_dir.iterdir()
        if f.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )

    if not image_files:
        logger.error("Не знайдено зображень у: %s", dataset_dir)
        sys.exit(1)

    logger.info("Знайдено %d зображень", len(image_files))

    records: list[FaceRecord] = []
    skipped = 0

    for img_path in image_files:
        person_name = extract_person_name(img_path.name)

        try:
            image = face_recognition.load_image_file(str(img_path))
            encodings = face_recognition.face_encodings(image)

            if len(encodings) == 0:
                logger.warning("ПРОПУСК (0 облич): %s", img_path.name)
                skipped += 1
                continue

            if len(encodings) > 1:
                logger.warning("ПРОПУСК (%d облич): %s", len(encodings), img_path.name)
                skipped += 1
                continue

            records.append(FaceRecord(
                person_name=person_name,
                image_path=str(img_path),
                encoding=np.array(encodings[0], dtype=np.float64),
            ))

        except Exception as exc:
            logger.warning("ПРОПУСК (помилка): %s — %s", img_path.name, exc)
            skipped += 1

    logger.info("Валідних: %d, пропущено: %d", len(records), skipped)
    return records, skipped


def compute_all_pairs(records: list[FaceRecord]) -> list[PairResult]:
    results: list[PairResult] = []
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            dist = float(np.linalg.norm(records[i].encoding - records[j].encoding))
            label = "same" if records[i].person_name == records[j].person_name else "different"
            results.append(PairResult(
                person_a=records[i].person_name,
                image_a=Path(records[i].image_path).name,
                person_b=records[j].person_name,
                image_b=Path(records[j].image_path).name,
                label=label,
                distance=dist,
            ))
    return results


def save_csv(results: list[PairResult], output_path: Path) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["person_a", "image_a", "person_b", "image_b", "label", "distance"])
        for r in results:
            writer.writerow([r.person_a, r.image_a, r.person_b, r.image_b, r.label, f"{r.distance:.6f}"])
    logger.info("CSV збережено: %s (%d рядків)", output_path, len(results))


def plot_histogram(stats: Stats, output_path: Path, threshold: float = 0.6) -> None:
    fig, ax = plt.subplots(figsize=(10, 6))

    if stats.same_distances:
        ax.hist(stats.same_distances, bins=30, alpha=0.6, label="Одна особа")
    if stats.different_distances:
        ax.hist(stats.different_distances, bins=30, alpha=0.6, label="Різні особи")

    ax.axvline(x=threshold, color="red", linestyle="--", linewidth=1.5, label=f"Поріг = {threshold}")

    ax.set_xlabel("Евклідова відстань між 128D векторами")
    ax.set_ylabel("Кількість пар")
    ax.set_title("Розподіл евклідових відстаней:\nодна особа vs різні особи")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(str(output_path), dpi=300)
    plt.close(fig)
    logger.info("Графік збережено: %s", output_path)


def print_stats(stats: Stats) -> None:
    sep = "=" * 60
    print()
    print(sep)
    print("  ЕКСПЕРИМЕНТ 1: ВЕРИФІКАЦІЯ ОБЛИЧ")
    print(sep)
    print()
    print(f"  Валідних фото:          {stats.valid_photos}")
    print(f"  Пропущених фото:        {stats.skipped_photos}")
    print()

    if stats.same_distances:
        arr = np.array(stats.same_distances)
        print("  SAME PERSON distances:")
        print(f"    min  = {arr.min():.6f}")
        print(f"    mean = {arr.mean():.6f}")
        print(f"    max  = {arr.max():.6f}")
    else:
        print("  SAME PERSON distances:  (немає даних)")
    print()

    if stats.different_distances:
        arr = np.array(stats.different_distances)
        print("  DIFFERENT PERSONS distances:")
        print(f"    min  = {arr.min():.6f}")
        print(f"    mean = {arr.mean():.6f}")
        print(f"    max  = {arr.max():.6f}")
    else:
        print("  DIFFERENT PERSONS distances:  (немає даних)")
    print()
    print(f"  Same pairs:             {stats.same_pairs}")
    print(f"  Different pairs:        {stats.different_pairs}")
    print()
    print(sep)


def main() -> None:
    parser = argparse.ArgumentParser(description="Експеримент 1: Верифікація облич")
    parser.add_argument("--dataset", type=str, default="dataset")
    parser.add_argument("--output-dir", type=str, default="output")
    parser.add_argument("--threshold", type=float, default=0.6)
    args = parser.parse_args()

    dataset_dir = Path(args.dataset)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    records, skipped = load_dataset(dataset_dir)
    if len(records) < 2:
        logger.error("Потрібно мінімум 2 валідних фото")
        sys.exit(1)

    results = compute_all_pairs(records)
    save_csv(results, output_dir / "01_pair_distances.csv")

    stats = Stats(
        valid_photos=len(records),
        skipped_photos=skipped,
    )
    for r in results:
        if r.label == "same":
            stats.same_distances.append(r.distance)
            stats.same_pairs += 1
        else:
            stats.different_distances.append(r.distance)
            stats.different_pairs += 1

    print_stats(stats)
    plot_histogram(stats, output_dir / "01_distance_histogram.png", threshold=args.threshold)
    logger.info("Експеримент 1 завершено. Результати у: %s", output_dir)


if __name__ == "__main__":
    main()
