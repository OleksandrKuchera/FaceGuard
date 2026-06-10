#!/usr/bin/env python3
"""
Експеримент 4: Візуалізація pipeline системи розпізнавання облич

Малює блок-схему з 7 етапів для вставки у дипломну роботу.
"""

import argparse
import logging
from pathlib import Path

import matplotlib
import matplotlib.patches as patches
import matplotlib.pyplot as plt

matplotlib.use("Agg")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

FIG_WIDTH_IN = 12
FIG_HEIGHT_IN = 17
DPI = 300

STAGES = [
    {
        "title": "1. ImagePreprocessor",
        "subtitle": "Препроцесинг та масштабування",
        "ops": [
            "BGR frame from camera",
            "CLAHE, tileGridSize = 8×8",
            "resize to 25%",
            "BGR → RGB",
        ],
        "color": "#4472C4",
    },
    {
        "title": "2. FaceDetector",
        "subtitle": "Детекція облич",
        "ops": [
            "face_recognition.face_locations()",
            "координати: top, right, bottom, left",
            "якщо faces = 0 → next frame",
        ],
        "color": "#548235",
    },
    {
        "title": "3. FaceTracker",
        "subtitle": "Трекінг облич",
        "ops": [
            "зіставлення bounding boxes між кадрами",
            "distance between centers",
            "stable track_id",
            "потрібно для liveness",
        ],
        "color": "#BF8F00",
    },
    {
        "title": "4. Landmarks",
        "subtitle": "Виділення ключових точок",
        "ops": [
            "68 facial landmarks",
            "eyes: 36–47",
            "nose: 27–35",
            "mouth: 48–67",
            "face contour: 0–16",
        ],
        "color": "#7030A0",
    },
    {
        "title": "5. FaceEncoder",
        "subtitle": "Генерація embedding",
        "ops": [
            "aligned face 150×150 px",
            "CNN dlib",
            "128D vector",
            "L2-normalized embedding",
        ],
        "color": "#C00000",
    },
    {
        "title": "6. AntiSpoofing",
        "subtitle": "Антиспуфінг",
        "ops": [
            "TextureAntiSpoofing",
            "LivenessDetector",
            "blink analysis",
            "if spoofing → stop matching",
        ],
        "color": "#FF6600",
    },
    {
        "title": "7. FaceMatcher",
        "subtitle": "Порівняння з базою",
        "ops": [
            "compare with cached embeddings",
            "Euclidean distance",
            "tolerance < 0.55",
            "confidence > 45%",
        ],
        "color": "#00B050",
    },
]

RESULT_BLOCK = {
    "title": "Результат",
    "lines": ["identified", "unknown", "spoofing"],
    "color": "#1F3864",
}


def draw_stage_box(ax, x, y, w, h, stage, boxstyle="round,pad=0.3"):
    color = stage["color"]
    light = color + "18"

    rect = patches.FancyBboxPatch(
        (x, y), w, h,
        boxstyle=boxstyle,
        facecolor=light,
        edgecolor=color,
        linewidth=2,
        zorder=2,
    )
    ax.add_patch(rect)

    title_y = y + h - 0.35
    ax.text(
        x + w / 2, title_y,
        stage["title"],
        ha="center", va="center",
        fontsize=13, fontweight="bold", color=color,
        zorder=3,
    )

    sub_y = title_y - 0.35
    ax.text(
        x + w / 2, sub_y,
        stage["subtitle"],
        ha="center", va="center",
        fontsize=11, fontstyle="italic", color="#333333",
        zorder=3,
    )

    op_y = sub_y - 0.45
    for op in stage["ops"]:
        ax.text(
            x + 0.3, op_y,
            "• " + op,
            ha="left", va="center",
            fontsize=10, color="#444444",
            zorder=3,
        )
        op_y -= 0.3


def draw_arrow_down(ax, x_top, y_top, x_bottom, y_bottom):
    ax.annotate(
        "",
        xy=(x_bottom, y_bottom),
        xytext=(x_top, y_top),
        arrowprops=dict(
            arrowstyle="->",
            color="#333333",
            lw=2,
            mutation_scale=20,
        ),
        zorder=1,
    )


def draw_side_branch(
    ax, x_start, y_start, x_end, y_end, label, color="#CC0000",
):
    ax.annotate(
        "",
        xy=(x_end, y_end),
        xytext=(x_start, y_start),
        arrowprops=dict(
            arrowstyle="->",
            color=color,
            lw=1.5,
            ls="--",
            mutation_scale=15,
        ),
        zorder=1,
    )
    mid_x = (x_start + x_end) / 2
    mid_y = (y_start + y_end) / 2
    ax.text(
        mid_x + 0.3, mid_y,
        label,
        ha="left", va="center",
        fontsize=9, color=color, fontstyle="italic",
        zorder=3,
    )


def draw_result_box(ax, x, y, w, h, block):
    color = block["color"]
    light = color + "15"

    rect = patches.FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.4",
        facecolor=light,
        edgecolor=color,
        linewidth=2.5,
        zorder=2,
    )
    ax.add_patch(rect)

    ax.text(
        x + w / 2, y + h - 0.35,
        block["title"],
        ha="center", va="center",
        fontsize=14, fontweight="bold", color=color,
        zorder=3,
    )

    for i, line in enumerate(block["lines"]):
        ax.text(
            x + w / 2, y + h - 0.8 - i * 0.35,
            line,
            ha="center", va="center",
            fontsize=12, color="#333333",
            zorder=3,
        )


def draw_pipeline(output_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(FIG_WIDTH_IN, FIG_HEIGHT_IN), dpi=DPI)
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#FFFFFF")

    ax.set_xlim(0, FIG_WIDTH_IN)
    ax.set_ylim(0, FIG_HEIGHT_IN)
    ax.axis("off")

    ax.set_title(
        "Конвеєр обробки кадру в системі розпізнавання облич",
        fontsize=16, fontweight="bold", color="#1F3864",
        y=0.985,
    )

    box_w = 7.0
    box_h = 1.7
    x_center = (FIG_WIDTH_IN - box_w) / 2

    stage_positions = []
    y_cursor = FIG_HEIGHT_IN - 1.5

    for stage in STAGES:
        y_cursor -= box_h
        draw_stage_box(ax, x_center, y_cursor, box_w, box_h, stage)
        stage_positions.append((x_center, y_cursor))
        y_cursor -= 0.55

    for i in range(len(stage_positions) - 1):
        _, y_top = stage_positions[i]
        _, y_bottom = stage_positions[i + 1]
        x_mid = x_center + box_w / 2
        draw_arrow_down(ax, x_mid, y_top, x_mid, y_bottom + box_h)

    draw_side_branch(
        ax,
        x_start=x_center + box_w,
        y_start=stage_positions[1][1] + box_h / 2,
        x_end=x_center + box_w + 2.5,
        y_end=stage_positions[1][1] - 0.5,
        label="faces = 0 →\nнаступний кадр",
        color="#CC0000",
    )

    draw_side_branch(
        ax,
        x_start=x_center + box_w,
        y_start=stage_positions[5][1] + box_h / 2,
        x_end=x_center + box_w + 2.5,
        y_end=stage_positions[5][1] - 0.5,
        label="is_spoofing = True →\nmatching skipped",
        color="#CC0000",
    )

    result_w = 5.0
    result_h = 1.3
    result_x = (FIG_WIDTH_IN - result_w) / 2
    result_y = y_cursor - result_h - 0.3

    draw_arrow_down(
        ax,
        x_center + box_w / 2,
        stage_positions[-1][1],
        result_x + result_w / 2,
        result_y + result_h,
    )

    draw_result_box(ax, result_x, result_y, result_w, result_h, RESULT_BLOCK)

    fig.tight_layout(pad=0.5)

    png_path = output_dir / "04_face_pipeline_vertical.png"
    pdf_path = output_dir / "04_face_pipeline_vertical.pdf"

    fig.savefig(str(png_path), dpi=DPI, bbox_inches="tight", facecolor="#FFFFFF")
    fig.savefig(str(pdf_path), dpi=DPI, bbox_inches="tight", facecolor="#FFFFFF")
    plt.close(fig)

    logger.info("PNG збережено: %s", png_path)
    logger.info("PDF збережено: %s", pdf_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Експеримент 4: Pipeline схема")
    parser.add_argument("--output-dir", type=str, default="output")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    draw_pipeline(output_dir)
    logger.info("Експеримент 4 завершено.")


if __name__ == "__main__":
    main()
