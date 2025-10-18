"""
Gemeinsame Utilities für alle Migrationstools.
"""
import os
import csv
import re
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse


# Content-Type Detection
ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".txt", ".csv",
    ".docx", ".xlsx", ".pptx", ".mp4", ".mp3", ".wav"
}

CONTENT_TYPE_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/csv": ".csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "video/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "image/svg+xml": ".png",
}


def sniff_content_type(data: bytes) -> Optional[str]:
    """Content-Type anhand von Magic Bytes erkennen."""
    if len(data) >= 12:
        b = data[:12]
        if b.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        elif b.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        elif b.startswith(b"GIF87a") or b.startswith(b"GIF89a"):
            return "image/gif"
        elif b.startswith(b"%PDF-"):
            return "application/pdf"
        elif b[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp"
        elif b[:2] == b"PK":
            return "application/zip"

    # Fallback: HTML/SVG Detection über String-Inhalt
    try:
        sample = data[:2000].decode("utf-8")
        lower_sample = sample.lower()
        if "<svg" in lower_sample:
            return "image/svg+xml"
        elif "<html" in lower_sample:
            return "text/html"
        return "text/plain"
    except UnicodeDecodeError:
        return None


def get_extension_from_filename(filename: str) -> str:
    """Dateiendung aus Dateinamen extrahieren."""
    _, ext = os.path.splitext(filename)
    return ext.lower()


def get_safe_filename(original_name: str, content_type: str) -> str:
    """Sicheren Dateinamen für Notion-Upload generieren."""
    name, _ = os.path.splitext(original_name)

    # Bekannte Content-Types mappen
    ext = CONTENT_TYPE_TO_EXT.get(content_type)

    # Fallback: mimetypes oder .bin
    if not ext:
        ext = mimetypes.guess_extension(content_type) or ".bin"

    # Sicherheitscheck: nur erlaubte Extensions
    if ext not in ALLOWED_EXTENSIONS:
        if content_type.startswith("image/"):
            ext = ".png"
            content_type = "image/png"
        elif content_type.startswith("text/"):
            ext = ".txt"
            content_type = "text/plain"
        else:
            ext = ".pdf"
            content_type = "application/pdf"

    if not name:
        name = "file"

    return f"{name}{ext}"


def detect_content_type_and_filename(data: bytes, content_type_header: Optional[str],
                                   url: str) -> Tuple[str, str]:
    """Content-Type und sicheren Dateinamen bestimmen."""
    # Header-Content-Type (falls vorhanden)
    header_ct = (content_type_header or "").split(";")[0].strip() or None

    # Magic-Byte-Analyse
    guessed_ct = sniff_content_type(data)

    # Extension aus URL
    url_ext = get_extension_from_filename(os.path.basename(urlparse(url).path))

    # Besten Content-Type wählen
    chosen_ct = header_ct
    if not chosen_ct or chosen_ct == "application/octet-stream":
        chosen_ct = guessed_ct or (
            "image/png" if url_ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".svgz"}
            else None
        )

    if not chosen_ct:
        chosen_ct = "application/pdf"

    # Sicheren Dateinamen generieren
    basename = os.path.basename(urlparse(url).path) or "file"
    filename = get_safe_filename(basename, chosen_ct)

    return chosen_ct, filename


def sniff_csv_delimiter(file_path: Path) -> str:
    """CSV-Delimiter automatisch erkennen."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            sample = f.read(4096)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;|\t")
        return dialect.delimiter
    except Exception:
        return ";"


def read_csv_file(file_path: Path, delimiter: str) -> List[Dict[str, str]]:
    """CSV-Datei lesen und als Liste von Dictionaries zurückgeben."""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        return [row for row in reader]


def convert_to_iso_date(date_str: str) -> str:
    """Deutsches Datumsformat in ISO konvertieren."""
    if not date_str or not isinstance(date_str, str):
        return ""

    date_str = str(date_str).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", date_str):
        return date_str

    # Deutsche Formate versuchen
    patterns = [
        ("%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"),
        ("%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M"),
        ("%d.%m.%Y", "%Y-%m-%d"),
    ]

    for src_pattern, dst_pattern in patterns:
        try:
            return datetime.strptime(date_str, src_pattern).strftime(dst_pattern)
        except ValueError:
            continue

    return date_str


def split_multi_values(value: str, separator: str = ";") -> List[str]:
    """Mehrfachwerte aufsplitten und bereinigen."""
    if not value:
        return []

    return [part.strip() for part in str(value).split(separator) if part.strip()]


def join_multi_values(values: List[str], separator: str = ", ") -> str:
    """Mehrfachwerte für Notion zusammenfügen."""
    return separator.join(str(v) for v in values if v)


def find_column_by_name(headers: List[str], target_name: str) -> Optional[str]:
    """Spalte anhand von Namen finden (case-insensitive, trimmed)."""
    target_lower = target_name.strip().lower()

    for header in headers:
        if header.strip().lower() == target_lower:
            return header

    return None


def validate_file_exists(file_path: str) -> Path:
    """Datei-Pfad validieren und als Path zurückgeben."""
    path = Path(file_path).expanduser()

    if not path.exists():
        print(f"\n[❌] Fehler: Die angegebene Datei wurde nicht gefunden.")
        print(f"Gesucht wurde: {path.resolve()}")
        print(f"Aktueller Arbeitsordner: {Path.cwd()}")

        print("\nVorhandene Dateien im aktuellen Ordner:")
        for p in Path.cwd().iterdir():
            if p.is_file():
                print(f"  - {p.name}")

        print("\nTipp: korrekten Pfad/Dateinamen prüfen und gerade Anführungszeichen verwenden.\n")
        raise FileNotFoundError(f"Datei nicht gefunden: {path}")

    return path


def create_clean_csv_path(original_path: Path) -> Path:
    """Pfad für bereinigte CSV erstellen."""
    return original_path.with_name(original_path.stem + "_clean.csv")


def setup_rate_limiting(rate_per_second: float) -> float:
    """Rate Limiting konfigurieren."""
    return 1.0 / rate_per_second if rate_per_second > 0 else 0
