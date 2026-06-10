#!/usr/bin/env python3
"""
Експеримент: Вплив розміру бази даних на точність розпізнавання облич.

Перевіряє, як збільшення кількості осіб у базі впливає на якість
ідентифікації. Для кожного розміру бази виконується кілька повторів
з різними випадковими наборами осіб, після чого обчислюються середні
метрики та стандартні відхилення.

Датасет (flat, без підпапок):
  dataset/
    ivan_1.jpg
    ivan_2.jpg
    maria_1.jpeg
    petro_1.png

Ім'я особи визначається з імені файлу: все до останнього _.
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
import pandas as pd
from numpy.typing import NDArray
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
)

matplotlib.use("Agg")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


# ─── Dataclasses ───────────────────────────────────────────────────────


@dataclass
class FaceRecord:
    """Валідний запис обличчя з encoding."""

    person_id: str
    image_path: str
    encoding: NDArray[np.float64]


@dataclass
class SplitResult:
    """Результат розбиття на train/test для однієї особи."""

    train_encodings: list[NDArray[np.float64]]
    test_encodings: list[NDArray[np.float64]]
    train_paths: list[str]
    test_paths: list[str]


@dataclass
class RepeatMetrics:
    """Метрики одного повтору експерименту."""

    database_size: int
    repeat_id: int
    selected_people: int
    train_photos: int
    test_photos: int
    accuracy: float
    precision: float
    recall: float
    f1: float


@dataclass
class AggregatedMetrics:
    """Агреговані метрики для одного розміру бази."""

    database_size: int
    repeats: int
    train_photos_mean: float
    test_photos_mean: float
    accuracy_mean: float
    accuracy_std: float
    precision_mean: float
    precision_std: float
    recall_mean: float
    recall_std: float
    f1_mean: float
    f1_std: float


@dataclass
class DatasetStats:
    """Статистика обробки датасету."""

    total_images: int = 0
    valid_images: int = 0
    skipped_images: int = 0
    skipped_no_face: int = 0
    skipped_multi_face: int = 0
    skipped_error: int = 0
    excluded_people: int = 0
    valid_people: int = 0
    valid_people_ids: list[str] = field(default_factory=list)


# ─── Parsing ───────────────────────────────────────────────────────────


def extract_person_id(filename: str) -> str:
    """
    Витягує person_id з імені файлу.

    Формат: {person_id}_{number}.ext
    Наприклад: KyrulukM_3.jpeg → "KyrulukM"
    """
    stem = Path(filename).stem
    match = re.match(r"^(.+)_\d+$", stem)
    if match:
        return match.group(1)
    return stem


# ─── Dataset loading ───────────────────────────────────────────────────


def load_and_validate_dataset(
    dataset_dir: Path,
    detector_model: str = "hog",
) -> tuple[dict[str, list[FaceRecord]], DatasetStats]:
    """
    Зчитує всі зображення, знаходить обличчя, групує за person_id.

    Повертає dict {person_id: [FaceRecord, ...]} та DatasetStats.
    """
    if not dataset_dir.is_dir():
        logger.error("Директорія датасету не існує: %s", dataset_dir)
        sys.exit(1)

    image_files = sorted(
        f
        for f in dataset_dir.iterdir()
        if f.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if not image_files:
        logger.error("Не знайдено зображень у: %s", dataset_dir)
        sys.exit(1)

    stats = DatasetStats(total_images=len(image_files))
    grouped: dict[str, list[FaceRecord]] = {}

    for img_path in image_files:
        person_id = extract_person_id(img_path.name)

        try:
            image = face_recognition.load_image_file(str(img_path))
            face_locations = face_recognition.face_locations(image, model=detector_model)

            if len(face_locations) == 0:
                logger.warning("ПРОПУСК (0 облич): %s", img_path.name)
                stats.skipped_no_face += 1
                stats.skipped_images += 1
                continue

            if len(face_locations) > 1:
                logger.warning("ПРОПУСК (%d облич): %s", len(face_locations), img_path.name)
                stats.skipped_multi_face += 1
                stats.skipped_images += 1
                continue

            encodings = face_recognition.face_encodings(
                image, known_face_locations=face_locations
            )
            if not encodings:
                logger.warning("ПРОПУСК (не вдалося отримати encoding): %s", img_path.name)
                stats.skipped_error += 1
                stats.skipped_images += 1
                continue

            record = FaceRecord(
                person_id=person_id,
                image_path=str(img_path),
                encoding=np.array(encodings[0], dtype=np.float64),
            )
            grouped.setdefault(person_id, []).append(record)
            stats.valid_images += 1

        except Exception as exc:
            logger.warning("ПРОПУСК (помилка): %s — %s", img_path.name, exc)
            stats.skipped_error += 1
            stats.skipped_images += 1

    return grouped, stats


def filter_people(
    grouped: dict[str, list[FaceRecord]],
    min_photos: int = 3,
) -> tuple[dict[str, list[FaceRecord]], int]:
    """
    Залишає тільки осіб з мінімальною кількістю валідних фото.

    Повертає відфільтрований dict та кількість виключених осіб.
    """
    filtered = {}
    excluded = 0
    for person_id, records in grouped.items():
        if len(records) >= min_photos:
            filtered[person_id] = records
        else:
            logger.warning(
                "Виключено особу %s (%d фото, потрібно мінімум %d)",
                person_id,
                len(records),
                min_photos,
            )
            excluded += 1
    return filtered, excluded


# ─── Train/test split ──────────────────────────────────────────────────


def split_train_test(
    records: list[FaceRecord],
    random_state: int = 42,
) -> SplitResult:
    """
    Ділить фото особи на train/test.

    Правила:
      - >= 8 фото: 6 train, 2 test
      - 5–7 фото: 70% train, 30% test (мінімум 1 test)
      - 3–4 фото: 2 train, 1 test
    """
    rng = np.random.RandomState(random_state)
    indices = rng.permutation(len(records))

    n = len(records)
    if n >= 8:
        n_train, n_test = 6, 2
    elif n >= 5:
        n_test = max(1, int(round(n * 0.3)))
        n_train = n - n_test
    else:  # 3-4
        n_train, n_test = 2, 1

    train_idx = indices[:n_train]
    test_idx = indices[n_train : n_train + n_test]

    return SplitResult(
        train_encodings=[records[i].encoding for i in train_idx],
        test_encodings=[records[i].encoding for i in test_idx],
        train_paths=[records[i].image_path for i in train_idx],
        test_paths=[records[i].image_path for i in test_idx],
    )


# ─── Identification experiment ─────────────────────────────────────────


def run_identification(
    selected_person_ids: list[str],
    splits: dict[str, SplitResult],
    tolerance: float = 0.55,
) -> tuple[list[str], list[str]]:
    """
    Виконує ідентифікацію для обраного набору осіб.

    Для кожної особи обчислюється СЕРЕДНІЙ encoding (centroid)
    з train-фото. Test encoding порівнюється з centroid кожної особи.

    Повертає (y_true, y_pred) для обчислення метрик.
    """
    known_centroids: list[NDArray[np.float64]] = []
    known_person_ids: list[str] = []

    for pid in selected_person_ids:
        split = splits[pid]
        centroid = np.mean(split.train_encodings, axis=0)
        known_centroids.append(centroid)
        known_person_ids.append(pid)

    known_matrix = np.array(known_centroids, dtype=np.float64)

    y_true: list[str] = []
    y_pred: list[str] = []

    for pid in selected_person_ids:
        split = splits[pid]
        for test_enc in split.test_encodings:
            y_true.append(pid)

            distances = np.linalg.norm(known_matrix - test_enc, axis=1)
            min_idx = int(np.argmin(distances))
            min_dist = float(distances[min_idx])

            if min_dist < tolerance:
                y_pred.append(known_person_ids[min_idx])
            else:
                y_pred.append("unknown")

    return y_true, y_pred


def compute_sklearn_metrics(
    y_true: list[str],
    y_pred: list[str],
) -> tuple[float, float, float, float]:
    """Обчислює Accuracy, Precision, Recall, F1 (macro)."""
    acc = float(accuracy_score(y_true, y_pred))
    prec = float(
        precision_score(y_true, y_pred, average="macro", zero_division=0)
    )
    rec = float(recall_score(y_true, y_pred, average="macro", zero_division=0))
    f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
    return acc, prec, rec, f1


# ─── Experiment runner ─────────────────────────────────────────────────


def run_experiment(
    filtered_grouped: dict[str, list[FaceRecord]],
    database_sizes: list[int],
    tolerance: float = 0.55,
    repeats: int = 5,
    random_state: int = 42,
) -> tuple[list[RepeatMetrics], list[AggregatedMetrics]]:
    """
    Запускає експеримент для всіх розмірів бази.

    Повертає (raw_results, aggregated_results).
    """
    all_person_ids = sorted(filtered_grouped.keys())
    n_available = len(all_person_ids)

    # Попередньо обчислюємо splits для кожної особи
    splits: dict[str, SplitResult] = {}
    for pid in all_person_ids:
        splits[pid] = split_train_test(filtered_grouped[pid], random_state=random_state)

    raw_results: list[RepeatMetrics] = []

    for db_size in database_sizes:
        if db_size > n_available:
            logger.warning(
                "Пропуск database_size=%d (доступно лише %d осіб)",
                db_size,
                n_available,
            )
            continue

        logger.info("=== database_size=%d, repeats=%d ===", db_size, repeats)

        repeat_rng = np.random.RandomState(random_state + db_size)
        size_raw: list[RepeatMetrics] = []

        for rep in range(1, repeats + 1):
            # Випадковий вибір осіб
            selected = repeat_rng.choice(
                all_person_ids, size=db_size, replace=False
            ).tolist()

            y_true, y_pred = run_identification(selected, splits, tolerance=tolerance)

            if not y_true:
                logger.warning("Порожній test set для repeat %d, size %d", rep, db_size)
                continue

            acc, prec, rec, f1 = compute_sklearn_metrics(y_true, y_pred)

            n_train = sum(len(splits[pid].train_encodings) for pid in selected)
            n_test = sum(len(splits[pid].test_encodings) for pid in selected)

            rm = RepeatMetrics(
                database_size=db_size,
                repeat_id=rep,
                selected_people=db_size,
                train_photos=n_train,
                test_photos=n_test,
                accuracy=acc,
                precision=prec,
                recall=rec,
                f1=f1,
            )
            size_raw.append(rm)
            logger.info(
                "  repeat %d: acc=%.4f prec=%.4f rec=%.4f f1=%.4f",
                rep, acc, prec, rec, f1,
            )

        raw_results.extend(size_raw)

    # Агрегація
    aggregated = aggregate_metrics(raw_results)
    return raw_results, aggregated


def aggregate_metrics(
    raw: list[RepeatMetrics],
) -> list[AggregatedMetrics]:
    """Групує raw results за database_size та обчислює mean/std."""
    from collections import defaultdict

    groups: dict[int, list[RepeatMetrics]] = defaultdict(list)
    for r in raw:
        groups[r.database_size].append(r)

    aggregated: list[AggregatedMetrics] = []
    for db_size in sorted(groups.keys()):
        reps = groups[db_size]
        n = len(reps)
        if n == 0:
            continue

        acc_vals = [r.accuracy for r in reps]
        prec_vals = [r.precision for r in reps]
        rec_vals = [r.recall for r in reps]
        f1_vals = [r.f1 for r in reps]
        train_vals = [r.train_photos for r in reps]
        test_vals = [r.test_photos for r in reps]

        agg = AggregatedMetrics(
            database_size=db_size,
            repeats=n,
            train_photos_mean=float(np.mean(train_vals)),
            test_photos_mean=float(np.mean(test_vals)),
            accuracy_mean=float(np.mean(acc_vals)),
            accuracy_std=float(np.std(acc_vals, ddof=1) if n > 1 else 0.0),
            precision_mean=float(np.mean(prec_vals)),
            precision_std=float(np.std(prec_vals, ddof=1) if n > 1 else 0.0),
            recall_mean=float(np.mean(rec_vals)),
            recall_std=float(np.std(rec_vals, ddof=1) if n > 1 else 0.0),
            f1_mean=float(np.mean(f1_vals)),
            f1_std=float(np.std(f1_vals, ddof=1) if n > 1 else 0.0),
        )
        aggregated.append(agg)

    return aggregated


# ─── Saving results ────────────────────────────────────────────────────


def save_raw_csv(raw: list[RepeatMetrics], output_dir: Path) -> Path:
    """Зберігає детальні результати кожного повтору."""
    path = output_dir / "database_size_metrics_raw.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "database_size", "repeat_id", "selected_people",
            "train_photos", "test_photos",
            "accuracy", "precision", "recall", "f1",
        ])
        for r in raw:
            writer.writerow([
                r.database_size, r.repeat_id, r.selected_people,
                r.train_photos, r.test_photos,
                f"{r.accuracy:.6f}", f"{r.precision:.6f}",
                f"{r.recall:.6f}", f"{r.f1:.6f}",
            ])
    logger.info("Raw CSV збережено: %s", path)
    return path


def save_aggregated_csv(agg: list[AggregatedMetrics], output_dir: Path) -> Path:
    """Зберігає агреговані метрики."""
    path = output_dir / "database_size_metrics.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "database_size", "repeats",
            "train_photos_mean", "test_photos_mean",
            "accuracy_mean", "accuracy_std",
            "precision_mean", "precision_std",
            "recall_mean", "recall_std",
            "f1_mean", "f1_std",
        ])
        for a in agg:
            writer.writerow([
                a.database_size, a.repeats,
                f"{a.train_photos_mean:.2f}", f"{a.test_photos_mean:.2f}",
                f"{a.accuracy_mean:.6f}", f"{a.accuracy_std:.6f}",
                f"{a.precision_mean:.6f}", f"{a.precision_std:.6f}",
                f"{a.recall_mean:.6f}", f"{a.recall_std:.6f}",
                f"{a.f1_mean:.6f}", f"{a.f1_std:.6f}",
            ])
    logger.info("Aggregated CSV збережено: %s", path)
    return path


# ─── Plotting ──────────────────────────────────────────────────────────


def plot_accuracy(
    agg: list[AggregatedMetrics],
    output_dir: Path,
) -> Path:
    """Графік: вплив розміру бази на точність (accuracy)."""
    path = output_dir / "database_size_accuracy.png"

    sizes = [a.database_size for a in agg]
    means = [a.accuracy_mean * 100 for a in agg]
    stds = [a.accuracy_std * 100 for a in agg]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.errorbar(
        sizes, means, yerr=stds,
        fmt="o-", capsize=6, capthick=1.5,
        linewidth=2, markersize=8,
        label="Accuracy",
    )
    ax.axhline(y=95.0, color="red", linestyle="--", linewidth=1.5, label="Ціль = 95%")

    ax.set_xlabel("Кількість осіб у базі", fontsize=12)
    ax.set_ylabel("Accuracy, %", fontsize=12)
    ax.set_title("Вплив розміру бази на точність розпізнавання", fontsize=14)
    ax.legend(loc="best", fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.set_xticks(sizes)

    fig.tight_layout()
    fig.savefig(str(path), dpi=300)
    plt.close(fig)
    logger.info("Графік accuracy збережено: %s", path)
    return path


def plot_all_metrics(
    agg: list[AggregatedMetrics],
    output_dir: Path,
) -> Path:
    """Графік: всі метрики залежно від розміру бази."""
    path = output_dir / "database_size_metrics.png"

    sizes = [a.database_size for a in agg]

    fig, ax = plt.subplots(figsize=(12, 7))

    ax.plot(
        sizes, [a.accuracy_mean * 100 for a in agg],
        "o-", label="Accuracy", linewidth=2, markersize=7,
    )
    ax.plot(
        sizes, [a.precision_mean * 100 for a in agg],
        "s-", label="Precision", linewidth=2, markersize=7,
    )
    ax.plot(
        sizes, [a.recall_mean * 100 for a in agg],
        "^-", label="Recall", linewidth=2, markersize=7,
    )
    ax.plot(
        sizes, [a.f1_mean * 100 for a in agg],
        "d-", label="F1-score", linewidth=2, markersize=7,
    )

    ax.set_xlabel("Кількість осіб у базі", fontsize=12)
    ax.set_ylabel("Значення метрики, %", fontsize=12)
    ax.set_title("Метрики розпізнавання залежно від розміру бази", fontsize=14)
    ax.legend(loc="best", fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.set_xticks(sizes)

    fig.tight_layout()
    fig.savefig(str(path), dpi=300)
    plt.close(fig)
    logger.info("Графік метрик збережено: %s", path)
    return path


# ─── Report ────────────────────────────────────────────────────────────


def generate_report(
    stats: DatasetStats,
    tested_sizes: list[int],
    agg: list[AggregatedMetrics],
    output_dir: Path,
) -> Path:
    """Генерує текстовий звіт."""
    path = output_dir / "database_size_report.txt"

    lines: list[str] = []
    sep = "=" * 70

    lines.append(sep)
    lines.append("  ЗВІТ: Вплив розміру бази даних на точність розпізнавання облич")
    lines.append(sep)
    lines.append("")

    lines.append("1. СТАТИСТИКА ДАТАСЕТУ")
    lines.append(f"   Загальна кількість фото:         {stats.total_images}")
    lines.append(f"   Валідних фото:                   {stats.valid_images}")
    lines.append(f"   Пропущених фото:                 {stats.skipped_images}")
    lines.append(f"     — 0 облич:                     {stats.skipped_no_face}")
    lines.append(f"     — >1 облич:                    {stats.skipped_multi_face}")
    lines.append(f"     — помилки обробки:             {stats.skipped_error}")
    lines.append(f"   Кількість валідних осіб:         {stats.valid_people}")
    lines.append(f"   Виключено осіб (<3 фото):        {stats.excluded_people}")
    lines.append("")

    lines.append("2. ТЕСТОВАНІ РОЗМІРИ БАЗИ")
    lines.append(f"   Протестовані database_sizes:     {tested_sizes}")
    lines.append("")

    lines.append("3. РЕЗУЛЬТАТИ")
    lines.append("")
    header = (
        f"  {'Size':>6}  {'Repeats':>8}  "
        f"{'Acc mean':>10}  {'Acc std':>9}  "
        f"{'Prec mean':>10}  {'Prec std':>9}  "
        f"{'Rec mean':>10}  {'Rec std':>9}  "
        f"{'F1 mean':>10}  {'F1 std':>9}"
    )
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))

    for a in agg:
        row = (
            f"  {a.database_size:>6}  {a.repeats:>8}  "
            f"{a.accuracy_mean * 100:>9.2f}%  {a.accuracy_std * 100:>8.2f}%  "
            f"{a.precision_mean * 100:>9.2f}%  {a.precision_std * 100:>8.2f}%  "
            f"{a.recall_mean * 100:>9.2f}%  {a.recall_std * 100:>8.2f}%  "
            f"{a.f1_mean * 100:>9.2f}%  {a.f1_std * 100:>8.2f}%"
        )
        lines.append(row)

    lines.append("")
    lines.append("4. ВИСНОВОК")
    lines.append("")

    if agg:
        best_acc = max(agg, key=lambda a: a.accuracy_mean)
        worst_acc = min(agg, key=lambda a: a.accuracy_mean)

        lines.append(
            f"   Найкраща точність: {best_acc.accuracy_mean * 100:.2f}% "
            f"(база = {best_acc.database_size} осіб)"
        )
        lines.append(
            f"   Найнижча точність: {worst_acc.accuracy_mean * 100:.2f}% "
            f"(база = {worst_acc.database_size} осіб)"
        )
        lines.append("")

        if best_acc.accuracy_mean >= 0.95:
            lines.append(
                "   Система зберігає точність не нижче 95% "
                "при протестованих розмірах бази."
            )
        else:
            lines.append(
                "   УВАГА: точність нижче 95% при деяких розмірах бази."
            )
            lines.append("")
            lines.append("   Можливі причини:")
            lines.append("   - мало фото на людину для якісного навчання;")
            lines.append("   - погане освітлення на фотографіях;")
            lines.append("   - різні ракурси та вирази обличчя;")
            lines.append("   - схожі обличчя серед різних осіб;")
            lines.append("   - низька роздільна здатність або якість фото;")
            lines.append("   - можливо, потрібно підібрати інший tolerance.")

        lines.append("")

        if len(agg) >= 2:
            trend = "зростає" if agg[-1].accuracy_mean > agg[0].accuracy_mean else "спадає"
            lines.append(
                f"   Тренд: при збільшенні бази точність {trend} "
                f"(з {agg[0].accuracy_mean * 100:.2f}% до {agg[-1].accuracy_mean * 100:.2f}%)."
            )
    else:
        lines.append("   Експеримент не виконано (недостатньо даних).")

    lines.append("")
    lines.append(sep)

    report_text = "\n".join(lines)
    path.write_text(report_text, encoding="utf-8")
    logger.info("Звіт збережено: %s", path)
    return path


# ─── CLI ───────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Експеримент: вплив розміру бази даних на точність розпізнавання облич"
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="./dataset",
        help="Шлях до папки з фото",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./output",
        help="Шлях до папки для результатів",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.55,
        help="Поріг евклідової відстані для ідентифікації (default: 0.55)",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=5,
        help="Кількість повторів для кожного розміру бази (default: 5)",
    )
    parser.add_argument(
        "--sizes",
        type=int,
        nargs="+",
        default=[5, 10, 20],
        help="Розміри бази для тестування (default: 5 10 20)",
    )
    parser.add_argument(
        "--detector-model",
        type=str,
        default="hog",
        choices=["hog", "cnn"],
        help="Модель детектора облич (default: hog)",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Фіксований seed для відтворюваності (default: 42)",
    )
    return parser.parse_args()


# ─── Main ──────────────────────────────────────────────────────────────


def main() -> None:
    args = parse_args()

    dataset_dir = Path(args.dataset)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Датасет: %s", dataset_dir.resolve())
    logger.info("Вивід:   %s", output_dir.resolve())
    logger.info("Tolerance:  %.2f", args.tolerance)
    logger.info("Repeats:    %d", args.repeats)
    logger.info("Sizes:      %s", args.sizes)
    logger.info("Detector:   %s", args.detector_model)
    logger.info("Random state: %d", args.random_state)
    logger.info("")

    # 1. Завантаження та валідація
    logger.info("--- Завантаження датасету ---")
    grouped, stats = load_and_validate_dataset(dataset_dir, args.detector_model)
    logger.info("Знайдено %d фото, валідних %d, пропущено %d",
                stats.total_images, stats.valid_images, stats.skipped_images)

    # 2. Фільтрація осіб
    logger.info("--- Фільтрація осіб (мін. 3 фото) ---")
    filtered, excluded = filter_people(grouped, min_photos=3)
    stats.excluded_people = excluded
    stats.valid_people = len(filtered)
    stats.valid_people_ids = sorted(filtered.keys())
    logger.info("Валідних осіб: %d, виключено: %d", stats.valid_people, excluded)

    if stats.valid_people < 2:
        logger.error("Потрібно мінімум 2 валідні особи для експерименту")
        sys.exit(1)

    # 3. Визначаємо реальні розміри для тестування
    tested_sizes = [s for s in args.sizes if s <= stats.valid_people]
    if not tested_sizes:
        logger.error(
            "Жоден із запитаних розмірів бази не підходить "
            "(валідних осіб: %d, запитані: %s)",
            stats.valid_people, args.sizes,
        )
        sys.exit(1)

    logger.info("Реальні розміри для тестування: %s", tested_sizes)
    logger.info("")

    # 4. Запуск експерименту
    logger.info("--- Запуск експерименту ---")
    raw, aggregated = run_experiment(
        filtered,
        database_sizes=tested_sizes,
        tolerance=args.tolerance,
        repeats=args.repeats,
        random_state=args.random_state,
    )

    if not aggregated:
        logger.error("Експеримент не повернув результатів")
        sys.exit(1)

    # 5. Збереження CSV
    logger.info("--- Збереження результатів ---")
    save_raw_csv(raw, output_dir)
    save_aggregated_csv(aggregated, output_dir)

    # 6. Графіки
    logger.info("--- Побудова графіків ---")
    plot_accuracy(aggregated, output_dir)
    plot_all_metrics(aggregated, output_dir)

    # 7. Звіт
    logger.info("--- Генерація звіту ---")
    generate_report(stats, tested_sizes, aggregated, output_dir)

    logger.info("")
    logger.info("Експеримент завершено. Результати у: %s", output_dir.resolve())

    # Друк звіту в консоль
    report_path = output_dir / "database_size_report.txt"
    print("\n" + report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
