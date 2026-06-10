# Експерименти для дипломної роботи — FaceGuard

4 експерименти для підтвердження принципів роботи системи розпізнавання облич.

## Структура

```
experiments/
├── exp_01_distances.py     # Верифікація: гістограма відстаней
├── exp_02_metrics.py       # FAR / FRR / Accuracy + sweep
├── exp_03_encryption.py    # Шифрування біометрії (Fernet)
├── exp_04_pipeline.py      # Схема pipeline системи
├── requirements.txt        # Залежності
├── Dockerfile              # Один Docker образ для всіх
├── docker-compose.yml      # Один compose для всіх 4
├── run.sh                  # Запуск всіх 4 локально
├── dataset/                # ← ТУДИ КЛАДИ ФОТО
└── output/                 # ← ТУТИ БУДУТЬ РЕЗУЛЬТАТИ
```

## Як підготувати датасет

**Всі фото в ОДНІЙ папці `dataset/`**, без підпапок.

Ім'я особи визначається з імені файлу — **префікс до `_число`**:

```
dataset/
  ivanenko_01.jpg     ← особа "ivanenko"
  ivanenko_02.jpg     ← особа "ivanenko"
  ivanenko_03.jpg     ← особа "ivanenko"
  petrenko_01.jpg     ← особа "petrenko"
  petrenko_02.jpg     ← особа "petrenko"
  sydor_01.jpg        ← особа "sydor"
  sydor_02.jpg        ← особа "sydor"
  sydor_03.jpg        ← особа "sydor"
```

**Вимоги:**
- Формат: `.jpg`, `.jpeg`, `.png`
- На кожному фото — **рівно одне обличчя**
- Мінімум 2 особи, по 2+ фото на кожну
- Рекомендовано: 3-10 фото на особу

## Запуск

### Варіант 1: Одна команда (локально)

```bash
cd experiments
./run.sh
```

Або з кореня проєкту:

```bash
make exp-run-all
```

### Варіант 2: Окремі експерименти

```bash
cd experiments

# Створити venv один раз
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Експеримент 1
python exp_01_distances.py --dataset dataset --output-dir output

# Експеримент 2
python exp_02_metrics.py --dataset dataset --output-dir output

# Експеримент 3 (не потребує датасету)
python exp_03_encryption.py --output-dir output

# Експеримент 4 (не потребує датасету)
python exp_04_pipeline.py --output-dir output
```

### Варіант 3: Docker

```bash
cd experiments

# Всі 4 експерименти
docker compose up --build

# Або окремо:
docker compose up --build exp-01
docker compose up --build exp-02
docker compose up --build exp-03
docker compose up --build exp-04
```

## Результати

Після запуску в `output/` з'являться:

| Файл | Експеримент | Опис |
|------|-------------|------|
| `01_distance_histogram.png` | 1 | Гістограма відстаней same vs different |
| `01_pair_distances.csv` | 1 | Всі пари з відстанями |
| `02_metrics_by_tolerance.png` | 2 | Графік FAR/FRR/Accuracy |
| `02_distance_distribution.png` | 2 | Гістограма відстаней з threshold |
| `02_metrics_by_tolerance.csv` | 2 | Метрики для tolerance [0.40–0.60] |
| `03_encryption_results.png` | 3 | Графік тестів шифрування |
| `03_encryption_tests.csv` | 3 | Результати тестів |
| `04_face_pipeline_vertical.png` | 4 | Схема pipeline (PNG, dpi=300) |
| `04_face_pipeline_vertical.pdf` | 4 | Схема pipeline (PDF, вектор) |

## Опис експериментів

### Експеримент 1: Верифікація облич

Підтверджує що евклідова відстань між 128D векторами однієї особи
менша ніж між різними особами. Будує гістограму з порогом 0.6.

### Експеримент 2: FAR / FRR / Accuracy

Обчислює біометричні метрики для tolerance = [0.40, 0.45, 0.50, 0.55, 0.60].
Показує trade-off: зниження tolerance зменшує FAR, але збільшує FRR.

### Експеримент 3: Шифрування біометрії

Демонструє принцип збереження 128D векторів у БД через Fernet.
Підтверджує цілісність, неможливість читання без ключа, рандомізацію IV.

### Експеримент 4: Схема pipeline

Візуалізує повний конвеєр обробки кадру: від препроцесингу до порівняння
з базою. Містить 7 блоків з умовними гілками (faces=0, spoofing).
Зберігається у PNG (dpi=300) та PDF (вектор) для вставки у Word.

**Підпис до рисунка:**
> Рис. X.X. Конвеєр обробки кадру в системі розпізнавання облич.
