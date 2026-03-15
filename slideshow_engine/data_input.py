import json
from pathlib import Path
from typing import Any, Dict, List, TypedDict, cast

from .config import DATA_FILE, IMAGES_DIR, MAX_PRODUCTS, MIN_PRODUCTS

DEFAULT_INTRO_TEXT = "Top 5 san pham noi bat"
DEFAULT_OUTRO_TEXT = "San ngay Flash Sale"


class ProductContent(TypedDict):
    image: str
    text: str
    hook: str


class VideoContent(TypedDict):
    intro_text: str
    outro_text: str
    products: List[ProductContent]


def discover_default_data() -> List[ProductContent]:
    image_files = sorted(
        [
            p
            for p in IMAGES_DIR.iterdir()
            if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        ]
    )
    return [
        {
            "image": p.name,
            "text": f"Top {idx}: San pham noi bat",
            "hook": f"Deal nong Top {idx}!",
        }
        for idx, p in enumerate(image_files[:MAX_PRODUCTS], start=1)
    ]


def _normalize_product(raw_item: Dict[str, Any], index: int) -> ProductContent:
    required_keys = {"image", "text", "hook"}
    missing_keys = required_keys.difference(raw_item.keys())
    if missing_keys:
        missing = ", ".join(sorted(missing_keys))
        raise ValueError(f"Product thu {index} thieu truong: {missing}")

    return ProductContent(
        image=str(raw_item["image"]),
        text=str(raw_item["text"]),
        hook=str(raw_item["hook"]),
    )


def _fallback_content() -> VideoContent:
    return {
        "intro_text": DEFAULT_INTRO_TEXT,
        "outro_text": DEFAULT_OUTRO_TEXT,
        "products": discover_default_data(),
    }


def load_video_content() -> VideoContent:
    """
    Dynamic content is managed in DATA_FILE so user can change text/image mapping
    without touching Python code.
    """
    if not DATA_FILE.exists():
        return _fallback_content()

    with DATA_FILE.open("r", encoding="utf-8") as f:
        content = json.load(f)

    if not isinstance(content, dict):
        raise ValueError("Noi dung DATA_FILE phai la object JSON.")

    products = content.get("products")
    if not isinstance(products, list):
        raise ValueError("DATA_FILE phai co truong 'products' dang list.")

    normalized_products = []
    for idx, product in enumerate(products, start=1):
        if not isinstance(product, dict):
            raise ValueError(f"Product thu {idx} phai la object JSON.")
        normalized_products.append(_normalize_product(cast(Dict[str, Any], product), idx))

    return VideoContent(
        intro_text=str(content.get("intro_text", DEFAULT_INTRO_TEXT)),
        outro_text=str(content.get("outro_text", DEFAULT_OUTRO_TEXT)),
        products=normalized_products,
    )


def resolve_data() -> List[ProductContent]:
    return load_video_content()["products"]


def validate_input_data(
    items: List[ProductContent],
    images_dir: Path = IMAGES_DIR,
) -> None:
    if not (MIN_PRODUCTS <= len(items) <= MAX_PRODUCTS):
        raise ValueError(
            f"Can {MIN_PRODUCTS}-{MAX_PRODUCTS} san pham, hien tai co {len(items)}."
        )

    for idx, item in enumerate(items, start=1):
        if "image" not in item or "text" not in item or "hook" not in item:
            raise ValueError(f"Data thu {idx} thieu key 'image'/'text'/'hook'.")

        image_path = images_dir / item["image"]
        if not image_path.exists():
            raise FileNotFoundError(f"Khong tim thay anh: {image_path}")


def load_from_dict(data: Dict[str, Any]) -> VideoContent:
    """Parse a dict (e.g. from PB job input_json) into VideoContent.

    Accepts 2-10 products.  Same validation as ``load_video_content`` but
    from an in-memory dict rather than a JSON file.
    """
    if not isinstance(data, dict):
        raise ValueError("Input phai la object dict/JSON.")

    products = data.get("products")
    if not isinstance(products, list):
        raise ValueError("Input phai co truong 'products' dang list.")

    normalized: List[ProductContent] = []
    for idx, product in enumerate(products, start=1):
        if not isinstance(product, dict):
            raise ValueError(f"Product thu {idx} phai la object.")
        normalized.append(_normalize_product(cast(Dict[str, Any], product), idx))

    return VideoContent(
        intro_text=str(data.get("intro_text", DEFAULT_INTRO_TEXT)),
        outro_text=str(data.get("outro_text", DEFAULT_OUTRO_TEXT)),
        products=normalized,
    )
