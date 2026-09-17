"""Fill the shared model cache once, so nothing downloads at test time.

Run through `make warm-models`, which mounts this into the api image with the
offline flags turned off. An flock on the cache directory makes concurrent runs
from two worktrees wait rather than corrupt each other (BRANCH.md §9).
"""

import fcntl
import os
import sys
from pathlib import Path

CACHE_DIR = Path(os.environ.get("MODELS_CACHE_DIR", "/models"))
DOCLING_DIR = Path(os.environ.get("DOCLING_ARTIFACTS_DIR", str(CACHE_DIR / "docling")))
EMBEDDING_MODEL_ID = os.environ.get("EMBEDDING_MODEL_ID", "BAAI/bge-m3")


def warm_docling() -> None:
    from docling.utils.model_downloader import download_models

    DOCLING_DIR.mkdir(parents=True, exist_ok=True)
    print(f"docling: downloading layout + OCR artifacts into {DOCLING_DIR}")
    download_models(output_dir=DOCLING_DIR, progress=False)


def warm_embeddings() -> None:
    from sentence_transformers import SentenceTransformer

    print(f"embeddings: downloading {EMBEDDING_MODEL_ID}")
    SentenceTransformer(EMBEDDING_MODEL_ID, device="cpu")


def main() -> int:
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "MODELS_OFFLINE"):
        os.environ[key] = "0"

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = CACHE_DIR / ".warm-models.lock"
    with open(lock_path, "w") as lock:
        print(f"waiting for {lock_path}")
        fcntl.flock(lock, fcntl.LOCK_EX)
        failures = []
        for name, step in (("docling", warm_docling), ("embeddings", warm_embeddings)):
            try:
                step()
            except Exception as exc:
                failures.append(f"{name}: {type(exc).__name__}: {exc}")

    for failure in failures:
        print(f"FAILED {failure}", file=sys.stderr)
    if failures:
        return 1
    print(f"model cache warm at {CACHE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
