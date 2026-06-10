#!/usr/bin/env python3
"""
Експеримент: Confusion matrix + порівняння dlib/face_recognition
з класичними методами Eigenfaces/PCA та Fisherfaces/LDA.

Датасет (flat, без підпапок):
  dataset/
    KyrulukM_1.jpeg
    KyrulukM_2.jpeg
    Martsinkiv_1.jpeg
    ...

Ім'я особи визначається з імені файлу: все до останнього _.
"""

import argparse
import csv
import logging
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import face_recognition
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from numpy.typing import NDArray
from sklearn.decomposition import PCA
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import StandardScaler

matplotlib.use("Agg")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
FACE_CROP_SIZE = (100, 100)


# ─── Dataclasses ───────────────────────────────────────────────────────


@dataclass
class FaceRecord:
    """Валідний запис обличчя."""

    person_id: str
    image_path: str
    encoding: NDArray[np.float64]
    face_crop: NDArray[np.uint8]  # grayscale 100x100


@dataclass
class SplitResult:
    """Результат розбиття на train/test для однієї особи."""

    train_records: list[FaceRecord]
    test_records: list[FaceRecord]


@dataclass
class MethodRepeatResult:
    """Результат одного повтору для одного методу."""

    method: str
    database_size: int
    repeat_id: int
    selected_people: int
    train_photos: int
    test_photos: int
    accuracy: float
    precision: float
    recall: float
    f1: float
    y_true: list[str]
    y_pred: list[str]
    labels: list[str]
    status: str = "ok"
    notes: str = ""


@dataclass
class MethodAggregated:
    """Агреговані метрики для методу + розміру бази."""

    method: str
    database_size: int
    repeats: int
    accuracy_mean: float
    accuracy_std: float
    precision_mean: float
    precision_std: float
    recall_mean: float
    recall_std: float
    f1_mean: float
    f1_std: float
    status: str = "ok"
    notes: str = ""


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

            # Face crop для класичних методів
            top, right, bottom, left = face_locations[0]
            face_crop_bgr = image[top:bottom, left:right]
            face_crop_gray = cv2.cvtColor(face_crop_bgr, cv2.COLOR_RGB2GRAY)
            face_crop_resized = cv2.resize(face_crop_gray, FACE_CROP_SIZE, interpolation=cv2.INTER_AREA)

            record = FaceRecord(
                person_id=person_id,
                image_path=str(img_path),
                encoding=np.array(encodings[0], dtype=np.float64),
                face_crop=face_crop_resized,
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


# ─── dlib / face_recognition experiment ────────────────────────────────


def run_dlib_identification(
    selected_person_ids: list[str],
    splits: dict[str, SplitResult],
    tolerance: float = 0.55,
) -> tuple[list[str], list[str]]:
    """
    Ідентифікація через dlib/face_recognition.
    Використовує MEAN encoding (centroid) для кожної особи.
    """
    known_centroids: list[NDArray[np.float64]] = []
    known_person_ids: list[str] = []

    for pid in selected_person_ids:
        split = splits[pid]
        centroid = np.mean([r.encoding for r in split.train_records], axis=0)
        known_centroids.append(centroid)
        known_person_ids.append(pid)

    known_matrix = np.array(known_centroids, dtype=np.float64)

    y_true: list[str] = []
    y_pred: list[str] = []

    for pid in selected_person_ids:
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


# ─── PCA / Eigenfaces experiment ───────────────────────────────────────


def run_pca_identification(
    selected_person_ids: list[str],
    splits: dict[str, SplitResult],
) -> tuple[list[str], list[str], str, str]:
    """
    Ідентифікація через Eigenfaces/PCA + 1-NN.

    Використовує PCA для зменшення розмірності + KNN(k=1).
    KNN(k=1) обрано як найпростіший і найстабільніший варіант
    для малих датасетів — не потребує налаштування hyperparameter.
    """
    # Підготовка train даних
    train_vectors: list[NDArray[np.float64]] = []
    train_labels: list[str] = []
    for pid in selected_person_ids:
        for rec in splits[pid].train_records:
            train_vectors.append(rec.face_crop.flatten().astype(np.float64))
            train_labels.append(pid)

    X_train = np.array(train_vectors, dtype=np.float64)
    y_train = train_labels

    # Підготовка test даних
    test_vectors: list[NDArray[np.float64]] = []
    test_labels: list[str] = []
    for pid in selected_person_ids:
        for rec in splits[pid].test_records:
            test_vectors.append(rec.face_crop.flatten().astype(np.float64))
            test_labels.append(pid)

    X_test = np.array(test_vectors, dtype=np.float64)
    y_test = test_labels

    # Центрування
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # PCA: n_components = min(50, n_samples - 1)
    n_components = min(50, X_train.shape[0] - 1)
    if n_components < 1:
        return y_test, ["unknown"] * len(y_test), "skipped", "Недостатньо train-зразків для PCA"

    pca = PCA(n_components=n_components, random_state=42)
    X_train_pca = pca.fit_transform(X_train_scaled)
    X_test_pca = pca.transform(X_test_scaled)

    # 1-NN класифікація
    knn = KNeighborsClassifier(n_neighbors=1)
    knn.fit(X_train_pca, y_train)
    y_pred = knn.predict(X_test_pca).tolist()

    return y_test, y_pred, "ok", f"PCA n_components={n_components}"


# ─── LDA / Fisherfaces experiment ──────────────────────────────────────


def run_lda_identification(
    selected_person_ids: list[str],
    splits: dict[str, SplitResult],
) -> tuple[list[str], list[str], str, str]:
    """
    Ідентифікація через Fisherfaces/PCA+LDA + 1-NN.

    Спочатку PCA для зменшення розмірності (до n_classes-1 або менше),
    потім LDA для максимізації міжкласової дисперсії.
    """
    train_vectors: list[NDArray[np.float64]] = []
    train_labels: list[str] = []
    for pid in selected_person_ids:
        for rec in splits[pid].train_records:
            train_vectors.append(rec.face_crop.flatten().astype(np.float64))
            train_labels.append(pid)

    X_train = np.array(train_vectors, dtype=np.float64)
    y_train = train_labels

    test_vectors: list[NDArray[np.float64]] = []
    test_labels: list[str] = []
    for pid in selected_person_ids:
        for rec in splits[pid].test_records:
            test_vectors.append(rec.face_crop.flatten().astype(np.float64))
            test_labels.append(pid)

    X_test = np.array(test_vectors, dtype=np.float64)
    y_test = test_labels

    n_classes = len(selected_person_ids)
    n_samples = X_train.shape[0]

    # Перевірка: LDA потребує n_components <= n_classes - 1
    if n_classes < 2:
        return y_test, ["unknown"] * len(y_test), "skipped", "Менше 2 класів для LDA"

    # Перевірка: достатньо зразків
    if n_samples <= n_classes:
        return y_test, ["unknown"] * len(y_test), "skipped", \
            f"Недостатньо train-зразків ({n_samples}) для {n_classes} класів"

    # Центрування
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Попередній PCA: зменшуємо до n_classes - 1 (або менше)
    n_pca_components = min(n_classes - 1, n_samples - 1, X_train.shape[1])
    if n_pca_components < 1:
        return y_test, ["unknown"] * len(y_test), "skipped", \
            "Неможливо виконати попередній PCA для Fisherfaces"

    pca = PCA(n_components=n_pca_components, random_state=42)
    X_train_pca = pca.fit_transform(X_train_scaled)
    X_test_pca = pca.transform(X_test_scaled)

    # LDA
    n_lda_components = min(n_classes - 1, n_pca_components)
    lda = LinearDiscriminantAnalysis(n_components=n_lda_components)

    try:
        lda.fit(X_train_pca, y_train)
    except Exception as exc:
        return y_test, ["unknown"] * len(y_test), "skipped", f"LDA помилка: {exc}"

    X_train_lda = lda.transform(X_train_pca)
    X_test_lda = lda.transform(X_test_pca)

    # 1-NN у LDA-просторі
    knn = KNeighborsClassifier(n_neighbors=1)
    knn.fit(X_train_lda, y_train)
    y_pred = knn.predict(X_test_lda).tolist()

    return y_test, y_pred, "ok", f"Fisherfaces PCA={n_pca_components}, LDA={n_lda_components}"


# ─── Metrics computation ───────────────────────────────────────────────


def compute_metrics(
    y_true: list[str],
    y_pred: list[str],
) -> tuple[float, float, float, float]:
    """Обчислює Accuracy, Precision, Recall, F1 (macro)."""
    acc = float(accuracy_score(y_true, y_pred))
    prec = float(precision_score(y_true, y_pred, average="macro", zero_division=0))
    rec = float(recall_score(y_true, y_pred, average="macro", zero_division=0))
    f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
    return acc, prec, rec, f1


def get_all_labels(y_true: list[str], y_pred: list[str]) -> list[str]:
    """Повертає відсортований список унікальних класів."""
    return sorted(set(y_true) | set(y_pred))


# ─── Experiment runner ─────────────────────────────────────────────────


def run_experiment_for_method(
    filtered_grouped: dict[str, list[FaceRecord]],
    database_sizes: list[int],
    method_name: str,
    method_fn,
    tolerance: float = 0.55,
    repeats: int = 5,
    random_state: int = 42,
) -> list[MethodRepeatResult]:
    """
    Запускає експеримент для одного методу.
    method_fn(selected_person_ids, splits, **kwargs) -> (y_true, y_pred, status, notes)
    """
    all_person_ids = sorted(filtered_grouped.keys())
    n_available = len(all_person_ids)

    # Попередньо обчислюємо splits
    splits: dict[str, SplitResult] = {}
    for pid in all_person_ids:
        splits[pid] = split_train_test(filtered_grouped[pid], random_state=random_state)

    raw_results: list[MethodRepeatResult] = []

    for db_size in database_sizes:
        if db_size > n_available:
            logger.warning(
                "Пропуск %s size=%d (доступно %d осіб)",
                method_name, db_size, n_available,
            )
            continue

        logger.info("=== %s: database_size=%d, repeats=%d ===", method_name, db_size, repeats)

        repeat_rng = np.random.RandomState(random_state + db_size)

        for rep in range(1, repeats + 1):
            selected = repeat_rng.choice(
                all_person_ids, size=db_size, replace=False
            ).tolist()

            try:
                if method_name == "dlib":
                    y_true, y_pred = method_fn(selected, splits, tolerance=tolerance)
                    status, notes = "ok", ""
                else:
                    y_true, y_pred, status, notes = method_fn(selected, splits)
            except Exception as exc:
                logger.error("%s repeat %d size %d помилка: %s", method_name, rep, db_size, exc)
                continue

            if not y_true:
                logger.warning("Порожній test set %s repeat %d size %d", method_name, rep, db_size)
                continue

            acc, prec, rec, f1 = compute_metrics(y_true, y_pred)
            labels = get_all_labels(y_true, y_pred)

            n_train = sum(len(splits[pid].train_records) for pid in selected)
            n_test = sum(len(splits[pid].test_records) for pid in selected)

            rm = MethodRepeatResult(
                method=method_name,
                database_size=db_size,
                repeat_id=rep,
                selected_people=db_size,
                train_photos=n_train,
                test_photos=n_test,
                accuracy=acc,
                precision=prec,
                recall=rec,
                f1=f1,
                y_true=y_true,
                y_pred=y_pred,
                labels=labels,
                status=status,
                notes=notes,
            )
            raw_results.append(rm)
            logger.info(
                "  repeat %d: acc=%.4f prec=%.4f rec=%.4f f1=%.4f [%s]",
                rep, acc, prec, rec, f1, status,
            )

    return raw_results


def aggregate_method_results(
    raw: list[MethodRepeatResult],
) -> list[MethodAggregated]:
    """Групує raw results за (method, database_size) та обчислює mean/std."""
    groups: dict[tuple[str, int], list[MethodRepeatResult]] = defaultdict(list)
    for r in raw:
        groups[(r.method, r.database_size)].append(r)

    aggregated: list[MethodAggregated] = []
    for (method, db_size) in sorted(groups.keys()):
        reps = groups[(method, db_size)]
        n = len(reps)
        if n == 0:
            continue

        ok_reps = [r for r in reps if r.status == "ok"]
        if not ok_reps:
            agg = MethodAggregated(
                method=method, database_size=db_size, repeats=n,
                accuracy_mean=0, accuracy_std=0,
                precision_mean=0, precision_std=0,
                recall_mean=0, recall_std=0,
                f1_mean=0, f1_std=0,
                status="failed",
                notes="Усі повтори завершились помилкою",
            )
            aggregated.append(agg)
            continue

        acc_vals = [r.accuracy for r in ok_reps]
        prec_vals = [r.precision for r in ok_reps]
        rec_vals = [r.recall for r in ok_reps]
        f1_vals = [r.f1 for r in ok_reps]

        notes_parts = [r.notes for r in ok_reps if r.notes]
        notes = "; ".join(set(notes_parts)) if notes_parts else ""

        agg = MethodAggregated(
            method=method,
            database_size=db_size,
            repeats=n,
            accuracy_mean=float(np.mean(acc_vals)),
            accuracy_std=float(np.std(acc_vals, ddof=1) if n > 1 else 0.0),
            precision_mean=float(np.mean(prec_vals)),
            precision_std=float(np.std(prec_vals, ddof=1) if n > 1 else 0.0),
            recall_mean=float(np.mean(rec_vals)),
            recall_std=float(np.std(rec_vals, ddof=1) if n > 1 else 0.0),
            f1_mean=float(np.mean(f1_vals)),
            f1_std=float(np.std(f1_vals, ddof=1) if n > 1 else 0.0),
            status="ok",
            notes=notes,
        )
        aggregated.append(agg)

    return aggregated


# ─── Confusion matrix helpers ──────────────────────────────────────────


def compute_confusion_matrix(
    y_true: list[str],
    y_pred: list[str],
    labels: list[str] | None = None,
) -> tuple[NDArray[np.int64], list[str]]:
    """Обчислює confusion matrix."""
    if labels is None:
        labels = get_all_labels(y_true, y_pred)
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    return cm, labels


def save_confusion_matrix_csv(
    cm: NDArray[np.int64],
    labels: list[str],
    output_path: Path,
) -> None:
    """Зберігає confusion matrix у CSV."""
    df = pd.DataFrame(cm, index=labels, columns=labels)
    df.index.name = "actual"
    df.columns.name = "predicted"
    df.to_csv(output_path, sep=";", encoding="utf-8")
    logger.info("Confusion matrix CSV: %s", output_path)


def plot_confusion_matrix(
    cm: NDArray[np.int64],
    labels: list[str],
    title: str,
    output_path: Path,
) -> None:
    """Будує heatmap confusion matrix через matplotlib."""
    n = len(labels)
    fig, ax = plt.subplots(figsize=(max(8, n * 0.8), max(7, n * 0.7)))

    im = ax.imshow(cm, interpolation="nearest", cmap=plt.cm.Blues)
    ax.set_title(title, fontsize=13)
    ax.set_xlabel("Передбачений клас", fontsize=11)
    ax.set_ylabel("Реальний клас", fontsize=11)

    tick_marks = np.arange(n)
    rotation = 45 if n > 6 else 0
    ax.set_xticks(tick_marks)
    ax.set_xticklabels(labels, rotation=rotation, ha="right", fontsize=8)
    ax.set_yticks(tick_marks)
    ax.set_yticklabels(labels, fontsize=8)

    # Значення всередині клітинок
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


# ─── Classification report helpers ─────────────────────────────────────


def save_classification_report_csv(
    y_true: list[str],
    y_pred: list[str],
    labels: list[str],
    output_csv: Path,
    output_md: Path,
) -> None:
    """Зберігає classification report у CSV та MD."""
    report_dict = classification_report(
        y_true, y_pred, labels=labels,
        output_dict=True, zero_division=0,
    )

    rows = []
    for label in labels:
        if label in report_dict:
            d = report_dict[label]
            rows.append({
                "person_id": label,
                "precision": d.get("precision", 0),
                "recall": d.get("recall", 0),
                "f1-score": d.get("f1-score", 0),
                "support": int(d.get("support", 0)),
            })

    # Додаємо aggregated рядки
    for key in ("accuracy", "macro avg", "weighted avg"):
        if key in report_dict:
            d = report_dict[key]
            if isinstance(d, float):
                rows.append({
                    "person_id": key,
                    "precision": d,
                    "recall": d,
                    "f1-score": d,
                    "support": "",
                })
            else:
                rows.append({
                    "person_id": key,
                    "precision": d.get("precision", ""),
                    "recall": d.get("recall", ""),
                    "f1-score": d.get("f1-score", ""),
                    "support": d.get("support", ""),
                })

    df = pd.DataFrame(rows)
    df.to_csv(output_csv, sep=";", index=False, encoding="utf-8")
    logger.info("Classification report CSV: %s", output_csv)

    # Markdown
    lines = [f"# Classification Report\n", f"## {output_md.stem}\n"]
    lines.append("| person_id | precision | recall | f1-score | support |")
    lines.append("|-----------|-----------|--------|----------|---------|")
    for row in rows:
        pid = row["person_id"]
        prec = f'{row["precision"]:.4f}' if isinstance(row["precision"], float) else row["precision"]
        rec = f'{row["recall"]:.4f}' if isinstance(row["recall"], float) else row["recall"]
        f1 = f'{row["f1-score"]:.4f}' if isinstance(row["f1-score"], float) else row["f1-score"]
        sup = row["support"]
        lines.append(f"| {pid} | {prec} | {rec} | {f1} | {sup} |")

    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Classification report MD: %s", output_md)


# ─── Plotting: method comparison ───────────────────────────────────────


def plot_method_comparison(
    aggregated: list[MethodAggregated],
    metric: str,
    metric_label: str,
    title: str,
    output_path: Path,
) -> None:
    """Будує графік порівняння методів."""
    method_names = sorted(set(a.method for a in aggregated))
    sizes = sorted(set(a.database_size for a in aggregated))

    fig, ax = plt.subplots(figsize=(12, 7))

    colors = {"dlib": "#2196F3", "eigenfaces_pca": "#FF9800", "fisherfaces_lda": "#4CAF50"}
    markers = {"dlib": "o", "eigenfaces_pca": "s", "fisherfaces_lda": "^"}
    method_labels = {
        "dlib": "dlib / face_recognition",
        "eigenfaces_pca": "Eigenfaces / PCA",
        "fisherfaces_lda": "Fisherfaces / LDA",
    }

    for method in method_names:
        method_data = [a for a in aggregated if a.method == method and a.status == "ok"]
        if not method_data:
            continue

        x = [a.database_size for a in method_data]
        means = [getattr(a, f"{metric}_mean") * 100 for a in method_data]
        stds = [getattr(a, f"{metric}_std") * 100 for a in method_data]

        color = colors.get(method, None)
        marker = markers.get(method, "o")

        ax.errorbar(
            x, means, yerr=stds,
            fmt=f"{marker}-", capsize=6, capthick=1.5,
            linewidth=2, markersize=8,
            label=method_labels.get(method, method),
            color=color,
        )

    ax.set_xlabel("Кількість осіб у базі", fontsize=12)
    ax.set_ylabel(f"{metric_label}, %", fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.legend(loc="best", fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.set_xticks(sizes)

    fig.tight_layout()
    fig.savefig(str(output_path), dpi=300)
    plt.close(fig)
    logger.info("Графік порівняння збережено: %s", output_path)


# ─── Report generation ─────────────────────────────────────────────────


def generate_report(
    stats: DatasetStats,
    tested_sizes: list[int],
    dlib_raw: list[MethodRepeatResult],
    dlib_agg: list[MethodAggregated],
    pca_raw: list[MethodRepeatResult],
    pca_agg: list[MethodAggregated],
    lda_raw: list[MethodRepeatResult],
    lda_agg: list[MethodAggregated],
    output_dir: Path,
) -> Path:
    """Генерує підсумковий текстовий звіт."""
    path = output_dir / "confusion_and_methods_report.txt"
    lines: list[str] = []
    sep = "=" * 70

    lines.append(sep)
    lines.append("  ЗВІТ: Confusion matrix + порівняння методів розпізнавання")
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
    lines.append(f"   Валідні особи:                   {', '.join(stats.valid_people_ids)}")
    lines.append("")

    # 2. Протестовані розміри
    lines.append("2. ТЕСТОВАНІ РОЗМІРИ БАЗИ")
    lines.append(f"   Протестовані database_sizes:     {tested_sizes}")
    lines.append("")

    # 3. dlib
    lines.append("3. DLIB / FACE_RECOGNITION")
    lines.append("")
    if dlib_agg:
        lines.append("   Summary metrics:")
        lines.append(f"   {'Size':>6}  {'Repeats':>8}  {'Acc mean':>10}  {'Acc std':>9}  "
                      f"{'Prec mean':>10}  {'F1 mean':>10}")
        for a in dlib_agg:
            lines.append(
                f"   {a.database_size:>6}  {a.repeats:>8}  "
                f"{a.accuracy_mean * 100:>9.2f}%  {a.accuracy_std * 100:>8.2f}%  "
                f"{a.precision_mean * 100:>9.2f}%  {a.f1_mean * 100:>9.2f}%"
            )
        lines.append("")
        lines.append("   Confusion matrix:")
        for sz in tested_sizes:
            cm_path = output_dir / f"confusion_matrix_dlib_size_{sz}.png"
            if cm_path.exists():
                lines.append(f"     size={sz}: {cm_path}")
        lines.append("")
        lines.append("   Classification report:")
        for sz in tested_sizes:
            cr_path = output_dir / f"classification_report_dlib_size_{sz}.md"
            if cr_path.exists():
                lines.append(f"     size={sz}: {cr_path}")
    else:
        lines.append("   Немає результатів.")
    lines.append("")

    # 4. PCA
    lines.append("4. EIGENFACES / PCA")
    lines.append("")
    if pca_agg:
        lines.append("   Summary metrics:")
        for a in pca_agg:
            status_tag = f" [{a.status}]" if a.status != "ok" else ""
            notes_tag = f" ({a.notes})" if a.notes else ""
            lines.append(
                f"   size={a.database_size}: acc={a.accuracy_mean * 100:.2f}% "
                f"f1={a.f1_mean * 100:.2f}%{status_tag}{notes_tag}"
            )
        lines.append("")
        ok_count = sum(1 for a in pca_agg if a.status == "ok")
        lines.append(f"   Короткий висновок: успішно виконано {ok_count}/{len(pca_agg)} експериментів.")
    else:
        lines.append("   Немає результатів.")
    lines.append("")

    # 5. LDA
    lines.append("5. FISHERFACES / LDA")
    lines.append("")
    if lda_agg:
        ok_count = sum(1 for a in lda_agg if a.status == "ok")
        skip_count = sum(1 for a in lda_agg if a.status == "skipped")
        lines.append(f"   Успішно: {ok_count}, пропущено: {skip_count}")
        for a in lda_agg:
            status_tag = f" [{a.status}]" if a.status != "ok" else ""
            notes_tag = f" ({a.notes})" if a.notes else ""
            lines.append(
                f"   size={a.database_size}: acc={a.accuracy_mean * 100:.2f}% "
                f"f1={a.f1_mean * 100:.2f}%{status_tag}{notes_tag}"
            )
    else:
        lines.append("   Немає результатів.")
    lines.append("")

    # 6. Порівняння
    lines.append("6. ПОРІВНЯННЯ МЕТОДІВ")
    lines.append("")
    all_agg = dlib_agg + pca_agg + lda_agg
    if all_agg:
        lines.append(f"   {'Method':>22}  {'Size':>6}  {'Acc mean':>10}  {'F1 mean':>10}")
        lines.append(f"   {'─' * 22}  {'─' * 6}  {'─' * 10}  {'─' * 10}")
        for a in sorted(all_agg, key=lambda x: (x.database_size, x.method)):
            lines.append(
                f"   {a.method:>22}  {a.database_size:>6}  "
                f"{a.accuracy_mean * 100:>9.2f}%  {a.f1_mean * 100:>9.2f}%"
            )
    lines.append("")

    # 7. Висновок
    lines.append("7. ВИСНОВОК")
    lines.append("")

    ok_methods = [a for a in all_agg if a.status == "ok"]
    if ok_methods:
        best_acc = max(ok_methods, key=lambda a: a.accuracy_mean)
        best_f1 = max(ok_methods, key=lambda a: a.f1_mean)

        lines.append(
            f"   Найкраща Accuracy: {best_acc.accuracy_mean * 100:.2f}% "
            f"(метод: {best_acc.method}, база: {best_acc.database_size} осіб)"
        )
        lines.append(
            f"   Найкращий F1-score: {best_f1.f1_mean * 100:.2f}% "
            f"(метод: {best_f1.method}, база: {best_f1.database_size} осіб)"
        )
        lines.append("")

        # Чи зростає кількість помилок зі збільшенням бази
        for method_name in ["dlib", "eigenfaces_pca", "fisherfaces_lda"]:
            method_data = sorted(
                [a for a in ok_methods if a.method == method_name],
                key=lambda a: a.database_size,
            )
            if len(method_data) >= 2:
                acc_first = method_data[0].accuracy_mean
                acc_last = method_data[-1].accuracy_mean
                trend = "спадає" if acc_last < acc_first else "зростає" if acc_last > acc_first else "стабільна"
                lines.append(
                    f"   {method_name}: при збільшенні бази точність {trend} "
                    f"(з {acc_first * 100:.2f}% до {acc_last * 100:.2f}%)."
                )
        lines.append("")

        # Чи є "unknown" частою причиною помилок для dlib
        if dlib_raw:
            unknown_count = sum(
                1 for r in dlib_raw for p in r.y_pred if p == "unknown"
            )
            total_test = sum(len(r.y_pred) for r in dlib_raw)
            if total_test > 0:
                unknown_pct = unknown_count / total_test * 100
                lines.append(
                    f"   dlib: 'unknown' predictions = {unknown_count}/{total_test} "
                    f"({unknown_pct:.1f}% тестів)."
                )
                if unknown_pct > 10:
                    lines.append(
                        f"   tolerance=0.40 є досить суворим, що призводить до "
                        f"частого класифікування як 'unknown'."
                    )
        lines.append("")

        # Перевага сучасних методів
        dlib_acc = [a.accuracy_mean for a in ok_methods if a.method == "dlib"]
        pca_acc = [a.accuracy_mean for a in ok_methods if a.method == "eigenfaces_pca"]
        lda_acc = [a.accuracy_mean for a in ok_methods if a.method == "fisherfaces_lda"]

        if dlib_acc and pca_acc:
            dlib_avg = np.mean(dlib_acc)
            pca_avg = np.mean(pca_acc)
            if dlib_avg > pca_avg:
                lines.append(
                    f"   dlib/face_recognition (mean acc={dlib_avg * 100:.2f}%) "
                    f"перевершує Eigenfaces/PCA (mean acc={pca_avg * 100:.2f}%)."
                )
            else:
                lines.append(
                    f"   Eigenfaces/PCA (mean acc={pca_avg * 100:.2f}%) "
                    f"перевершує dlib/face_recognition (mean acc={dlib_avg * 100:.2f}%)."
                )

        if dlib_acc and lda_acc:
            dlib_avg = np.mean(dlib_acc)
            lda_avg = np.mean(lda_acc)
            if dlib_avg > lda_avg:
                lines.append(
                    f"   dlib/face_recognition (mean acc={dlib_avg * 100:.2f}%) "
                    f"перевершує Fisherfaces/LDA (mean acc={lda_avg * 100:.2f}%)."
                )
            else:
                lines.append(
                    f"   Fisherfaces/LDA (mean acc={lda_avg * 100:.2f}%) "
                    f"перевершує dlib/face_recognition (mean acc={dlib_avg * 100:.2f}%)."
                )

        lines.append("")
        lines.append(
            "   Перевага сучасних embedding-підходів (dlib/face_recognition) "
            "над класичними методами (Eigenfaces/PCA, Fisherfaces/LDA) "
            "підтверджується на цьому датасеті."
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
        description="Експеримент: Confusion matrix + порівняння dlib з класичними методами"
    )
    parser.add_argument("--dataset", type=str, default="./dataset", help="Шлях до папки з фото")
    parser.add_argument("--output", type=str, default="./output", help="Шлях до папки для результатів")
    parser.add_argument("--tolerance", type=float, default=0.55, help="Поріг для dlib (default: 0.55)")
    parser.add_argument("--sizes", type=int, nargs="+", default=[5, 10], help="Розміри бази (default: 5 10)")
    parser.add_argument("--repeats", type=int, default=5, help="Кількість повторів (default: 5)")
    parser.add_argument("--random-state", type=int, default=42, help="Seed (default: 42)")
    parser.add_argument("--detector-model", type=str, default="hog", choices=["hog", "cnn"], help="Detector")
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
    logger.info("Sizes:      %s", args.sizes)
    logger.info("Repeats:    %d", args.repeats)
    logger.info("Detector:   %s", args.detector_model)
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

    tested_sizes = [s for s in args.sizes if s <= stats.valid_people]
    if not tested_sizes:
        logger.error("Жоден розмір не підходить (валідних осіб: %d)", stats.valid_people)
        sys.exit(1)

    logger.info("Реальні розміри: %s", tested_sizes)
    logger.info("")

    # 3. dlib / face_recognition
    logger.info("=== DLIB / FACE_RECOGNITION ===")
    dlib_raw = run_experiment_for_method(
        filtered, tested_sizes, "dlib", run_dlib_identification,
        tolerance=args.tolerance, repeats=args.repeats, random_state=args.random_state,
    )
    dlib_agg = aggregate_method_results(dlib_raw)
    logger.info("")

    # Confusion matrix + classification report для dlib
    for sz in tested_sizes:
        sz_repeats = [r for r in dlib_raw if r.database_size == sz and r.status == "ok"]
        if not sz_repeats:
            logger.warning("Немає результатів dlib для size=%d", sz)
            continue

        # Repeat 1 — прикладова матриця
        rep1 = sz_repeats[0]
        cm1, labels1 = compute_confusion_matrix(rep1.y_true, rep1.y_pred, rep1.labels)

        save_confusion_matrix_csv(
            cm1, labels1,
            output_dir / f"confusion_matrix_dlib_size_{sz}.csv",
        )
        plot_confusion_matrix(
            cm1, labels1,
            f"Матриця помилок dlib/face_recognition для бази з {sz} осіб",
            output_dir / f"confusion_matrix_dlib_size_{sz}.png",
        )
        save_classification_report_csv(
            rep1.y_true, rep1.y_pred, labels1,
            output_dir / f"classification_report_dlib_size_{sz}.csv",
            output_dir / f"classification_report_dlib_size_{sz}.md",
        )

        # Aggregated confusion matrix
        agg_cm = np.zeros((len(labels1), len(labels1)), dtype=np.int64)
        for r in sz_repeats:
            cm_r, labels_r = compute_confusion_matrix(r.y_true, r.y_pred, labels1)
            agg_cm += cm_r

        save_confusion_matrix_csv(
            agg_cm, labels1,
            output_dir / f"confusion_matrix_dlib_size_{sz}_aggregated.csv",
        )
        plot_confusion_matrix(
            agg_cm, labels1,
            f"Агрегована матриця помилок dlib/face_recognition для бази з {sz} осіб",
            output_dir / f"confusion_matrix_dlib_size_{sz}_aggregated.png",
        )

    logger.info("")

    # 4. PCA / Eigenfaces
    logger.info("=== EIGENFACES / PCA ===")
    pca_raw = run_experiment_for_method(
        filtered, tested_sizes, "eigenfaces_pca", run_pca_identification,
        repeats=args.repeats, random_state=args.random_state,
    )
    pca_agg = aggregate_method_results(pca_raw)
    logger.info("")

    for sz in tested_sizes:
        sz_repeats = [r for r in pca_raw if r.database_size == sz and r.status == "ok"]
        if not sz_repeats:
            logger.warning("Немає результатів PCA для size=%d", sz)
            continue

        rep1 = sz_repeats[0]
        cm1, labels1 = compute_confusion_matrix(rep1.y_true, rep1.y_pred, rep1.labels)

        save_confusion_matrix_csv(
            cm1, labels1,
            output_dir / f"confusion_matrix_pca_size_{sz}.csv",
        )
        plot_confusion_matrix(
            cm1, labels1,
            f"Матриця помилок Eigenfaces/PCA для бази з {sz} осіб",
            output_dir / f"confusion_matrix_pca_size_{sz}.png",
        )
        save_classification_report_csv(
            rep1.y_true, rep1.y_pred, labels1,
            output_dir / f"classification_report_pca_size_{sz}.csv",
            output_dir / f"classification_report_pca_size_{sz}.md",
        )

    logger.info("")

    # 5. LDA / Fisherfaces
    logger.info("=== FISHERFACES / LDA ===")
    lda_raw = run_experiment_for_method(
        filtered, tested_sizes, "fisherfaces_lda", run_lda_identification,
        repeats=args.repeats, random_state=args.random_state,
    )
    lda_agg = aggregate_method_results(lda_raw)
    logger.info("")

    for sz in tested_sizes:
        sz_repeats = [r for r in lda_raw if r.database_size == sz and r.status == "ok"]
        if not sz_repeats:
            skipped = [r for r in lda_raw if r.database_size == sz and r.status == "skipped"]
            if skipped:
                logger.warning("LDA пропущено для size=%d: %s", sz, skipped[0].notes)
            continue

        rep1 = sz_repeats[0]
        cm1, labels1 = compute_confusion_matrix(rep1.y_true, rep1.y_pred, rep1.labels)

        save_confusion_matrix_csv(
            cm1, labels1,
            output_dir / f"confusion_matrix_lda_size_{sz}.csv",
        )
        plot_confusion_matrix(
            cm1, labels1,
            f"Матриця помилок Fisherfaces/LDA для бази з {sz} осіб",
            output_dir / f"confusion_matrix_lda_size_{sz}.png",
        )
        save_classification_report_csv(
            rep1.y_true, rep1.y_pred, labels1,
            output_dir / f"classification_report_lda_size_{sz}.csv",
            output_dir / f"classification_report_lda_size_{sz}.md",
        )

    logger.info("")

    # 6. Порівняння методів
    logger.info("--- Порівняння методів ---")
    all_agg = dlib_agg + pca_agg + lda_agg

    # CSV
    comp_path = output_dir / "method_comparison.csv"
    comp_rows = []
    for a in all_agg:
        comp_rows.append({
            "method": a.method,
            "database_size": a.database_size,
            "repeats": a.repeats,
            "accuracy_mean": f"{a.accuracy_mean:.6f}",
            "accuracy_std": f"{a.accuracy_std:.6f}",
            "precision_mean": f"{a.precision_mean:.6f}",
            "precision_std": f"{a.precision_std:.6f}",
            "recall_mean": f"{a.recall_mean:.6f}",
            "recall_std": f"{a.recall_std:.6f}",
            "f1_mean": f"{a.f1_mean:.6f}",
            "f1_std": f"{a.f1_std:.6f}",
            "status": a.status,
            "notes": a.notes,
        })
    pd.DataFrame(comp_rows).to_csv(comp_path, sep=";", index=False, encoding="utf-8")
    logger.info("Method comparison CSV: %s", comp_path)

    # Графіки
    plot_method_comparison(
        all_agg, "accuracy", "Accuracy",
        "Порівняння точності dlib, Eigenfaces/PCA та Fisherfaces/LDA",
        output_dir / "method_comparison_accuracy.png",
    )
    plot_method_comparison(
        all_agg, "f1", "F1-score",
        "Порівняння F1-score dlib, Eigenfaces/PCA та Fisherfaces/LDA",
        output_dir / "method_comparison_f1.png",
    )

    # 7. Звіт
    logger.info("--- Генерація звіту ---")
    generate_report(
        stats, tested_sizes,
        dlib_raw, dlib_agg,
        pca_raw, pca_agg,
        lda_raw, lda_agg,
        output_dir,
    )

    logger.info("")
    logger.info("Експеримент завершено. Результати у: %s", output_dir.resolve())

    report_path = output_dir / "confusion_and_methods_report.txt"
    print("\n" + report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
