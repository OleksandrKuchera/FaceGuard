#!/usr/bin/env python3
"""
Експеримент 2: Оцінювання системи — FAR, FRR, Accuracy

Обчислює біометричні метрики для різних значень tolerance.
Підтверджує trade-off: зниження tolerance зменшує FAR, але збільшує FRR.

Датасет (flat):
  dataset/
    ivanenko_01.jpg
    ivanenko_02.jpg
    petrenko_01.jpg
    petrenko_02.jpg
"""

import argparse
import csv
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

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
class PairData:
    person_a: str
    image_a: str
    person_b: str
    image_b: str
    distance: float
    is_same_person: bool


@dataclass
class MetricsResult:
    tolerance: float
    min_confidence: float
    tp: int = 0
    tn: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def far(self) -> float:
        denom = self.fp + self.tn
        return (self.fp / denom * 100) if denom > 0 else 0.0

    @property
    def frr(self) -> float:
        denom = self.fn + self.tp
        return (self.fn / denom * 100) if denom > 0 else 0.0

    @property
    def accuracy(self) -> float:
        total = self.tp + self.tn + self.fp + self.fn
        return ((self.tp + self.tn) / total * 100) if total > 0 else 0.0


def extract_person_name(filename: str) -> str:
    stem = Path(filename).stem
    match = re.match(r"^(.+?)_\d+$", stem)
    if match:
        return match.group(1)
    return stem


def compute_confidence(distance: float) -> float:
    return max(0.0, (1.0 - distance) * 100)


def is_match(distance: float, tolerance: float, min_confidence: float) -> bool:
    return distance < tolerance and compute_confidence(distance) >= min_confidence


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


def build_pairs(records: list[FaceRecord]) -> list[PairData]:
    pairs: list[PairData] = []
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            dist = float(np.linalg.norm(records[i].encoding - records[j].encoding))
            pairs.append(PairData(
                person_a=records[i].person_name,
                image_a=Path(records[i].image_path).name,
                person_b=records[j].person_name,
                image_b=Path(records[j].image_path).name,
                distance=dist,
                is_same_person=(records[i].person_name == records[j].person_name),
            ))
    return pairs


def compute_metrics(pairs: list[PairData], tolerance: float, min_confidence: float) -> MetricsResult:
    m = MetricsResult(tolerance=tolerance, min_confidence=min_confidence)
    for pair in pairs:
        predicted = is_match(pair.distance, tolerance, min_confidence)
        if pair.is_same_person and predicted:
            m.tp += 1
        elif not pair.is_same_person and not predicted:
            m.tn += 1
        elif not pair.is_same_person and predicted:
            m.fp += 1
        elif pair.is_same_person and not predicted:
            m.fn += 1
    return m


def save_csv(results: list[MetricsResult], output_path: Path) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["tolerance", "min_confidence", "FAR (%)", "FRR (%)", "Accuracy (%)", "TP", "TN", "FP", "FN"])
        for r in results:
            writer.writerow([
                f"{r.tolerance:.2f}", f"{r.min_confidence:.1f}",
                f"{r.far:.2f}", f"{r.frr:.2f}", f"{r.accuracy:.2f}",
                r.tp, r.tn, r.fp, r.fn,
            ])
    logger.info("CSV збережено: %s", output_path)


def plot_metrics(results: list[MetricsResult], output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 6))
    tols = [r.tolerance for r in results]
    ax.plot(tols, [r.far for r in results], "o-", label="FAR (%)")
    ax.plot(tols, [r.frr for r in results], "s-", label="FRR (%)")
    ax.plot(tols, [r.accuracy for r in results], "^-", label="Accuracy (%)")
    ax.set_xlabel("Tolerance (поріг евклідової відстані)")
    ax.set_ylabel("Значення (%)")
    ax.set_title("Залежність FAR, FRR та Accuracy від порогу tolerance")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    ax.set_xticks(tols)
    fig.tight_layout()
    fig.savefig(str(output_path), dpi=300)
    plt.close(fig)
    logger.info("Графік метрик збережено: %s", output_path)


def plot_distribution(pairs: list[PairData], output_path: Path, threshold: float = 0.55) -> None:
    fig, ax = plt.subplots(figsize=(10, 6))
    same = [p.distance for p in pairs if p.is_same_person]
    diff = [p.distance for p in pairs if not p.is_same_person]
    if same:
        ax.hist(same, bins=30, alpha=0.6, label="Одна особа")
    if diff:
        ax.hist(diff, bins=30, alpha=0.6, label="Різні особи")
    ax.axvline(x=threshold, color="red", linestyle="--", linewidth=1.5, label=f"Tolerance = {threshold}")
    ax.set_xlabel("Евклідова відстань між 128D векторами")
    ax.set_ylabel("Кількість пар")
    ax.set_title("Розподіл відстаней: одна особа vs різні особи")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(str(output_path), dpi=300)
    plt.close(fig)
    logger.info("Гістограма відстаней збережена: %s", output_path)


def print_report(num_persons: int, valid: int, skipped: int, same: int, diff: int, main: MetricsResult, all_m: list[MetricsResult]) -> None:
    sep = "=" * 60
    print()
    print(sep)
    print("  ЕКСПЕРИМЕНТ 2: FAR / FRR / ACCURACY")
    print(sep)
    print()
    print(f"  Кількість осіб:           {num_persons}")
    print(f"  Валідних фото:            {valid}")
    print(f"  Пропущених фото:          {skipped}")
    print(f"  Same person pairs:        {same}")
    print(f"  Different person pairs:   {diff}")
    print()

    if valid < 10:
        print("  ⚠  ПОПЕРЕДЖЕННЯ: датасет занадто малий (< 10 фото).")
        print()

    print(f"  tolerance = {main.tolerance:.2f}, min_confidence = {main.min_confidence:.1f}%")
    print(f"    FAR      = {main.far:.2f}%")
    print(f"    FRR      = {main.frr:.2f}%")
    print(f"    Accuracy = {main.accuracy:.2f}%")
    print(f"    TP={main.tp}  TN={main.tn}  FP={main.fp}  FN={main.fn}")
    print()

    print("  Sweep по tolerance:")
    print(f"  {'tol':>6}  {'FAR':>8}  {'FRR':>8}  {'Acc':>8}  {'TP':>4}  {'TN':>4}  {'FP':>4}  {'FN':>4}")
    print(f"  {'─' * 6}  {'─' * 8}  {'─' * 8}  {'─' * 8}  {'─' * 4}  {'─' * 4}  {'─' * 4}  {'─' * 4}")
    for r in all_m:
        print(f"  {r.tolerance:>6.2f}  {r.far:>7.2f}%  {r.frr:>7.2f}%  {r.accuracy:>7.2f}%  {r.tp:>4}  {r.tn:>4}  {r.fp:>4}  {r.fn:>4}")
    print()
    print(sep)


def main() -> None:
    parser = argparse.ArgumentParser(description="Експеримент 2: FAR/FRR/Accuracy")
    parser.add_argument("--dataset", type=str, default="dataset")
    parser.add_argument("--output-dir", type=str, default="output")
    parser.add_argument("--tolerance", type=float, default=0.55)
    parser.add_argument("--min-confidence", type=float, default=45.0)
    args = parser.parse_args()

    dataset_dir = Path(args.dataset)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    tolerances = [0.40, 0.45, 0.50, 0.55, 0.60]

    records, skipped = load_dataset(dataset_dir)
    if len(records) < 2:
        logger.error("Потрібно мінімум 2 валідних фото")
        sys.exit(1)

    pairs = build_pairs(records)
    same_pairs = sum(1 for p in pairs if p.is_same_person)
    diff_pairs = sum(1 for p in pairs if not p.is_same_person)

    if same_pairs == 0 or diff_pairs == 0:
        logger.error("Потрібні пари both same та different persons")
        sys.exit(1)

    all_metrics = [compute_metrics(pairs, t, args.min_confidence) for t in tolerances]
    main_metrics = compute_metrics(pairs, args.tolerance, args.min_confidence)

    save_csv(all_metrics, output_dir / "02_metrics_by_tolerance.csv")
    plot_metrics(all_metrics, output_dir / "02_metrics_by_tolerance.png")
    plot_distribution(pairs, output_dir / "02_distance_distribution.png", threshold=args.tolerance)

    num_persons = len(set(r.person_name for r in records))
    print_report(num_persons, len(records), skipped, same_pairs, diff_pairs, main_metrics, all_metrics)
    logger.info("Експеримент 2 завершено. Результати у: %s", output_dir)


if __name__ == "__main__":
    main()
