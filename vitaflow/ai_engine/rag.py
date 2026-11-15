"""RAG utilities for the GYMFlow food catalogue.

The CSV is the source of truth. Its SHA-256 fingerprint is stored in the
Chroma collection metadata so changed/new food rows are synchronized on the
next AI Coach request instead of being ignored when the collection is non-empty.
"""

from __future__ import annotations

import csv
import hashlib
import logging
import math
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV_PATH = PROJECT_ROOT / "data" / "food_data.csv"
DB_DIR = Path(os.getenv("CHROMA_DB_DIR", str(PROJECT_ROOT / "chroma_db_data"))).resolve()
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "food_collection")
EMBEDDING_MODEL = os.getenv(
    "FOOD_EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
)
REQUIRED_COLUMNS = ("ID", "TenMon", "Calo", "Protein", "Carb", "Fat", "TheLoai")
BATCH_SIZE = 100


class FoodDataError(RuntimeError):
    """A readable failure related to the CSV food catalogue or ChromaDB."""

    user_message = (
        "Không thể nạp kho dữ liệu món ăn. Hãy kiểm tra data/food_data.csv "
        "và xem thông báo lỗi trong cửa sổ chạy Flask."
    )


_client = None
_collection = None
_catalog_cache_key: tuple[int, int] | None = None
_catalog_cache_rows: list[dict[str, Any]] | None = None


def _get_collection():
    """Create the Chroma client/collection lazily, only when AI Coach is used."""
    global _client, _collection
    if _collection is not None:
        return _collection

    try:
        import chromadb
        from chromadb.utils import embedding_functions

        DB_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(DB_DIR))
        embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL
        )
        _collection = _client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=embedding_function,
            metadata={"hnsw:space": "cosine"},
        )
        log.info("ChromaDB ready: collection=%s, count=%d", COLLECTION_NAME, _collection.count())
        return _collection
    except Exception as exc:
        log.exception("Không thể khởi tạo ChromaDB/embedding model")
        raise FoodDataError(
            "Không khởi tạo được ChromaDB hoặc mô hình embedding. "
            "Kiểm tra các package chromadb, sentence-transformers và kết nối tải model lần đầu."
        ) from exc


def _read_food_csv(csv_path: str | Path = DEFAULT_CSV_PATH) -> tuple[list[dict[str, Any]], str]:
    """Read and validate the CSV. Supports UTF-8 with or without BOM."""
    path = Path(csv_path).expanduser().resolve()
    if not path.is_file():
        raise FoodDataError(f"Không tìm thấy file dữ liệu thực phẩm: {path}")

    try:
        raw_bytes = path.read_bytes()
        source_hash = hashlib.sha256(raw_bytes).hexdigest()
        with path.open("r", encoding="utf-8-sig", newline="") as file_obj:
            reader = csv.DictReader(file_obj)
            headers = set(reader.fieldnames or [])
            missing = [column for column in REQUIRED_COLUMNS if column not in headers]
            if missing:
                raise FoodDataError(
                    "CSV thiếu các cột bắt buộc: " + ", ".join(missing)
                )

            rows: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            for line_number, raw_row in enumerate(reader, start=2):
                food_id = str(raw_row.get("ID", "")).strip()
                name = str(raw_row.get("TenMon", "")).strip()
                category = str(raw_row.get("TheLoai", "")).strip()
                if not food_id or not name or not category:
                    raise FoodDataError(
                        f"Dòng {line_number}: ID, TenMon và TheLoai không được để trống."
                    )
                if food_id in seen_ids:
                    raise FoodDataError(f"Dòng {line_number}: ID '{food_id}' bị trùng.")
                seen_ids.add(food_id)

                numeric: dict[str, float] = {}
                for column in ("Calo", "Protein", "Carb", "Fat"):
                    try:
                        value = float(str(raw_row.get(column, "")).strip())
                    except (TypeError, ValueError) as exc:
                        raise FoodDataError(
                            f"Dòng {line_number}: cột {column} phải là số."
                        ) from exc
                    if not math.isfinite(value) or value < 0:
                        raise FoodDataError(
                            f"Dòng {line_number}: cột {column} phải là số hữu hạn không âm."
                        )
                    numeric[column] = value

                rows.append(
                    {
                        "id": food_id,
                        "TenMon": name,
                        "Calo": numeric["Calo"],
                        "Protein": numeric["Protein"],
                        "Carb": numeric["Carb"],
                        "Fat": numeric["Fat"],
                        "TheLoai": category,
                    }
                )

        if not rows:
            raise FoodDataError("File food_data.csv không có dòng thực phẩm nào.")
        return rows, source_hash
    except FoodDataError:
        raise
    except (OSError, UnicodeError, csv.Error) as exc:
        log.exception("Không đọc được CSV thực phẩm: %s", path)
        raise FoodDataError(f"Không đọc được file CSV thực phẩm: {path.name}") from exc


def ingest_data_to_chroma(csv_path: str | Path = DEFAULT_CSV_PATH, force: bool = False) -> int:
    """Synchronize the complete CSV into ChromaDB using stable IDs and upsert."""
    rows, source_hash = _read_food_csv(csv_path)
    collection = _get_collection()
    current_metadata = dict(collection.metadata or {})

    if (
        not force
        and current_metadata.get("source_sha256") == source_hash
        and collection.count() == len(rows)
    ):
        log.info("Food CSV unchanged; keeping %d Chroma records.", len(rows))
        return len(rows)

    ids = [row["id"] for row in rows]
    documents = [
        (
            f"{row['TenMon']} | Loại: {row['TheLoai']} | "
            f"Calo: {row['Calo']} kcal | Protein: {row['Protein']}g | "
            f"Carb: {row['Carb']}g | Fat: {row['Fat']}g"
        )
        for row in rows
    ]
    metadatas = [
        {
            "TenMon": row["TenMon"],
            "Calo": float(row["Calo"]),
            "Protein": float(row["Protein"]),
            "Carb": float(row["Carb"]),
            "Fat": float(row["Fat"]),
            "TheLoai": row["TheLoai"],
        }
        for row in rows
    ]

    try:
        for offset in range(0, len(ids), BATCH_SIZE):
            batch = slice(offset, offset + BATCH_SIZE)
            collection.upsert(
                ids=ids[batch],
                documents=documents[batch],
                metadatas=metadatas[batch],
            )

        # Remove records which were deleted from the source CSV.
        existing_ids = set(collection.get().get("ids", []))
        stale_ids = sorted(existing_ids - set(ids))
        for offset in range(0, len(stale_ids), BATCH_SIZE):
            collection.delete(ids=stale_ids[offset : offset + BATCH_SIZE])

        current_metadata.update(
            {
                "source_sha256": source_hash,
                "source_filename": Path(csv_path).name,
                "source_rows": len(rows),
            }
        )
        collection.modify(metadata=current_metadata)

        actual_count = collection.count()
        if actual_count != len(rows):
            raise FoodDataError(
                f"Đồng bộ CSV chưa hoàn tất: CSV có {len(rows)} món, ChromaDB có {actual_count} món."
            )
        log.info("Đã đồng bộ %d món từ %s vào ChromaDB.", actual_count, Path(csv_path).name)
        return actual_count
    except FoodDataError:
        raise
    except Exception as exc:
        log.exception("Lỗi khi đồng bộ CSV vào ChromaDB")
        raise FoodDataError(
            "Không thể đồng bộ dữ liệu CSV vào ChromaDB. Xem traceback trong terminal."
        ) from exc


def get_food_catalog(csv_path: str | Path = DEFAULT_CSV_PATH) -> list[dict[str, Any]]:
    """Load the small food catalogue directly from CSV, without starting Chroma.

    AI Coach currently sends the complete catalogue to Gemini, so vector search
    adds no value to this request path. Chroma remains available through
    ``search_foods`` for future semantic-search features. Results are cached by
    file modification time and size; editing the CSV invalidates the cache.
    """
    global _catalog_cache_key, _catalog_cache_rows
    path = Path(csv_path).expanduser().resolve()
    try:
        stat = path.stat()
    except OSError as exc:
        raise FoodDataError(f"Không tìm thấy hoặc không đọc được file dữ liệu: {path.name}") from exc

    cache_key = (stat.st_mtime_ns, stat.st_size)
    if _catalog_cache_key == cache_key and _catalog_cache_rows is not None:
        return [row.copy() for row in _catalog_cache_rows]

    rows, _source_hash = _read_food_csv(path)
    # Re-stat after reading so a concurrent file replacement is not cached
    # under the metadata captured before the read.
    stat_after = path.stat()
    _catalog_cache_key = (stat_after.st_mtime_ns, stat_after.st_size)
    _catalog_cache_rows = [row.copy() for row in rows]
    log.info("Loaded %d foods directly from %s (Chroma not required).", len(rows), path.name)
    return [row.copy() for row in rows]


_prompt_cache_key: tuple[int, int] | None = None
_prompt_cache_value: tuple[str, frozenset[str]] | None = None


def _num(value: float) -> str:
    """188.0 -> '188', 0.5 -> '0.5' (ngắn gọn hơn để prompt nhẹ hơn)."""
    return f"{float(value):g}"


def get_prompt_catalog(csv_path: str | Path = DEFAULT_CSV_PATH) -> tuple[str, frozenset[str]]:
    """Trả về (food_context, tên món hợp lệ) đã dựng sẵn và cache theo mtime/size của CSV.

    Trước đây mỗi lượt gọi đều dựng lại chuỗi 95 dòng; giờ chỉ dựng khi CSV đổi.
    """
    global _prompt_cache_key, _prompt_cache_value
    foods = get_food_catalog(csv_path)
    if _prompt_cache_value is not None and _prompt_cache_key == _catalog_cache_key:
        return _prompt_cache_value
    context = "\n".join(
        f"{food['TenMon']} [{food['TheLoai']}]: {_num(food['Calo'])}kcal, "
        f"P{_num(food['Protein'])}g C{_num(food['Carb'])}g F{_num(food['Fat'])}g"
        for food in foods
    )
    value = (context, frozenset(food["TenMon"] for food in foods))
    _prompt_cache_key, _prompt_cache_value = _catalog_cache_key, value
    return value


def search_foods(query_text: str, n_results: int = 10, the_loai_filter: str | None = None) -> list[str]:
    """Semantic search helper retained for other parts of the project."""
    if not str(query_text or "").strip():
        raise ValueError("query_text không được để trống.")
    ingest_data_to_chroma()
    collection = _get_collection()
    count = collection.count()
    if count == 0:
        return []

    where = {"TheLoai": the_loai_filter} if the_loai_filter else None
    try:
        results = collection.query(
            query_texts=[query_text],
            n_results=max(1, min(int(n_results), count)),
            where=where,
        )
        context_list = []
        metadatas = (results.get("metadatas") or [[]])[0]
        for meta in metadatas:
            context_list.append(
                f"Tên: {meta['TenMon']} | Calo: {meta['Calo']} | "
                f"P: {meta['Protein']}g | C: {meta['Carb']}g | "
                f"F: {meta['Fat']}g | Loại: {meta['TheLoai']}"
            )
        return context_list
    except Exception as exc:
        log.exception("Lỗi truy vấn vector ChromaDB")
        raise FoodDataError("Không thể tìm kiếm món ăn trong ChromaDB.") from exc


if __name__ == "__main__":
    total = ingest_data_to_chroma(force=True)
    print(f"Đã đồng bộ {total} món ăn vào {DB_DIR}")
