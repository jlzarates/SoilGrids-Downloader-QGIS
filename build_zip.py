"""Construye el ZIP instalable del plugin SoilGrids."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parent
PLUGIN = ROOT / "soilgrids_aoi_downloader"
DIST = ROOT / "dist"
OUTPUT = DIST / "SoilGrids_AOI_Downloader_0.1.1.zip"
REQUIRED = {
    "soilgrids_aoi_downloader/__init__.py",
    "soilgrids_aoi_downloader/metadata.txt",
    "soilgrids_aoi_downloader/plugin.py",
    "soilgrids_aoi_downloader/dialog.py",
    "soilgrids_aoi_downloader/tasks.py",
    "soilgrids_aoi_downloader/core/soilgrids.py",
    "soilgrids_aoi_downloader/core/__init__.py",
    "soilgrids_aoi_downloader/icon.svg",
    "soilgrids_aoi_downloader/README.md",
    "soilgrids_aoi_downloader/LICENSE",
}
EXCLUDED_PARTS = {"__pycache__", ".git", ".pytest_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp", ".part"}


def source_files():
    for path in sorted(PLUGIN.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if EXCLUDED_PARTS.intersection(relative.parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        yield path, relative.as_posix()


def validate_python(path):
    if path.suffix.lower() == ".py":
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


def build():
    DIST.mkdir(parents=True, exist_ok=True)
    files = list(source_files())
    if not files:
        raise RuntimeError("No se encontraron archivos del complemento")
    for path, _ in files:
        validate_python(path)

    temporary = OUTPUT.with_suffix(OUTPUT.suffix + ".part")
    if temporary.exists():
        temporary.unlink()
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, archive_name in files:
            archive.write(path, archive_name)
    temporary.replace(OUTPUT)


def validate_zip():
    with zipfile.ZipFile(OUTPUT, "r") as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise RuntimeError("Miembro ZIP corrupto: {0}".format(bad_member))
        names = set(archive.namelist())
        missing = sorted(REQUIRED - names)
        if missing:
            raise RuntimeError("Faltan archivos requeridos: {0}".format(missing))
        roots = {PurePosixPath(name).parts[0] for name in names}
        if roots != {"soilgrids_aoi_downloader"}:
            raise RuntimeError("El ZIP no tiene una unica carpeta raiz: {0}".format(roots))
        for name in names:
            item = PurePosixPath(name)
            if item.is_absolute() or ".." in item.parts or "\\" in name:
                raise RuntimeError("Ruta ZIP no segura: {0}".format(name))

    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    print("ZIP:", OUTPUT)
    print("Tamano:", OUTPUT.stat().st_size, "bytes")
    print("SHA256:", digest)


if __name__ == "__main__":
    build()
    validate_zip()
