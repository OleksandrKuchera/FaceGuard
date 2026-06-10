#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATASET_DIR="${1:-${SCRIPT_DIR}/dataset}"
OUTPUT_DIR="${2:-${SCRIPT_DIR}/output}"

echo "================================================"
echo "  FaceGuard — Експерименти для дипломної роботи"
echo "================================================"
echo ""
echo "  Dataset:  ${DATASET_DIR}"
echo "  Output:   ${OUTPUT_DIR}"
echo ""

if [ ! -d "${DATASET_DIR}" ]; then
    echo "ERROR: Dataset directory not found: ${DATASET_DIR}"
    echo ""
    echo "Покладіть фото у папку dataset/:"
    echo "  dataset/"
    echo "    ivanenko_01.jpg"
    echo "    ivanenko_02.jpg"
    echo "    petrenko_01.jpg"
    echo "    petrenko_02.jpg"
    echo ""
    echo "Ім'я особи = префікс файлу до _number"
    exit 1
fi

IMAGE_COUNT=$(find "${DATASET_DIR}" -maxdepth 1 -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \) | wc -l | tr -d ' ')

if [ "${IMAGE_COUNT}" -eq 0 ]; then
    echo "ERROR: No images found in ${DATASET_DIR}"
    exit 1
fi

echo "  Знайдено зображень: ${IMAGE_COUNT}"
echo ""

cd "${SCRIPT_DIR}"

if [ ! -d "venv" ]; then
    echo "► Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "► Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo ""
echo "================================================"
echo "  ЕКСПЕРИМЕНТ 1: Верифікація облич"
echo "================================================"
python exp_01_distances.py --dataset "${DATASET_DIR}" --output-dir "${OUTPUT_DIR}"

echo ""
echo "================================================"
echo "  ЕКСПЕРИМЕНТ 2: FAR / FRR / Accuracy"
echo "================================================"
python exp_02_metrics.py --dataset "${DATASET_DIR}" --output-dir "${OUTPUT_DIR}"

echo ""
echo "================================================"
echo "  ЕКСПЕРИМЕНТ 3: Шифрування біометрії"
echo "================================================"
python exp_03_encryption.py --output-dir "${OUTPUT_DIR}"

echo ""
echo "================================================"
echo "  ЕКСПЕРИМЕНТ 4: Схема pipeline"
echo "================================================"
python exp_04_pipeline.py --output-dir "${OUTPUT_DIR}"

echo ""
echo "================================================"
echo "  ВСІ ЕКСПЕРИМЕНТИ ЗАВЕРШЕНО"
echo "================================================"
echo ""
echo "  Результати у: ${OUTPUT_DIR}"
echo ""
echo "  Експеримент 1:"
echo "    01_distance_histogram.png"
echo "    01_pair_distances.csv"
echo ""
echo "  Експеримент 2:"
echo "    02_metrics_by_tolerance.png"
echo "    02_distance_distribution.png"
echo "    02_metrics_by_tolerance.csv"
echo ""
echo "  Експеримент 3:"
echo "    03_encryption_results.png"
echo "    03_encryption_tests.csv"
echo ""
echo "  Експеримент 4:"
echo "    04_face_pipeline_vertical.png"
echo "    04_face_pipeline_vertical.pdf"
echo ""
