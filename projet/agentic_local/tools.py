from __future__ import annotations

import json
import re
import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from config import (
    ARTIFACTS, DATASET_ROOT, E5_MODEL, IMAGE_BACKEND, IMAGE_FEATURES, IMAGE_METADATA,
    METADATA_CATALOG, REPORT_CHROMA, REPORT_COLLECTION, VIT_MODEL,
)

try:
    from functools import cache
except ImportError:  # pragma: no cover - Python 3.8 compatibility
    from functools import lru_cache as cache


def _snapshot_path(path: Path) -> Path:
    if (path / "config.json").exists() or (path / "modules.json").exists():
        return path
    snapshots = path / "snapshots"
    if snapshots.exists():
        candidates = sorted((p for p in snapshots.iterdir() if p.is_dir()), key=lambda p: p.name)
        if candidates:
            return candidates[-1]
    return path


@lru_cache(maxsize=1)
def _report_index():
    if not REPORT_CHROMA.exists():
        raise RuntimeError(f"Saved report Chroma directory is missing: {REPORT_CHROMA}")
    import chromadb
    client = chromadb.PersistentClient(path=str(REPORT_CHROMA))
    collection = client.get_collection(REPORT_COLLECTION)
    return client, collection


@lru_cache(maxsize=1)
def _e5_model():
    local_model = _snapshot_path(E5_MODEL)
    if not local_model.exists():
        raise RuntimeError(f"Local E5 model cache not found: {local_model}; auto-download is disabled")
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(str(local_model), local_files_only=True, device="cpu")


def embed_query(question: str) -> list[float]:
    if len(question) > 2200:
        raise ValueError("Search query exceeds 2200 characters")
    vector = _e5_model().encode(
        [f"query: {question.strip()}"], normalize_embeddings=True,
        convert_to_numpy=True, show_progress_bar=False,
    )[0]
    return vector.astype("float32").tolist()


def normalize_evidence_hit(passage_id: str, text: str, metadata: dict[str, Any], distance: float, rank: int) -> dict[str, Any]:
    """Canonical evidence registry row, retaining source and patient provenance."""
    metadata = dict(metadata or {})
    return {
        "passage_id": str(passage_id), "text": str(text or ""),
        "patient_id": str(metadata.get("patient_id")) if metadata.get("patient_id") is not None else None,
        "source": metadata.get("source"), "split": metadata.get("split"),
        "modality": metadata.get("modality"), "distance": float(distance),
        "similarity": 1.0 - float(distance), "rank": int(rank), "metadata": metadata,
    }


def search_reports(question: str, top_k: int = 5, exclude_patient_id: str | None = None) -> list[dict[str, Any]]:
    _, collection = _report_index()
    if collection.count() == 0:
        return []
    result = collection.query(
        query_embeddings=[embed_query(question)],
        n_results=min(max(1, int(top_k) * 4), collection.count()),
        include=["documents", "metadatas", "distances"],
    )
    rows = []
    for rank, (rid, text, meta, distance) in enumerate(zip(
        result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
    ), 1):
        meta = meta or {}
        if meta.get("split") != "train":
            continue
        pid = str(meta.get("patient_id", ""))
        if exclude_patient_id and pid == str(exclude_patient_id):
            continue
        if not pid:
            continue
        rows.append(normalize_evidence_hit(str(rid), text or "", meta, float(distance), rank))
        if len(rows) >= top_k:
            break
    return rows


@lru_cache(maxsize=1)
def load_catalog() -> list[dict[str, Any]]:
    if not METADATA_CATALOG.is_file():
        raise RuntimeError(f"Metadata catalog missing: {METADATA_CATALOG}")
    return json.loads(METADATA_CATALOG.read_text(encoding="utf-8"))


def metadata_lookup(filters: dict[str, Any]) -> dict[str, Any]:
    rows = load_catalog()
    split = str(filters.get("split", "train")).lower()
    if split != "train" and not filters.get("audit_mode"):
        return {"status": "invalid_filter", "total": 0, "results": [], "message": "Non-train lookup requires audit_mode=true"}
    modality = filters.get("modality")
    if modality is not None:
        aliases = {"mammo": "Mammogram", "mammography": "Mammogram", "mammogram": "Mammogram", "us": "Ultrasound", "ultrasound": "Ultrasound", "ultrasonography": "Ultrasound"}
        modality = aliases.get(re.sub(r"[\s_-]+", "", str(modality)).lower())
        if modality is None:
            return {"status": "invalid_filter", "total": 0, "results": [], "message": "Allowed modalities: Mammogram, Ultrasound"}
    birads = filters.get("birads")
    if birads is not None:
        birads = re.sub(r"^bi[\s-]*rads?\s*|^birad\s*", "", str(birads).lower()).replace(" ", "")
    out = []
    for row in rows:
        if row.get("split") != split: continue
        if filters.get("patient_id") and str(row.get("patient_id")) != str(filters["patient_id"]): continue
        if filters.get("image_id") and filters["image_id"] not in row.get("image_ids", []): continue
        if modality and modality not in row.get("modalities", []): continue
        if filters.get("has_report") is not None and bool(row.get("has_report")) != bool(filters["has_report"]): continue
        if filters.get("has_structured_report") is not None and bool(row.get("has_structured_report")) != bool(filters["has_structured_report"]): continue
        if birads and birads not in [str(x).lower().replace("birads", "").replace("bi-rads", "").strip() for x in row.get("birads_values", [])]: continue
        safe_row = dict(row)
        raw_paths = safe_row.pop("image_paths", [])
        safe_row["image_references"] = ["/".join(Path(str(p).replace("\\", "/")).as_posix().split("/")[-3:]) for p in raw_paths]
        out.append(safe_row)
    return {"status": "ok" if out else "not_found", "total": len(out), "filters_applied": filters, "results": out}


@cache
def _image_runtime():
    if IMAGE_BACKEND != "vit":
        raise RuntimeError(f"Unsupported local image backend '{IMAGE_BACKEND}'. Only cached ViT vectors are available; CLIP weights are not installed.")
    if not IMAGE_FEATURES.is_file() or not IMAGE_METADATA.is_file():
        raise RuntimeError("Saved local ViT image vectors/metadata are missing")
    if not _snapshot_path(VIT_MODEL).exists():
        raise RuntimeError("Local ViT weights unavailable; auto-download is disabled")
    import torch
    from PIL import Image, ImageOps
    from transformers import AutoImageProcessor, AutoModel
    device = "cpu"
    local_model = str(_snapshot_path(VIT_MODEL))
    processor = AutoImageProcessor.from_pretrained(local_model, local_files_only=True)
    model = AutoModel.from_pretrained(local_model, add_pooling_layer=False, local_files_only=True).to(device).eval()
    return torch, Image, ImageOps, processor, model, device


def search_images(image_path: Path, top_k: int = 5, modality: str | None = None,
                  exclude_patient_id: str | None = None) -> list[dict[str, Any]]:
    torch, Image, ImageOps, processor, model, device = _image_runtime()
    vectors = np.load(IMAGE_FEATURES, mmap_mode="r")
    metadata = json.loads(IMAGE_METADATA.read_text(encoding="utf-8"))
    with Image.open(image_path) as im:
        im = ImageOps.exif_transpose(im)
        rgba = im.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
        rgb = Image.alpha_composite(background, rgba).convert("RGB")
        prepared = ImageOps.pad(rgb, (224, 224), method=Image.Resampling.LANCZOS, color=(0, 0, 0))
        inputs = processor(images=prepared, do_resize=False, return_tensors="pt").to(device)
        rgb.close()
        prepared.close()
    with torch.inference_mode():
        query = model(**inputs).last_hidden_state[:, 0, :].float()
        query = torch.nn.functional.normalize(query, p=2, dim=1).cpu().numpy()[0]
    scores = np.asarray(vectors) @ query
    catalog_by_patient = {str(row.get("patient_id")): row for row in load_catalog()}
    best = np.argsort(scores)[::-1]
    found, seen_patients = [], set()
    for idx in best:
        meta = metadata[int(idx)]
        if meta.get("split") != "train": continue
        pid = str(meta.get("patient_id", ""))
        if exclude_patient_id and pid == str(exclude_patient_id): continue
        if pid in seen_patients: continue
        if modality and meta.get("modalite") != modality: continue
        seen_patients.add(pid)
        raw_path = Path(meta.get("path", ""))
        rel = Path(*raw_path.parts[-3:])
        try:
            local_path = DATASET_ROOT / rel
            local_path = local_path.resolve()
            local_path.relative_to(DATASET_ROOT)
            safe_path = str(local_path) if local_path.is_file() else None
        except (ValueError, OSError):
            safe_path = None
        relative_reference = rel.as_posix()
        stable_id = "img_" + hashlib.sha256(relative_reference.encode("utf-8")).hexdigest()[:20]
        catalog_row = catalog_by_patient.get(pid, {})
        found.append({
            "image_id": stable_id,
            "patient_id": pid, "modality": meta.get("modalite"),
            "split": meta.get("split"), "similarity": float(scores[idx]),
            "rank": len(found) + 1, "image_path": safe_path,
            "source_image_reference": relative_reference,
            "report_sources": catalog_row.get("report_sources", []),
            "association_level": catalog_row.get("alignment_level", "patient"),
            "association_warning": catalog_row.get("association_warning", "Patient-level association; exam-level link not verified."),
            "embedding_model": "google/vit-base-patch16-224-in21k",
        })
        if len(found) >= top_k: break
    return found


def local_model_status() -> dict[str, Any]:
    return {
        "e5_cache_present": _snapshot_path(E5_MODEL).exists(),
        "vit_cache_present": _snapshot_path(VIT_MODEL).exists(),
        "report_index_present": REPORT_CHROMA.exists(),
        "selected_report_collection": REPORT_COLLECTION,
        "image_backend": "vit_saved_features" if IMAGE_FEATURES.exists() and IMAGE_BACKEND == "vit" else "unavailable",
        "ollama_model": __import__("config").OLLAMA_MODEL,
        "image_warning": "ViT path is separate from Kaggle's CLIP index; Kaggle CLIP metrics do not validate this backend.",
    }
