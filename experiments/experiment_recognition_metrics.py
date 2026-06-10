#!/usr/bin/env python3
"""
Експеримент: Основні метрики якості та безпеки системи розпізнавання облич.

Обчислює:
  - Accuracy, Precision, Recall, F1-score (macro)
  - FAR (False Acceptance Rate)
  - FRR (False Rejection Rate)
  - Confusion matrix
  - Classification report

Датасет (flat, без підпапок):
  dataset/
    KyrulukM_1.jpeg
    KyrulukM_2.jpeg
    Martsinkiv_1.jpeg
    ...

Ім'я особи визначається з імені файлу: все до останнього _.
"""

import argparse
import logging
import re
import sys
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

import face_recognition
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from numpy.typing import NDArray
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
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
    """Валідний запис обличчя."""

    person_id: str
    image_path: str
    filename: str
    encoding: NDArray[np.float64]


@dataclass
class SplitResult:
    """Розбиття на train/test для однієї особи."""

    train_records: list[FaceRecord]
    test_records: list[FaceRecord]


@dataclass
class PairData:
    """Дані пари для FAR/FRR."""

    image_1: str
    image_2: str
    person_1: str
    person_2: str
    pair_type: str  # "same" або "different"
    distance: float
    tolerance: float
    predicted: str  # "same" або "different"
    result: str  # "TP", "FN", "TN", "FP"


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
    """Витягує person_id з імені файлу."""
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
    """Зчитує зображення, знаходить обличчя, групує за person_id."""
    if not dataset_dir.is_dir():
        logger.error("Директорія датасету не існує: %s", dataset_dir)
        sys.exit(1)

    image_files = sorted(
        f for f in dataset_dir.iterdir()
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
                logger.warning("ПРОПУСК (encoding failed): %s", img_path.name)
                stats.skipped_error += 1
                stats.skipped_images += 1
                continue

            record = FaceRecord(
                person_id=person_id,
                image_path=str(img_path),
                filename=img_path.name,
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
    """Залишає тільки осіб з мінімальною кількістю валідних фото."""
    filtered = {}
    excluded = 0
    for person_id, records in grouped.items():
        if len(records) >= min_photos:
            filtered[person_id] = records
        else:
            logger.warning(
                "Виключено особу %s (%d фото, потрібно мінімум %d)",
                person_id, len(records), min_photos,
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
    >=8: 6/2, 5-7: 70/30, 3-4: 2/1
    """
    rng = np.random.RandomState(random_state)
    indices = rng.permutation(len(records))
    n = len(records)

    if n >= 8:
        n_train, n_test = 6, 2
    elif n >= 5:
        n_test = max(1, int(round(n * 0.3)))
        n_train = n - n_test
    else:
        n_train, n_test = 2, 1

    train_idx = indices[:n_train]
    test_idx = indices[n_train : n_train + n_test]

    return SplitResult(
        train_records=[records[i] for i in train_idx],
        test_records=[records[i] for i in test_idx],
    )


# ─── Identification ────────────────────────────────────────────────────


def run_identification(
    filtered_grouped: dict[str, list[FaceRecord]],
    splits: dict[str, SplitResult],
    tolerance: float = 0.55,
) -> tuple[list[str], list[str]]:
    """
    Виконує ідентифікацію для ВСІХ валідних осіб.
    Використовує MEAN encoding (centroid) для кожної особи.
    """
    all_person_ids = sorted(filtered_grouped.keys())

    known_centroids: list[NDArray[np.float64]] = []
    known_person_ids: list[str] = []

    for pid in all_person_ids:
        split = splits[pid]
        centroid = np.mean([r.encoding for r in split.train_records], axis=0)
        known_centroids.append(centroid)
        known_person_ids.append(pid)

    known_matrix = np.array(known_centroids, dtype=np.float64)

    y_true: list[str] = []
    y_pred: list[str] = []

    for pid in all_person_ids:
        split = splits[pid]
        for rec in split.test_records:
            y_true.append(pid)
            distances = np.linalg.norm(known_matrix - rec.encoding, axis=1)
            min_idx = int(np.argmin(distances))
            min_dist = float(distances[min_idx])

            if min_dist < tolerance:
                y_pred.append(known_person_ids[min_idx])
            else:
                y_pred.append("unknown")

    return y_true, y_pred


# ─── Pair generation for FAR/FRR ───────────────────────────────────────


def generate_pairs(
    filtered_grouped: dict[str, list[FaceRecord]],
    tolerance: float = 0.55,
    max_different_pairs: int = 5000,
    random_state: int = 42,
) -> list[PairData]:
    """Формує same/different pairs для розрахунку FAR/FRR."""
    rng = np.random.RandomState(random_state)
    pairs: list[PairData] = []

    all_pids = sorted(filtered_grouped.keys())

    # SAME PERSON PAIRS
    for pid in all_pids:
        records = filtered_grouped[pid]
        for i in range(len(records)):
            for j in range(i + 1, len(records)):
                dist = float(np.linalg.norm(records[i].encoding - records[j].encoding))
                predicted = "same" if dist < tolerance else "different"
                result = "TP" if predicted == "same" else "FN"
                pairs.append(PairData(
                    image_1=records[i].filename,
                    image_2=records[j].filename,
                    person_1=pid,
                    person_2=pid,
                    pair_type="same",
                    distance=dist,
                    tolerance=tolerance,
                    predicted=predicted,
                    result=result,
                ))

    # DIFFERENT PERSON PAIRS
    diff_candidates: list[tuple[FaceRecord, FaceRecord]] = []
    for i in range(len(all_pids)):
        for j in range(i + 1, len(all_pids)):
            pid_a = all_pids[i]
            pid_b = all_pids[j]
            for rec_a in filtered_grouped[pid_a]:
                for rec_b in filtered_grouped[pid_b]:
                    diff_candidates.append((rec_a, rec_b))

    if len(diff_candidates) > max_different_pairs:
        diff_candidates = rng.choice(
            diff_candidates, size=max_different_pairs, replace=False
        ).tolist()

    for rec_a, rec_b in diff_candidates:
        dist = float(np.linalg.norm(rec_a.encoding - rec_b.encoding))
        predicted = "same" if dist < tolerance else "different"
        result = "FP" if predicted == "same" else "TN"
        pairs.append(PairData(
            image_1=rec_a.filename,
            image_2=rec_b.filename,
            person_1=rec_a.person_id,
            person_2=rec_b.person_id,
            pair_type="different",
            distance=dist,
            tolerance=tolerance,
            predicted=predicted,
            result=result,
        ))

    return pairs


# ─── FAR / FRR computation ─────────────────────────────────────────────


def compute_far_frr(
    pairs: list[PairData],
) -> dict:
    """Обчислює FAR та FRR з пар."""
    same_pairs = [p for p in pairs if p.pair_type == "same"]
    diff_pairs = [p for p in pairs if p.pair_type == "different"]

    tp_pair = sum(1 for p in same_pairs if p.result == "TP")
    fn_pair = sum(1 for p in same_pairs if p.result == "FN")
    tn_pair = sum(1 for p in diff_pairs if p.result == "TN")
    fp_pair = sum(1 for p in diff_pairs if p.result == "FP")

    total_same = tp_pair + fn_pair
    total_diff = fp_pair + tn_pair

    frr = fn_pair / total_same if total_same > 0 else 0.0
    far = fp_pair / total_diff if total_diff > 0 else 0.0

    return {
        "same_pairs": len(same_pairs),
        "different_pairs": len(diff_pairs),
        "TP_pair": tp_pair,
        "FN_pair": fn_pair,
        "TN_pair": tn_pair,
        "FP_pair": fp_pair,
        "FAR": far,
        "FAR_percent": far * 100,
        "FRR": frr,
        "FRR_percent": frr * 100,
    }


# ─── Plotting ──────────────────────────────────────────────────────────


def plot_confusion_matrix(
    y_true: list[str],
    y_pred: list[str],
    output_path: Path,
) -> None:
    """Будує heatmap confusion matrix."""
    labels = sorted(set(y_true) | set(y_pred))
    cm = confusion_matrix(y_true, y_pred, labels=labels)

    n = len(labels)
    fig, ax = plt.subplots(figsize=(max(8, n * 0.8), max(7, n * 0.7)))

    im = ax.imshow(cm, interpolation="nearest", cmap=plt.cm.Blues)
    ax.set_title("Матриця помилок системи розпізнавання облич", fontsize=13)
    ax.set_xlabel("Передбачений клас", fontsize=11)
    ax.set_ylabel("Реальний клас", fontsize=11)

    tick_marks = np.arange(n)
    rotation = 45 if n > 6 else 0
    ax.set_xticks(tick_marks)
    ax.set_xticklabels(labels, rotation=rotation, ha="right", fontsize=8)
    ax.set_yticks(tick_marks)
    ax.set_yticklabels(labels, fontsize=8)

    thresh = cm.max() / 2.0
    for i in range(n):
        for j in range(n):
            color = "white" if cm[i, j] > thresh else "black"
            ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                    color=color, fontsize=9, fontweight="bold")

    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(str(output_path), dpi=300)
    plt.close(fig)
    logger.info("Confusion matrix PNG: %s", output_path)


def plot_classification_metrics_bar(
    accuracy: float,
    precision: float,
    recall: float,
    f1: float,
    output_path: Path,
) -> None:
    """Bar chart для Accuracy/Precision/Recall/F1."""
    names = ["Accuracy", "Precision", "Recall", "F1-score"]
    values = [accuracy * 100, precision * 100, recall * 100, f1 * 100]
    colors = ["#2196F3", "#4CAF50", "#FF9800", "#E91E63"]

    fig, ax = plt.subplots(figsize=(8, 6))
    bars = ax.bar(names, values, color=colors, width=0.5, edgecolor="black", linewidth=0.5)

    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"{val:.1f}%", ha="center", va="bottom", fontsize=11, fontweight="bold")

    ax.set_ylabel("Значення, %", fontsize=12)
    ax.set_title("Загальні метрики якості розпізнавання", fontsize=14)
    ax.set_ylim(0, max(values) * 1.15)
    ax.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(str(output_path), dpi=300)
    plt.close(fig)
    logger.info("Classification metrics bar PNG: %s", output_path)


def plot_distance_distribution(
    pairs: list[PairData],
    tolerance: float,
    output_path: Path,
) -> None:
    """Гістограма відстаней same vs different."""
    same_dists = [p.distance for p in pairs if p.pair_type == "same"]
    diff_dists = [p.distance for p in pairs if p.pair_type == "different"]

    fig, ax = plt.subplots(figsize=(10, 6))

    if same_dists:
        ax.hist(same_dists, bins=30, alpha=0.6, label="Одна особа", color="#2196F3")
    if diff_dists:
        ax.hist(diff_dists, bins=30, alpha=0.6, label="Різні особи", color="#E91E63")

    ax.axvline(x=tolerance, color="red", linestyle="--", linewidth=1.5,
               label=f"Tolerance = {tolerance}")

    ax.set_xlabel("Евклідова відстань між 128D векторами", fontsize=12)
    ax.set_ylabel("Кількість пар", fontsize=12)
    ax.set_title("Розподіл відстаней між біометричними векторами", fontsize=14)
    ax.legend(loc="upper right", fontsize=11)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(str(output_path), dpi=300)
    plt.close(fig)
    logger.info("Distance distribution PNG: %s", output_path)


def plot_far_frr_bar(
    far_pct: float,
    frr_pct: float,
    output_path: Path,
) -> None:
    """Bar chart для FAR/FRR."""
    names = ["FAR", "FRR"]
    values = [far_pct, frr_pct]
    colors = ["#F44336", "#FF9800"]

    fig, ax = plt.subplots(figsize=(6, 6))
    bars = ax.bar(names, values, color=colors, width=0.4, edgecolor="black", linewidth=0.5)

    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                f"{val:.2f}%", ha="center", va="bottom", fontsize=12, fontweight="bold")

    ax.set_ylabel("Значення, %", fontsize=12)
    ax.set_title("Метрики безпеки FAR та FRR", fontsize=14)
    ax.set_ylim(0, max(values) * 1.2 if max(values) > 0 else 10)
    ax.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(str(output_path), dpi=300)
    plt.close(fig)
    logger.info("FAR/FRR bar PNG: %s", output_path)


# ─── Report generation ─────────────────────────────────────────────────


def generate_report(
    stats: DatasetStats,
    detector_model: str,
    tolerance: float,
    random_state: int,
    total_test: int,
    correct: int,
    wrong: int,
    unknown_count: int,
    accuracy: float,
    precision: float,
    recall: float,
    f1: float,
    far_frr: dict,
    output_dir: Path,
) -> Path:
    """Генерує текстовий звіт."""
    path = output_dir / "recognition_metrics_report.txt"
    lines: list[str] = []
    sep = "=" * 70

    lines.append(sep)
    lines.append("  ЗВІТ: Метрики якості та безпеки системи розпізнавання облич")
    lines.append(sep)
    lines.append("")

    # 1. Статистика
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

    # 2. Параметри
    lines.append("2. ПАРАМЕТРИ ЕКСПЕРИМЕНТУ")
    lines.append(f"   Detector model:                  {detector_model}")
    lines.append(f"   Tolerance:                       {tolerance}")
    lines.append(f"   Random state:                    {random_state}")
    lines.append("")

    # 3. Метрики класифікації
    lines.append("3. МЕТРИКИ КЛАСИФІКАЦІЇ")
    lines.append(f"   Кількість test-зображень:        {total_test}")
    lines.append(f"   Правильних передбачень:          {correct}")
    lines.append(f"   Неправильних передбачень:        {wrong}")
    lines.append(f"   'unknown' передбачень:           {unknown_count}")
    lines.append("")
    lines.append(f"   Accuracy:                        {accuracy * 100:.2f}%")
    lines.append(f"   Precision (macro):               {precision * 100:.2f}%")
    lines.append(f"   Recall (macro):                  {recall * 100:.2f}%")
    lines.append(f"   F1-score (macro):                {f1 * 100:.2f}%")
    lines.append("")

    # 4. FAR/FRR
    lines.append("4. МЕТРИКИ БЕЗПЕКИ (FAR / FRR)")
    lines.append(f"   Same person pairs:               {far_frr['same_pairs']}")
    lines.append(f"   Different person pairs:          {far_frr['different_pairs']}")
    lines.append(f"   TP (правильно прийнято):         {far_frr['TP_pair']}")
    lines.append(f"   FN (помилково відхилено):        {far_frr['FN_pair']}")
    lines.append(f"   TN (правильно відхилено):        {far_frr['TN_pair']}")
    lines.append(f"   FP (помилково прийнято):         {far_frr['FP_pair']}")
    lines.append(f"   FAR:                             {far_frr['FAR_percent']:.2f}%")
    lines.append(f"   FRR:                             {far_frr['FRR_percent']:.2f}%")
    lines.append("")

    # 5. Висновок
    lines.append("5. ВИСНОВОК")
    lines.append("")

    if accuracy >= 0.90:
        lines.append("   Accuracy є високою (>= 90%), що свідчить про")
        lines.append("   загалом хорошу якість розпізнавання системи.")
    elif accuracy >= 0.70:
        lines.append("   Accuracy є помірною (70-90%), система працює")
        lines.append("   прийнятно, але потребує налаштування параметрів.")
    else:
        lines.append("   Accuracy є низькою (< 70%), що вказує на")
        lines.append("   серйозні проблеми з якістю розпізнавання.")
    lines.append("")

    if unknown_count > 0:
        unknown_pct = unknown_count / total_test * 100 if total_test > 0 else 0
        lines.append(f"   'unknown' predictions: {unknown_count}/{total_test} ({unknown_pct:.1f}%).")
        if unknown_pct > 20:
            lines.append("   Значна частина тестів класифікується як 'unknown',")
            lines.append("   що може свідчити про занадто суворий tolerance.")
        elif unknown_pct > 5:
            lines.append("   Помірна кількість 'unknown' передбачень.")
        else:
            lines.append("   Кількість 'unknown' передбачень є незначною.")
    else:
        lines.append("   'unknown' передбачень немає.")
    lines.append("")

    if far_frr["FAR_percent"] < 5:
        lines.append(f"   FAR = {far_frr['FAR_percent']:.2f}% — низький, система рідко")
        lines.append("   плутає різних людей.")
    elif far_frr["FAR_percent"] < 15:
        lines.append(f"   FAR = {far_frr['FAR_percent']:.2f}% — помірний, є помилкові")
        lines.append("   спрацювання для різних осіб.")
    else:
        lines.append(f"   FAR = {far_frr['FAR_percent']:.2f}% — високий, система часто")
        lines.append("   плутає різних людей.")
    lines.append("")

    if far_frr["FRR_percent"] < 10:
        lines.append(f"   FRR = {far_frr['FRR_percent']:.2f}% — низький, система рідко")
        lines.append("   відхиляє фото тієї самої особи.")
    elif far_frr["FRR_percent"] < 30:
        lines.append(f"   FRR = {far_frr['FRR_percent']:.2f}% — помірний, частина фото")
        lines.append("   тієї самої особи відхиляється.")
    else:
        lines.append(f"   FRR = {far_frr['FRR_percent']:.2f}% — високий, система часто")
        lines.append("   відхиляє фото тієї самої особи.")
    lines.append("")

    lines.append("   Компроміс між FAR та FRR:")
    lines.append("   - Зниження tolerance зменшує FAR, але збільшує FRR;")
    lines.append("   - Підвищення tolerance зменшує FRR, але збільшує FAR.")

    if far_frr["FRR_percent"] > far_frr["FAR_percent"] * 2:
        lines.append("   На цьому датасеті FRR значно перевищує FAR,")
        lines.append("   що свідчить про суворий tolerance — система")
        lines.append("   частіше відхиляє правильні збіги, ніж приймає")
        lines.append("   помилкові.")
    elif far_frr["FAR_percent"] > far_frr["FRR_percent"] * 2:
        lines.append("   На цьому датасеті FAR значно перевищує FRR,")
        lines.append("   що свідчить про м'який tolerance — система")
        lines.append("   частіше приймає помилкові збіги.")
    else:
        lines.append("   На цьому датасеті FAR та FRR є збалансованими.")

    lines.append("")
    lines.append(sep)

    report_text = "\n".join(lines)
    path.write_text(report_text, encoding="utf-8")
    logger.info("Звіт збережено: %s", path)
    return path


# ─── CLI ───────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Експеримент: Метрики якості та безпеки розпізнавання облич"
    )
    parser.add_argument("--dataset", type=str, default="./dataset", help="Шлях до папки з фото")
    parser.add_argument("--output", type=str, default="./output", help="Шлях до папки для результатів")
    parser.add_argument("--detector-model", type=str, default="hog", choices=["hog", "cnn"], help="Detector")
    parser.add_argument("--tolerance", type=float, default=0.55, help="Поріг евклідової відстані (default: 0.55)")
    parser.add_argument("--random-state", type=int, default=42, help="Seed (default: 42)")
    parser.add_argument("--max-different-pairs", type=int, default=5000, help="Макс. different pairs (default: 5000)")
    return parser.parse_args()


# ─── Main ──────────────────────────────────────────────────────────────


def main() -> None:
    args = parse_args()

    dataset_dir = Path(args.dataset)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Датасет: %s", dataset_dir.resolve())
    logger.info("Вивід:   %s", output_dir.resolve())
    logger.info("Detector:   %s", args.detector_model)
    logger.info("Tolerance:  %.2f", args.tolerance)
    logger.info("Random state: %d", args.random_state)
    logger.info("")

    # 1. Завантаження
    logger.info("--- Завантаження датасету ---")
    grouped, stats = load_and_validate_dataset(dataset_dir, args.detector_model)
    logger.info("Знайдено %d фото, валідних %d, пропущено %d",
                stats.total_images, stats.valid_images, stats.skipped_images)

    # 2. Фільтрація
    logger.info("--- Фільтрація осіб (мін. 3 фото) ---")
    filtered, excluded = filter_people(grouped, min_photos=3)
    stats.excluded_people = excluded
    stats.valid_people = len(filtered)
    stats.valid_people_ids = sorted(filtered.keys())
    logger.info("Валідних осіб: %d, виключено: %d", stats.valid_people, excluded)

    if stats.valid_people < 2:
        logger.error("Потрібно мінімум 2 валідні особи")
        sys.exit(1)

    # 3. Train/test split
    logger.info("--- Train/test split ---")
    splits: dict[str, SplitResult] = {}
    for pid in stats.valid_people_ids:
        splits[pid] = split_train_test(filtered[pid], random_state=args.random_state)

    total_train = sum(len(s.train_records) for s in splits.values())
    total_test = sum(len(s.test_records) for s in splits.values())
    logger.info("Train: %d, Test: %d", total_train, total_test)
    logger.info("")

    # 4. Ідентифікація
    logger.info("--- Ідентифікація ---")
    y_true, y_pred = run_identification(filtered, splits, tolerance=args.tolerance)

    # Метрики класифікації
    accuracy = float(accuracy_score(y_true, y_pred))
    precision = float(precision_score(y_true, y_pred, average="macro", zero_division=0))
    recall = float(recall_score(y_true, y_pred, average="macro", zero_division=0))
    f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))

    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    wrong = sum(1 for t, p in zip(y_true, y_pred) if t != p and p != "unknown")
    unknown_count = sum(1 for p in y_pred if p == "unknown")

    logger.info("Accuracy:  %.4f", accuracy)
    logger.info("Precision: %.4f", precision)
    logger.info("Recall:    %.4f", recall)
    logger.info("F1-score:  %.4f", accuracy)
    logger.info("Correct: %d, Wrong: %d, Unknown: %d", correct, wrong, unknown_count)
    logger.info("")

    # Classification report dict
    all_labels = sorted(set(y_true) | set(y_pred))
    report_dict = classification_report(
        y_true, y_pred, labels=all_labels,
        output_dict=True, zero_division=0,
    )

    # 5. FAR/FRR pairs
    logger.info("--- Генерація пар для FAR/FRR ---")
    pairs = generate_pairs(
        filtered,
        tolerance=args.tolerance,
        max_different_pairs=args.max_different_pairs,
        random_state=args.random_state,
    )
    logger.info("Same pairs: %d, Different pairs: %d",
                sum(1 for p in pairs if p.pair_type == "same"),
                sum(1 for p in pairs if p.pair_type == "different"))

    far_frr = compute_far_frr(pairs)
    logger.info("FAR: %.2f%%, FRR: %.2f%%", far_frr["FAR_percent"], far_frr["FRR_percent"])
    logger.info("")

    # ─── SAVE FILES ────────────────────────────────────────────────────

    # classification_metrics_summary.csv
    metrics_summary = pd.DataFrame([{
        "tolerance": args.tolerance,
        "total_test_images": len(y_true),
        "correct_predictions": correct,
        "wrong_predictions": wrong,
        "unknown_predictions": unknown_count,
        "accuracy": f"{accuracy:.6f}",
        "precision_macro": f"{precision:.6f}",
        "recall_macro": f"{recall:.6f}",
        "f1_macro": f"{f1:.6f}",
    }])
    metrics_summary.to_csv(output_dir / "classification_metrics_summary.csv",
                           sep=";", index=False, encoding="utf-8")
    logger.info("Saved: classification_metrics_summary.csv")

    # classification_report.csv
    cr_rows = []
    for label in all_labels:
        if label in report_dict and isinstance(report_dict[label], dict):
            d = report_dict[label]
            cr_rows.append({
                "class_name": label,
                "precision": f"{d.get('precision', 0):.6f}",
                "recall": f"{d.get('recall', 0):.6f}",
                "f1_score": f"{d.get('f1-score', 0):.6f}",
                "support": int(d.get("support", 0)),
            })
    # accuracy row
    if "accuracy" in report_dict and isinstance(report_dict["accuracy"], float):
        cr_rows.append({
            "class_name": "accuracy",
            "precision": f"{report_dict['accuracy']:.6f}",
            "recall": f"{report_dict['accuracy']:.6f}",
            "f1_score": f"{report_dict['accuracy']:.6f}",
            "support": len(y_true),
        })
    for key in ("macro avg", "weighted avg"):
        if key in report_dict and isinstance(report_dict[key], dict):
            d = report_dict[key]
            cr_rows.append({
                "class_name": key,
                "precision": f"{d.get('precision', 0):.6f}",
                "recall": f"{d.get('recall', 0):.6f}",
                "f1_score": f"{d.get('f1-score', 0):.6f}",
                "support": int(d.get("support", 0)),
            })
    pd.DataFrame(cr_rows).to_csv(output_dir / "classification_report.csv",
                                  sep=";", index=False, encoding="utf-8")
    logger.info("Saved: classification_report.csv")

    # confusion_matrix.csv
    cm = confusion_matrix(y_true, y_pred, labels=all_labels)
    cm_df = pd.DataFrame(cm, index=all_labels, columns=all_labels)
    cm_df.index.name = "actual"
    cm_df.columns.name = "predicted"
    cm_df.to_csv(output_dir / "confusion_matrix.csv", sep=";", encoding="utf-8")
    logger.info("Saved: confusion_matrix.csv")

    # pair_distances_far_frr.csv
    pair_rows = []
    for p in pairs:
        pair_rows.append({
            "image_1": p.image_1,
            "image_2": p.image_2,
            "person_1": p.person_1,
            "person_2": p.person_2,
            "pair_type": p.pair_type,
            "distance": f"{p.distance:.6f}",
            "tolerance": p.tolerance,
            "predicted": p.predicted,
            "result": p.result,
        })
    pd.DataFrame(pair_rows).to_csv(output_dir / "pair_distances_far_frr.csv",
                                    sep=";", index=False, encoding="utf-8")
    logger.info("Saved: pair_distances_far_frr.csv (%d rows)", len(pair_rows))

    # far_frr_summary.csv
    far_frr_df = pd.DataFrame([{
        "tolerance": args.tolerance,
        "same_pairs": far_frr["same_pairs"],
        "different_pairs": far_frr["different_pairs"],
        "TP_pair": far_frr["TP_pair"],
        "FN_pair": far_frr["FN_pair"],
        "TN_pair": far_frr["TN_pair"],
        "FP_pair": far_frr["FP_pair"],
        "FAR": f"{far_frr['FAR']:.6f}",
        "FAR_percent": f"{far_frr['FAR_percent']:.2f}",
        "FRR": f"{far_frr['FRR']:.6f}",
        "FRR_percent": f"{far_frr['FRR_percent']:.2f}",
    }])
    far_frr_df.to_csv(output_dir / "far_frr_summary.csv",
                      sep=";", index=False, encoding="utf-8")
    logger.info("Saved: far_frr_summary.csv")

    # recognition_metrics_summary.csv (об'єднаний)
    combined = pd.DataFrame([{
        "tolerance": args.tolerance,
        "total_test_images": len(y_true),
        "accuracy": f"{accuracy:.6f}",
        "precision_macro": f"{precision:.6f}",
        "recall_macro": f"{recall:.6f}",
        "f1_macro": f"{f1:.6f}",
        "same_pairs": far_frr["same_pairs"],
        "different_pairs": far_frr["different_pairs"],
        "FAR_percent": f"{far_frr['FAR_percent']:.2f}",
        "FRR_percent": f"{far_frr['FRR_percent']:.2f}",
        "unknown_predictions": unknown_count,
    }])
    combined.to_csv(output_dir / "recognition_metrics_summary.csv",
                    sep=";", index=False, encoding="utf-8")
    logger.info("Saved: recognition_metrics_summary.csv")

    # ─── PLOTS ─────────────────────────────────────────────────────────

    logger.info("--- Побудова графіків ---")
    plot_confusion_matrix(y_true, y_pred, output_dir / "confusion_matrix.png")
    plot_classification_metrics_bar(accuracy, precision, recall, f1,
                                     output_dir / "classification_metrics_bar.png")
    plot_distance_distribution(pairs, args.tolerance,
                                output_dir / "distance_distribution_far_frr.png")
    plot_far_frr_bar(far_frr["FAR_percent"], far_frr["FRR_percent"],
                      output_dir / "far_frr_bar.png")

    # ─── REPORT ────────────────────────────────────────────────────────

    logger.info("--- Генерація звіту ---")
    generate_report(
        stats, args.detector_model, args.tolerance, args.random_state,
        len(y_true), correct, wrong, unknown_count,
        accuracy, precision, recall, f1,
        far_frr, output_dir,
    )

    # ─── CONSOLE OUTPUT ────────────────────────────────────────────────

    sep = "=" * 60
    print()
    print(sep)
    print("  RECOGNITION METRICS EXPERIMENT")
    print(sep)
    print()
    print("Dataset:")
    print(f"  Total photos:       {stats.total_images}")
    print(f"  Valid photos:       {stats.valid_images}")
    print(f"  Valid people:       {stats.valid_people}")
    print()
    print("Parameters:")
    print(f"  detector_model:     {args.detector_model}")
    print(f"  tolerance:          {args.tolerance}")
    print()
    print("Classification metrics:")
    print(f"  Accuracy:           {accuracy * 100:.2f}%")
    print(f"  Precision:          {precision * 100:.2f}%")
    print(f"  Recall:             {recall * 100:.2f}%")
    print(f"  F1-score:           {f1 * 100:.2f}%")
    print(f"  Unknown predictions: {unknown_count}")
    print()
    print("FAR / FRR:")
    print(f"  Same pairs:         {far_frr['same_pairs']}")
    print(f"  Different pairs:    {far_frr['different_pairs']}")
    print(f"  FAR:                {far_frr['FAR_percent']:.2f}%")
    print(f"  FRR:                {far_frr['FRR_percent']:.2f}%")
    print()
    print("Files saved to:")
    for f in sorted(output_dir.iterdir()):
        if f.is_file():
            print(f"  {f.relative_to(output_dir)}")
    print()
    print(sep)

    logger.info("Експеримент завершено.")


if __name__ == "__main__":
    main()
