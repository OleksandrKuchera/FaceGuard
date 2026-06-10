#!/usr/bin/env python3
"""
Експеримент 3: Шифрування біометричних даних (Fernet)

Демонструє принцип збереження 128D векторів ознак у БД:
  1. Генерація Fernet-ключа
  2. Серіалізація numpy-масиву через pickle
  3. Шифрування через Fernet (AES-128-CBC + HMAC-SHA256)
  4. Дешифрування та відновлення масиву
  5. Перевірка цілісності (дані відновлені точно)

Підтверджує, що:
  - зашифровані дані неможливо прочитати без ключа;
  - Fernet гарантує цілісність (пошкоджені дані викликають помилку);
  - оригінал відновлюється без втрат.
"""

import argparse
import csv
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from cryptography.fernet import Fernet, InvalidToken
from numpy.typing import NDArray

matplotlib.use("Agg")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class EncryptionTestResult:
    test_name: str
    success: bool
    details: str
    duration_ms: float = 0.0


def generate_key() -> bytes:
    """Генерує новий Fernet-ключ."""
    return Fernet.generate_key()


def encrypt_encoding(encoding: NDArray[np.float64], key: bytes) -> bytes:
    """Серіалізує + шифрує 128D вектор."""
    import pickle
    raw = pickle.dumps(encoding, protocol=pickle.HIGHEST_PROTOCOL)
    return Fernet(key).encrypt(raw)


def decrypt_encoding(encrypted: bytes, key: bytes) -> NDArray[np.float64]:
    """Дешифрує + десеріалізує."""
    import pickle
    raw = Fernet(key).decrypt(encrypted)
    return pickle.loads(raw)


def test_roundtrip(key: bytes) -> EncryptionTestResult:
    """Тест: шифрування → дешифрування → порівняння з оригіналом."""
    start = time.perf_counter()
    original = np.random.rand(128).astype(np.float64)
    encrypted = encrypt_encoding(original, key)
    recovered = decrypt_encoding(encrypted, key)
    elapsed = (time.perf_counter() - start) * 1000

    match = np.array_equal(original, recovered)
    return EncryptionTestResult(
        test_name="Roundtrip (encrypt → decrypt)",
        success=match,
        details=f"Відновлено точно: {match}, час: {elapsed:.2f}мс",
        duration_ms=elapsed,
    )


def test_wrong_key(key: bytes) -> EncryptionTestResult:
    """Тест: дешифрування неправильним ключем викликає помилку."""
    start = time.perf_counter()
    original = np.random.rand(128).astype(np.float64)
    encrypted = encrypt_encoding(original, key)
    wrong_key = generate_key()

    try:
        decrypt_encoding(encrypted, wrong_key)
        elapsed = (time.perf_counter() - start) * 1000
        return EncryptionTestResult(
            test_name="Дешифрування неправильним ключем",
            success=False,
            details="ПОМИЛКА: не викликало InvalidToken!",
            duration_ms=elapsed,
        )
    except InvalidToken:
        elapsed = (time.perf_counter() - start) * 1000
        return EncryptionTestResult(
            test_name="Дешифрування неправильним ключем",
            success=True,
            details="Correctly raised InvalidToken",
            duration_ms=elapsed,
        )


def test_corrupted_data(key: bytes) -> EncryptionTestResult:
    """Тест: пошкоджені дані викликають помилку."""
    start = time.perf_counter()
    original = np.random.rand(128).astype(np.float64)
    encrypted = bytearray(encrypt_encoding(original, key))
    encrypted[10] ^= 0xFF  # пошкодити байт

    try:
        decrypt_encoding(bytes(encrypted), key)
        elapsed = (time.perf_counter() - start) * 1000
        return EncryptionTestResult(
            test_name="Пошкоджені дані",
            success=False,
            details="ПОМИЛКА: не викликало InvalidToken!",
            duration_ms=elapsed,
        )
    except InvalidToken:
        elapsed = (time.perf_counter() - start) * 1000
        return EncryptionTestResult(
            test_name="Пошкоджені дані",
            success=True,
            details="Correctly raised InvalidToken (цілісність HMAC)",
            duration_ms=elapsed,
        )


def test_data_not_readable(key: bytes) -> EncryptionTestResult:
    """Тест: зашифровані дані не містять відкритого вектора."""
    start = time.perf_counter()
    original = np.random.rand(128).astype(np.float64)
    encrypted = encrypt_encoding(original, key)

    import pickle
    raw_pickle = pickle.dumps(original, protocol=pickle.HIGHEST_PROTOCOL)
    is_leaked = raw_pickle in encrypted

    elapsed = (time.perf_counter() - start) * 1000
    return EncryptionTestResult(
        test_name="Відсутність відкритих даних",
        success=not is_leaked,
        details=f"Сирий pickle у ciphertext: {is_leaked} (має бути False)",
        duration_ms=elapsed,
    )


def test_multiple_encryptions(key: bytes) -> EncryptionTestResult:
    """Тест: одне й те саме значення дає різний ciphertext (IV рандомізований)."""
    start = time.perf_counter()
    original = np.random.rand(128).astype(np.float64)
    enc1 = encrypt_encoding(original, key)
    enc2 = encrypt_encoding(original, key)
    different = enc1 != enc2
    elapsed = (time.perf_counter() - start) * 1000

    return EncryptionTestResult(
        test_name="Рандомізація IV",
        success=different,
        details=f"Однакові ciphertext: {not different} (має бути False)",
        duration_ms=elapsed,
    )


def save_results_csv(results: list[EncryptionTestResult], output_path: Path) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["test_name", "success", "details", "duration_ms"])
        for r in results:
            writer.writerow([r.test_name, r.success, r.details, f"{r.duration_ms:.2f}"])
    logger.info("CSV збережено: %s", output_path)


def plot_results(results: list[EncryptionTestResult], output_path: Path) -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    names = [r.test_name[:30] for r in results]
    durations = [r.duration_ms for r in results]
    colors = ["green" if r.success else "red" for r in results]

    ax1.barh(names, durations, color=colors, alpha=0.7)
    ax1.set_xlabel("Час виконання (мс)")
    ax1.set_title("Час виконання тестів")
    ax1.grid(True, alpha=0.3, axis="x")

    passed = sum(1 for r in results if r.success)
    failed = len(results) - passed
    ax2.pie(
        [passed, failed],
        labels=["Passed", "Failed"],
        colors=["green", "red"],
        autopct="%1.1f%%",
        startangle=90,
    )
    ax2.set_title("Результати тестів")

    fig.suptitle("Експеримент 3: Шифрування біометричних даних (Fernet)", fontsize=14)
    fig.tight_layout()
    fig.savefig(str(output_path), dpi=300)
    plt.close(fig)
    logger.info("Графік збережено: %s", output_path)


def print_report(results: list[EncryptionTestResult], key: bytes) -> None:
    sep = "=" * 60
    print()
    print(sep)
    print("  ЕКСПЕРИМЕНТ 3: ШИФРУВАННЯ БІОМЕТРИЧНИХ ДАНИХ")
    print(sep)
    print()
    print(f"  Fernet-ключ (перші 20 символів): {key.decode()[:20]}...")
    print(f"  Розмір ключа: {len(key)} байт (URL-safe base64)")
    print()

    for r in results:
        status = "✓ PASS" if r.success else "✗ FAIL"
        print(f"  {status}  {r.test_name}")
        print(f"         {r.details}")
        print()

    passed = sum(1 for r in results if r.success)
    total = len(results)
    print(f"  Результат: {passed}/{total} тестів пройдено")
    print()
    print(sep)


def main() -> None:
    parser = argparse.ArgumentParser(description="Експеримент 3: Шифрування Fernet")
    parser.add_argument("--output-dir", type=str, default="output")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    key = generate_key()
    logger.info("Fernet-ключ згенеровано")

    tests = [
        test_roundtrip(key),
        test_wrong_key(key),
        test_corrupted_data(key),
        test_data_not_readable(key),
        test_multiple_encryptions(key),
    ]

    save_results_csv(tests, output_dir / "03_encryption_tests.csv")
    plot_results(tests, output_dir / "03_encryption_results.png")
    print_report(tests, key)

    logger.info("Експеримент 3 завершено. Результати у: %s", output_dir)


if __name__ == "__main__":
    main()
