import hashlib
import re
from pathlib import Path

def calculate_file_hash(filepath: Path | str) -> str:
    """Calculate SHA-256 hash of a file for deduplication."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

def format_bytes(size: int) -> str:
    """Convert bytes to human-readable format."""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.2f} GB"

def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent directory traversal or invalid characters."""
    # Strip path characters
    name = Path(filename).name
    # Keep alphanumeric, dashes, dots, underscores, spaces
    clean = re.sub(r'[^a-zA-Z0-9_\-\. ]', '_', name)
    # Prevent hidden files
    clean = clean.lstrip('.')
    return clean or "document"

def clean_text(text: str) -> str:
    """Clean and normalize extracted document text."""
    if not text:
        return ""
    # Replace weird ligatures and non-breaking spaces
    text = text.replace('\xa0', ' ').replace('\u200b', '')
    # Replace multiple spaces with single space
    text = re.sub(r'[ \t]+', ' ', text)
    # Replace more than 2 consecutive newlines with 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
