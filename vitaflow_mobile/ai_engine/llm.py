"""Gemini menu generation using the maintained Google GenAI Python SDK."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import os
import re
import threading
import time
import unicodedata
from collections import OrderedDict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

log = logging.getLogger(__name__)


class GeminiError(RuntimeError):
    user_message = "Gemini chưa thể tạo thực đơn. Vui lòng thử lại sau."


class GeminiConfigurationError(GeminiError):
    user_message = (
        "Chưa cấu hình GEMINI_API_KEY hợp lệ. Hãy kiểm tra file .env "
        "(không thêm dấu ngoặc kép hoặc dấu cách quanh giá trị)."
    )


class GeminiQuotaError(GeminiError):
    user_message = (
        "Gemini API đã chạm giới hạn sử dụng hoặc tốc độ yêu cầu. "
        "Hãy kiểm tra quota/billing trong Google AI Studio rồi thử lại sau."
    )


class GeminiModelError(GeminiError):
    user_message = (
        "Các model Gemini được cấu hình không khả dụng với API key hiện tại. "
        "Hãy kiểm tra GEMINI_MODEL trong file .env."
    )


class GeminiResponseError(GeminiError):
    user_message = (
        "Gemini đã phản hồi nhưng dữ liệu thực đơn không đúng cấu trúc. "
        "Hãy thử tạo lại; chi tiết đã được ghi vào terminal."
    )


class GeminiSDKError(GeminiError):
    user_message = (
        "Máy chủ chưa cài Google GenAI SDK. Hãy chạy: pip install -r requirements.txt "
        "trong môi trường ảo của dự án rồi khởi động lại Flask."
    )


class GeminiAPIError(GeminiError):
    user_message = (
        "Không kết nối được Gemini API. Hãy kiểm tra Internet, API key và trạng thái dịch vụ."
    )


class GeminiUnavailableError(GeminiError):
    user_message = (
        "Gemini đang quá tải (503). Hệ thống đã thử model dự phòng nhưng chưa nhận được phản hồi. "
        "Vui lòng thử lại sau ít phút."
    )


class GeminiTimeoutError(GeminiError):
    user_message = (
        "Gemini phản hồi quá lâu nên hệ thống đã dừng chờ. "
        "Vui lòng bấm tạo lại; nếu lặp lại, hãy kiểm tra kết nối mạng hoặc đổi model trong .env."
    )


# Flash-Lite is the low-latency, cost-efficient choice for this short JSON task.
# Keep stronger models as fallbacks rather than making the busiest model primary.
DEFAULT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_FALLBACKS = ("gemini-3.6-flash",)
PRIMARY_MODEL = (os.getenv("GEMINI_MODEL") or DEFAULT_MODEL).strip()
FALLBACK_MODELS = tuple(
    model.strip()
    for model in (os.getenv("GEMINI_FALLBACK_MODELS") or ",".join(DEFAULT_FALLBACKS)).split(",")
    if model.strip()
)
MODEL_CANDIDATES = tuple(dict.fromkeys((PRIMARY_MODEL, *FALLBACK_MODELS)))
MEAL_KEYS = ("bua_sang", "bua_trua", "bua_toi")
# The SDK otherwise retries transient HTTP failures internally (default: up to
# five attempts). We disable those hidden retries and perform one explicit,
# observable fallback request per model for 503 overloads.
SDK_HTTP_ATTEMPTS = 1
MAX_OUTPUT_TOKENS = 1024

# --- Tối ưu độ trễ -----------------------------------------------------------
# 1) Dòng Gemini 3.x mặc định thinking_level="high": model "suy nghĩ sâu" trước khi trả lời,
#    rất chậm với tác vụ chọn món -> JSON ngắn. Mặc định "low" (hoặc "minimal"/"off" qua .env).
THINKING_LEVEL = (os.getenv("GEMINI_THINKING_LEVEL") or "low").strip().lower()
# 2) Mỗi model chờ tối đa N giây rồi chuyển sang model dự phòng (không treo vô hạn).
REQUEST_TIMEOUT_S = float(os.getenv("GEMINI_TIMEOUT_S") or 25)
# 3) Cache kết quả theo nội dung prompt: cùng thông số + ghi chú -> trả ngay, không gọi API.
CACHE_TTL_S = int(os.getenv("MENU_CACHE_TTL_SECONDS") or 1800)
CACHE_MAX_ENTRIES = 128

_client = None
_client_api_key = None
_cache: "OrderedDict[str, tuple[float, dict[str, Any]]]" = OrderedDict()
_cache_lock = threading.Lock()


def _get_client():
    global _client, _client_api_key
    api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        raise GeminiConfigurationError("Thiếu GEMINI_API_KEY/GOOGLE_API_KEY.")
    if _client is not None and _client_api_key == api_key:
        return _client
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise GeminiSDKError("Thiếu package google-genai.") from exc
    try:
        retry_options = types.HttpRetryOptions(attempts=SDK_HTTP_ATTEMPTS)
        http_options = types.HttpOptions(
            retry_options=retry_options,
            timeout=int(REQUEST_TIMEOUT_S * 1000),  # SDK tính bằng mili-giây
        )
        _client = genai.Client(api_key=api_key, http_options=http_options)
        _client_api_key = api_key
        return _client
    except Exception as exc:
        log.exception("Không thể khởi tạo Google GenAI client")
        raise GeminiConfigurationError("Không khởi tạo được Google GenAI client.") from exc


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("JSON gốc không phải object.")
    return value


def _norm_name(name: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(name))).strip().casefold()


def _base_name(name: str) -> str:
    """'Phở bò (1 tô)' -> 'phở bò': bỏ phần khẩu phần trong ngoặc để khớp khi model viết tên rút gọn."""
    return _norm_name(re.sub(r"\(.*?\)", " ", str(name)))


def _validate_menu(data: dict[str, Any], allowed_food_names: set[str] | frozenset[str] | None = None) -> dict[str, Any]:
    # Khớp tên món không phân biệt hoa/thường, khoảng trắng thừa, dạng Unicode.
    lookup = {_norm_name(n): n for n in allowed_food_names} if allowed_food_names is not None else None
    base_lookup: dict[str, list[str]] = {}
    for n in allowed_food_names or ():
        base_lookup.setdefault(_base_name(n), []).append(n)
    clean: dict[str, Any] = {}
    for key in MEAL_KEYS:
        items = data.get(key)
        if not isinstance(items, list) or not items:
            raise ValueError(f"Thiếu hoặc rỗng khóa '{key}'.")
        clean[key] = []
        for item in items:
            if not isinstance(item, dict) or not str(item.get("ten_mon", "")).strip():
                raise ValueError(f"Món ăn trong '{key}' thiếu ten_mon.")

            name = str(item["ten_mon"]).strip()
            if lookup is not None:
                canonical = lookup.get(_norm_name(name))
                if canonical is None:
                    # Model hay viết "Phở bò" thay vì "Phở bò (1 tô)": khớp theo tên gốc nếu không mơ hồ.
                    candidates = base_lookup.get(_base_name(name), [])
                    if len(candidates) == 1:
                        canonical = candidates[0]
                if canonical is None:
                    # Bỏ món không có trong kho thay vì bắt người dùng chờ gọi lại cả lượt.
                    log.warning("Bỏ món ngoài danh mục do Gemini đề xuất: %r", name)
                    continue
                name = canonical

            try:
                portion = float(item.get("dinh_luong_g", 0))
                calories = float(item.get("calo", 0))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Định lượng/calo của '{name}' không phải số.") from exc

            if not math.isfinite(portion) or not (1 <= portion <= 2000):
                raise ValueError(f"Định lượng của '{name}' không hợp lệ.")
            if not math.isfinite(calories) or not (0 < calories <= 2500):
                raise ValueError(f"Calo của '{name}' không hợp lệ.")

            clean[key].append(
                {
                    "ten_mon": name,
                    "dinh_luong_g": round(portion, 1),
                    "calo": round(calories, 1),
                }
            )
        if not clean[key]:
            raise ValueError(f"Không còn món hợp lệ nào trong '{key}'.")
    return clean


def _build_prompt(user_stats: dict[str, Any], food_context: str, notes: str) -> str:
    """Phần CỐ ĐỊNH (quy tắc + danh mục) đặt trước, phần theo từng người đặt sau cùng.

    Gemini tự động cache tiền tố prompt giống nhau (implicit caching) nên cách sắp xếp này
    giúp các lượt sau nhanh và rẻ hơn.
    """
    macro = user_stats["macro"]
    return f"""Bạn là trợ lý gợi ý thực đơn tham khảo bằng tiếng Việt.
Hãy tạo thực đơn cho MỘT NGÀY gồm đúng 3 bữa: sáng, trưa, tối.

QUY TẮC BẮT BUỘC:
1. Chỉ chọn món trong DANH MỤC THỰC PHẨM và chép NGUYÊN VĂN tên món, GỒM CẢ phần khẩu phần trong ngoặc (ví dụ \"Phở bò (1 tô)\", không viết \"Phở bò\"). Không tự tạo món mới.
2. Không chọn món vi phạm dị ứng hoặc yêu cầu kiêng ăn. Nếu ghi chú mơ hồ, hãy ưu tiên loại trừ an toàn.
3. Cả ba bữa đều phải có ít nhất một món; ưu tiên đa dạng nhóm tinh bột, đạm, rau củ và trái cây.
4. Phân bổ năng lượng hợp lý giữa ba bữa; tổng calo nên gần mục tiêu nhưng không được khẳng định chính xác tuyệt đối.
5. `dinh_luong_g` là khối lượng ước tính theo gram; `calo` là năng lượng ước tính cho phần ăn đó.
6. Đây là gợi ý tham khảo, không phải tư vấn y tế. Không đề xuất nhịn ăn hoặc chế độ cực đoan.

DANH MỤC THỰC PHẨM (giá trị dinh dưỡng theo khẩu phần ghi trong tên món):
{food_context}

Chỉ trả về JSON hợp lệ, không Markdown, không giải thích, đúng cấu trúc:
{{
  "bua_sang": [{{"ten_mon": "Tên món chính xác", "dinh_luong_g": 150, "calo": 200}}],
  "bua_trua": [{{"ten_mon": "Tên món chính xác", "dinh_luong_g": 200, "calo": 450}}],
  "bua_toi": [{{"ten_mon": "Tên món chính xác", "dinh_luong_g": 150, "calo": 350}}]
}}

THÔNG SỐ MỤC TIÊU CỦA NGƯỜI DÙNG (ước tính):
- Năng lượng mục tiêu: {user_stats['calo_muc_tieu']} kcal/ngày.
- Protein: {macro['protein_g']} g/ngày. Carb: {macro['carb_g']} g/ngày. Fat: {macro['fat_g']} g/ngày.
- Dị ứng, kiêng ăn hoặc sở thích: {notes or 'Không có ghi chú.'}
"""


def _classify_api_error(exc: Exception) -> str:
    message = str(exc).lower()
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    status_text = str(status).lower()
    combined = f"{status_text} {message}"
    if status in (401, 403) or any(token in combined for token in (
        "api key not valid", "invalid api key", "permission_denied", "unauthenticated"
    )):
        return "auth"
    if status == 429 or any(token in combined for token in (
        "429", "quota", "resource_exhausted", "rate limit", "too many requests"
    )):
        return "quota"
    if status == 404 or any(token in combined for token in (
        "404", "not found", "model is not available", "unsupported model"
    )):
        return "model"
    if status == 504 or isinstance(exc, TimeoutError) or any(token in combined for token in (
        "timed out", "timeout", "deadline_exceeded", "deadline exceeded", "readtimeout"
    )):
        return "timeout"
    if status == 503 or any(token in combined for token in (
        "503", "unavailable", "service unavailable", "overloaded"
    )):
        return "overloaded"
    return "api"


def _thinking_config(types: Any, model_name: str) -> Any:
    """Giảm 'thinking' cho tác vụ đơn giản. Trả None nếu không áp dụng được."""
    mode = THINKING_LEVEL
    if mode in {"", "off", "none", "default"}:
        return None
    name = model_name.lower()
    try:
        if name.startswith("gemini-3"):
            level = mode if mode in {"minimal", "low", "medium", "high"} else "low"
            return types.ThinkingConfig(thinking_level=level)
        if name.startswith("gemini-2.5") and "pro" not in name:
            return types.ThinkingConfig(thinking_budget=0)  # 2.5 Pro không tắt được
    except (AttributeError, TypeError, ValueError):
        # SDK cũ chưa có thinking_level -> chạy mặc định thay vì hỏng cả tính năng.
        log.warning("SDK chưa hỗ trợ thinking_level; hãy nâng cấp: pip install -U google-genai")
    return None


def _call_model(client: Any, types: Any, model_name: str, prompt: str) -> Any:
    base = {
        "response_mime_type": "application/json",
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "temperature": 0.2,
    }
    thinking = _thinking_config(types, model_name)
    attempts = [thinking, None] if thinking is not None else [None]
    last_exc: Exception | None = None
    for thinking_cfg in attempts:
        kwargs = dict(base)
        if thinking_cfg is not None:
            kwargs["thinking_config"] = thinking_cfg
        try:
            return client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(**kwargs),
            )
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            # Model từ chối cấu hình thinking (400) -> thử lại đúng 1 lần không có thinking.
            if (
                thinking_cfg is not None
                and "thinking" in str(exc).lower()
                and _classify_api_error(exc) == "api"
            ):
                log.warning("Model %s từ chối thinking config (%s); thử lại không có.", model_name, str(exc)[:200])
                continue
            raise
    raise last_exc  # type: ignore[misc]


def _cache_key(prompt: str) -> str:
    return hashlib.sha256((",".join(MODEL_CANDIDATES) + "\n" + prompt).encode("utf-8")).hexdigest()


def _cache_get(key: str) -> dict[str, Any] | None:
    if CACHE_TTL_S <= 0:
        return None
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        stored_at, value = entry
        if now - stored_at > CACHE_TTL_S:
            _cache.pop(key, None)
            return None
        _cache.move_to_end(key)
        return copy.deepcopy(value)


def _cache_put(key: str, value: dict[str, Any]) -> None:
    if CACHE_TTL_S <= 0:
        return
    with _cache_lock:
        _cache[key] = (time.monotonic(), copy.deepcopy(value))
        _cache.move_to_end(key)
        while len(_cache) > CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)


def warm_up() -> bool:
    """Nạp trước SDK + tạo client lúc khởi động để lượt đầu không phải chờ import (~1-2 giây)."""
    try:
        _get_client()
        return True
    except GeminiError:
        return False


def generate_menu(
    user_stats: dict[str, Any],
    food_context: str,
    notes: str = "",
    allowed_food_names: set[str] | frozenset[str] | None = None,
    *,
    fresh: bool = False,
    return_meta: bool = False,
) -> Any:
    """Tạo + kiểm tra thực đơn; có cache, timeout và model dự phòng.

    fresh=True bỏ qua cache (nút "Tạo lại"). return_meta=True trả (menu, meta) với meta gồm
    cached/model/seconds để giao diện hiển thị.
    """
    if not str(food_context or "").strip():
        raise GeminiResponseError("Danh mục thực phẩm gửi cho Gemini đang rỗng.")

    prompt = _build_prompt(user_stats, food_context, notes)
    key = _cache_key(prompt)
    if not fresh:
        hit = _cache_get(key)
        if hit is not None:
            log.info("Menu cache hit (không gọi Gemini).")
            return (hit, {"cached": True, "model": None, "seconds": 0.0}) if return_meta else hit

    client = _get_client()
    try:
        from google.genai import types
    except ImportError as exc:
        raise GeminiSDKError("Thiếu package google-genai.") from exc

    last_error: Exception | None = None
    last_kind = "api"
    saw_overload = False

    models = list(MODEL_CANDIDATES)
    invalid_retries = 0
    while models:
        model_name = models.pop(0)
        model_started = time.perf_counter()
        try:
            response = _call_model(client, types, model_name, prompt)
            raw_text = getattr(response, "text", None)
            if not raw_text:
                finish_reason = None
                try:
                    finish_reason = response.candidates[0].finish_reason
                except (AttributeError, IndexError, TypeError):
                    pass
                raise GeminiResponseError(
                    f"Gemini không trả text (finish_reason={finish_reason})."
                )

            menu = _validate_menu(_extract_json(raw_text), allowed_food_names)
            elapsed = time.perf_counter() - model_started
            log.info("Gemini menu generated: model=%s duration=%.2fs", model_name, elapsed)
            _cache_put(key, menu)
            meta = {"cached": False, "model": model_name, "seconds": round(elapsed, 1)}
            return (menu, meta) if return_meta else menu

        except GeminiResponseError:
            raise
        except (json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
            # JSON/thực đơn lỗi là lỗi nội dung của model (không phải đường truyền). Mỗi lượt chỉ ~2 giây
            # nên thử lại đúng 1 lần cùng model; vẫn hỏng thì dừng, không thử model khác để khỏi chờ lâu.
            last_error = exc
            last_kind = "response"
            log.warning("Model %s returned an invalid menu: %s", model_name, exc)
            if invalid_retries < 1:
                invalid_retries += 1
                models.insert(0, model_name)
                continue
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            last_kind = _classify_api_error(exc)
            elapsed = time.perf_counter() - model_started
            log.warning(
                "Gemini request failed (model=%s, type=%s, category=%s, duration=%.2fs): %s",
                model_name, type(exc).__name__, last_kind, elapsed, str(exc)[:400],
            )
            if last_kind in {"overloaded", "timeout"}:
                saw_overload = saw_overload or last_kind == "overloaded"
                continue
            if last_kind in {"auth", "quota"}:
                break
            continue  # model/api: thử model dự phòng

    if last_kind == "auth":
        raise GeminiConfigurationError("Gemini API từ chối API key hoặc quyền truy cập.") from last_error
    if last_kind == "quota":
        raise GeminiQuotaError("Gemini API trả về quota/rate-limit.") from last_error
    if last_kind == "timeout":
        raise GeminiTimeoutError("Hết thời gian chờ Gemini.") from last_error
    if saw_overload:
        raise GeminiUnavailableError("Các model Gemini được thử đều quá tải (503 UNAVAILABLE).") from last_error
    if last_kind == "model":
        raise GeminiModelError("Không model nào trong danh sách fallback khả dụng.") from last_error
    if last_kind == "response":
        raise GeminiResponseError("Gemini trả dữ liệu không đúng cấu trúc thực đơn.") from last_error
    raise GeminiAPIError("Tất cả yêu cầu Gemini đều thất bại.") from last_error
