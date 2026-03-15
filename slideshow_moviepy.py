"""Entrypoint render slideshow viral A/B/C."""

from slideshow_engine.pipeline import render_all_variants


def main() -> None:
    try:
        outputs = render_all_variants()
        print("Da render thanh cong cac file:")
        for item in outputs:
            print(f"- {item}")
    except Exception as exc:
        print("Render that bai. Chi tiet loi:")
        print(exc)
        raise


if __name__ == "__main__":
    main()
