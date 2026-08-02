"""Bounded Gemini Vision client for the two-photo product-name workflow."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Protocol


MAX_VISION_IMAGE_BYTES = 8 * 1024 * 1024
MAX_VISION_IMAGE_DIMENSION = 8_000
MAX_VISION_IMAGE_PIXELS = 32_000_000
MAX_GEMINI_IMAGE_DIMENSION = 1_800
MAX_GEMINI_RESPONSE_TOKENS = 512
# Two 1,800px-square images are at most 18 Gemini 768px tiles.  The small
# prompt allowance below rounds the documented image-token estimate upward,
# so the budget guard can reserve a request before calling Gemini.
MAX_GEMINI_INPUT_TOKENS = 6_000


@dataclass(frozen=True)
class GeminiUsage:
    """Provider token metadata used only for aggregate cost accounting."""

    prompt_tokens: int
    candidate_tokens: int
    thought_tokens: int = 0


class VisionError(RuntimeError):
    """A Vision result that can safely fall back to manual name entry."""

    def __init__(self, message: str, *, usage: GeminiUsage | None = None):
        super().__init__(message)
        self.usage = usage


class VisionRetryableError(VisionError):
    """A transient Gemini failure eligible for bounded retry."""


class VisionInputError(VisionError):
    """Image input is invalid or exceeds the explicit resource bounds."""


@dataclass(frozen=True)
class ProductVisionResult:
    same_product: bool
    suggested_name_th: str
    brand: str
    product_type: str
    variant: str
    size: str
    confidence: float
    warnings: tuple[str, ...]
    usage: GeminiUsage | None = None


class ProductVisionClient(Protocol):
    def analyze_product(self, images: list[bytes]) -> ProductVisionResult: ...


VISION_RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "same_product": {"type": "boolean"},
        "suggested_name_th": {"type": "string", "maxLength": 160},
        "brand": {"type": "string"},
        "product_type": {"type": "string"},
        "variant": {"type": "string"},
        "size": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "warnings": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
    },
    "required": [
        "same_product", "suggested_name_th", "brand", "product_type", "variant",
        "size", "confidence", "warnings",
    ],
}


VISION_PROMPT = """You receive exactly two photos intended to show the front and back of one retail product.
Return exactly one JSON object and no Markdown. Its only fields must be same_product (boolean),
suggested_name_th (string), brand (string), product_type (string), variant (string), size (string),
confidence (number from 0 to 1), and warnings (an array of strings). Use only text and facts visibly present
in the photos. Do not guess a
name, brand, variant, flavour, model, size, quantity, or volume that is not visible. If the photos clearly
show different products, set same_product to false. Suggest a Thai retail Product Master name in the order:
Brand + product/type + visible formula/flavour/model + visible size or quantity. Preserve the brand spelling
shown on the package. Exclude promotional copy, claims, benefits, directions, warnings, producer address,
telephone numbers, registration numbers, prices, barcodes, and emoji. Do not translate in a way that changes
meaning. Normalize whitespace. Keep suggested_name_th at 160 characters or fewer. If there is not enough
visible text for a safe name, return an empty suggested_name_th and explain why in warnings."""


def normalize_product_name(value: str) -> str:
    """Normalize a user-visible product name without inventing content."""

    return re.sub(r"\s+", " ", str(value or "").strip())


def _result_from_payload(payload: Any) -> ProductVisionResult:
    if not isinstance(payload, dict):
        raise VisionError("Gemini structured response was not an object.")
    required = set(VISION_RESULT_SCHEMA["required"])
    if set(payload) - set(VISION_RESULT_SCHEMA["properties"]) or not required.issubset(payload):
        raise VisionError("Gemini structured response did not match the required schema.")
    if not isinstance(payload["same_product"], bool):
        raise VisionError("Gemini structured response had an invalid same_product value.")
    string_fields = ("suggested_name_th", "brand", "product_type", "variant", "size")
    if any(not isinstance(payload[field], str) for field in string_fields):
        raise VisionError("Gemini structured response had invalid text fields.")
    confidence = payload["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise VisionError("Gemini structured response had an invalid confidence value.")
    warnings = payload["warnings"]
    if not isinstance(warnings, list) or len(warnings) > 20 or any(not isinstance(item, str) for item in warnings):
        raise VisionError("Gemini structured response had invalid warnings.")
    name = normalize_product_name(payload["suggested_name_th"])
    if len(name) > 160:
        raise VisionError("Gemini suggested a name longer than 160 characters.")
    return ProductVisionResult(
        same_product=payload["same_product"],
        suggested_name_th=name,
        brand=normalize_product_name(payload["brand"]),
        product_type=normalize_product_name(payload["product_type"]),
        variant=normalize_product_name(payload["variant"]),
        size=normalize_product_name(payload["size"]),
        confidence=float(confidence),
        warnings=tuple(normalize_product_name(item) for item in warnings),
    )


def _usage_integer(value: Any) -> int:
    """Read a non-negative SDK usage field without trusting arbitrary values."""

    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _response_usage(response: Any) -> GeminiUsage | None:
    """Extract token metadata from current and older Google SDK response shapes."""

    raw = getattr(response, "usage_metadata", None)
    if raw is None:
        raw = getattr(response, "usageMetadata", None)
    if raw is None:
        return None

    def field(*names: str) -> int:
        for name in names:
            value = raw.get(name) if isinstance(raw, dict) else getattr(raw, name, None)
            if value is not None:
                return _usage_integer(value)
        return 0

    usage = GeminiUsage(
        prompt_tokens=field("prompt_token_count", "promptTokenCount"),
        candidate_tokens=field("candidates_token_count", "candidatesTokenCount", "candidate_token_count"),
        thought_tokens=field("thoughts_token_count", "thoughtsTokenCount"),
    )
    return usage if any((usage.prompt_tokens, usage.candidate_tokens, usage.thought_tokens)) else None


def _prepared_jpeg(image_bytes: bytes) -> bytes:
    """Validate and downsize one LINE image entirely in memory."""

    if not isinstance(image_bytes, bytes) or not image_bytes or len(image_bytes) > MAX_VISION_IMAGE_BYTES:
        raise VisionInputError("Image content was empty or exceeded the size limit.")
    try:
        from PIL import Image

        with Image.open(BytesIO(image_bytes)) as inspected:
            inspected.verify()
        with Image.open(BytesIO(image_bytes)) as image:
            if image.width > MAX_VISION_IMAGE_DIMENSION or image.height > MAX_VISION_IMAGE_DIMENSION:
                raise VisionInputError("Image dimensions exceeded the limit.")
            if image.width * image.height > MAX_VISION_IMAGE_PIXELS:
                raise VisionInputError("Image pixel count exceeded the limit.")
            image.load()
            prepared = image.convert("RGB")
            prepared.thumbnail((MAX_GEMINI_IMAGE_DIMENSION, MAX_GEMINI_IMAGE_DIMENSION))
            output = BytesIO()
            try:
                prepared.save(output, format="JPEG", quality=85, optimize=True)
                return output.getvalue()
            finally:
                output.close()
                prepared.close()
    except VisionInputError:
        raise
    except Exception as exc:
        raise VisionInputError("Image content was not a readable image.") from exc


def _is_retryable_exception(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in ("timeout", "timed out", "429", "500", "502", "503", "504"))


class GoogleProductVisionClient:
    """Official Google Gen AI SDK implementation, created only when Vision mode is enabled."""

    def __init__(self, api_key: str, model: str, *, timeout_seconds: int = 25):
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def analyze_product(self, images: list[bytes]) -> ProductVisionResult:
        if len(images) != 2:
            raise VisionInputError("Vision analysis requires exactly two images.")
        prepared_images = [_prepared_jpeg(image) for image in images]
        response = None
        usage = None
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(
                api_key=self.api_key,
                http_options={"timeout": self.timeout_seconds * 1000},
            )
            response = client.models.generate_content(
                model=self.model,
                contents=[
                    VISION_PROMPT,
                    *(types.Part.from_bytes(data=image, mime_type="image/jpeg") for image in prepared_images),
                ],
                config={
                    "max_output_tokens": MAX_GEMINI_RESPONSE_TOKENS,
                    "temperature": 0,
                    # Gemini 3.5 Flash otherwise spends the bounded output
                    # allowance on hidden reasoning before it emits the JSON.
                    "thinking_config": {"thinking_budget": 0},
                },
            )
            usage = _response_usage(response)
            payload = getattr(response, "parsed", None)
            if payload is None:
                text = getattr(response, "text", "")
                payload = json.loads(text)
            result = _result_from_payload(payload)
            return ProductVisionResult(
                same_product=result.same_product,
                suggested_name_th=result.suggested_name_th,
                brand=result.brand,
                product_type=result.product_type,
                variant=result.variant,
                size=result.size,
                confidence=result.confidence,
                warnings=result.warnings,
                usage=usage,
            )
        except VisionError as exc:
            if usage is not None and exc.usage is None:
                raise VisionError(str(exc), usage=usage) from exc
            raise
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise VisionError("Gemini did not return valid structured JSON.", usage=usage) from exc
        except Exception as exc:
            if _is_retryable_exception(exc):
                raise VisionRetryableError("Gemini was temporarily unavailable.") from exc
            raise VisionError("Gemini could not analyze the product safely.") from exc
        finally:
            # Bytes are short-lived and never persisted; clear references promptly.
            prepared_images.clear()
