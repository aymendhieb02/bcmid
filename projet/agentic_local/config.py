"""Explicit local paths and model settings; nothing downloads on startup."""
from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
ARTIFACTS = Path(os.getenv("BCMID_ARTIFACTS", HERE / "artifacts")).resolve()
DATASET_ROOT = Path(os.getenv("BCMID_DATASET_ROOT", PROJECT / "bcmid" / "BCMID_extracted")).resolve()
REPORT_CHROMA = ARTIFACTS / "chroma_db"
IMAGE_FEATURES = ARTIFACTS / "embeddings_vit_clinicalbert_v1" / "images_vit.npy"
IMAGE_METADATA = ARTIFACTS / "embeddings_vit_clinicalbert_v1" / "images_metadata.json"
METADATA_CATALOG = ARTIFACTS / "feature_metadata_lookup_v1" / "metadata_catalog.json"
E5_MODEL = Path(os.getenv("BCMID_E5_MODEL", PROJECT / "rag" / "outputs" / "hf_cache" / "hub" / "models--intfloat--multilingual-e5-small"))
VIT_MODEL = Path(os.getenv("BCMID_VIT_MODEL", PROJECT / "rag" / "outputs" / "hf_cache" / "hub" / "models--google--vit-base-patch16-224-in21k"))
REPORT_COLLECTION = os.getenv("BCMID_REPORT_COLLECTION", "bcmid_9eedf7ad75897745db9a")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
IMAGE_BACKEND = os.getenv("BCMID_IMAGE_BACKEND", "vit").strip().lower()
API_HOST = os.getenv("BCMID_API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("BCMID_API_PORT", "8000"))
MAX_UPLOAD_BYTES = int(os.getenv("BCMID_MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
MAX_QUERY_CHARS = int(os.getenv("BCMID_MAX_QUERY_CHARS", "2000"))
