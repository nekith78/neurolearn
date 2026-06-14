"""HTML + PDF renderer for report outlines.

Pipeline at render time:
  Outline → resolve image_refs against batch_dir → downscale via Pillow →
  embed as data: URIs → Jinja2 fill → WeasyPrint emit PDF.

WeasyPrint is part of the `report` optional extra. Tests for PDF
generation skip if it's missing; HTML rendering only needs Jinja2.
"""
from __future__ import annotations

import base64
import io
import mimetypes
import re
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files as _resource_files
from pathlib import Path
from typing import Any

from skills.neurolearn.report.outliner import Outline


# Image pipeline defaults — tunable from CLI.
_DEFAULT_MAX_WIDTH = 1000
_DEFAULT_MAX_IMAGES = 50

# Cap stored data URI sizes — defensive; downscale should already
# keep them small, but a single bloated source frame shouldn't
# inflate the HTML/PDF beyond control.
_MAX_DATA_URI_BYTES = 1_500_000   # 1.5 MB per image after downscale


@dataclass
class _PreparedImage:
    """One image ready to drop into the template — already a data: URI."""
    src: str
    caption: str = ""


# ---------------------------------------------------------------------------
# Image processing — Pillow-driven
# ---------------------------------------------------------------------------


def downscale_image(
    path: Path | str, *, max_width: int = _DEFAULT_MAX_WIDTH,
) -> bytes | None:
    """Return downscaled JPEG bytes, or None if the source can't be read.

    Already-small images pass through without upscaling. We always
    re-encode as JPEG for predictable size; alpha channels are flattened
    to white. Returning None on missing path lets the caller cleanly
    skip that image rather than blowing up the whole render.
    """
    src = Path(path)
    if not src.exists():
        return None
    try:
        from PIL import Image
    except ImportError:
        # Pillow is part of the report extra — if it's missing we
        # silently degrade (image won't appear).
        return None

    # Decompression-bomb defense: reject sources that decode to more
    # than ~25 megapixels before they exhaust memory. Stock Pillow caps
    # at ~89 MP; ours is tighter because keyframes are screen-sized.
    Image.MAX_IMAGE_PIXELS = 25_000_000

    try:
        with Image.open(src) as img:
            img.load()
            if img.mode in ("RGBA", "LA", "P"):
                # Flatten transparency on white background.
                bg = Image.new("RGB", img.size, (255, 255, 255))
                rgba = img.convert("RGBA")
                bg.paste(rgba, mask=rgba.split()[-1])
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")

            if img.width > max_width:
                ratio = max_width / float(img.width)
                new_size = (max_width, int(img.height * ratio))
                img = img.resize(new_size, Image.LANCZOS)

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=82, optimize=True)
            return buf.getvalue()
    except Exception:
        # Corrupt image / unsupported format → skip, don't crash.
        return None


def _to_data_uri(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    """Embed bytes as a base64 data: URI for the HTML <img src>."""
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------


def _resolve_image_path(batch_dir: Path, ref: str) -> Path | None:
    """Resolve an image_ref (path string from outline) to a real path
    INSIDE batch_dir, or None if it escapes the directory.

    image_refs are LLM-controlled (the outliner pulls them from the
    parsed model response). An adversarial / hallucinated LLM could
    emit absolute paths ("/etc/passwd") or relative traversals
    ("../../etc/shadow") — we never honor either. The resolved path
    must stay inside `batch_dir` or we return None and the caller
    silently skips the image.

    Tries, in order:
      1. batch_dir / ref
      2. batch_dir / "frames" / basename(ref)
    """
    batch_root = batch_dir.resolve()

    def _safe_under_batch(candidate: Path) -> Path | None:
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError):
            return None
        # Strict containment: resolved must be batch_root or strictly
        # below it. Using is_relative_to (3.9+) keeps the intent obvious.
        try:
            resolved.relative_to(batch_root)
        except ValueError:
            return None
        return resolved if resolved.exists() else None

    safe = _safe_under_batch(batch_dir / ref)
    if safe is not None:
        return safe
    safe = _safe_under_batch(batch_dir / "frames" / Path(ref).name)
    if safe is not None:
        return safe
    return None


def _prepare_section_images(
    outline: Outline,
    batch_dir: Path,
    *,
    max_images: int,
    max_width: int,
    include_screenshots: bool,
) -> dict[int, list[_PreparedImage]]:
    """Walk sections in order, resolve+downscale image refs up to the
    global `max_images` budget. Returns a dict {section_index: [imgs]}."""
    if not include_screenshots or max_images <= 0:
        return {}

    out: dict[int, list[_PreparedImage]] = {}
    remaining = max_images
    for idx, section in enumerate(outline.sections):
        if remaining <= 0:
            break
        section_imgs: list[_PreparedImage] = []
        for ref in section.image_refs:
            if remaining <= 0:
                break
            path = _resolve_image_path(batch_dir, ref)
            if path is None:
                continue
            jpg_bytes = downscale_image(path, max_width=max_width)
            if jpg_bytes is None:
                continue
            if len(jpg_bytes) > _MAX_DATA_URI_BYTES:
                # Pathologically large frame — re-downscale at lower width.
                jpg_bytes = downscale_image(path, max_width=600) or jpg_bytes
            section_imgs.append(_PreparedImage(
                src=_to_data_uri(jpg_bytes),
                caption=_first_timestamp(section),
            ))
            remaining -= 1
        if section_imgs:
            out[idx] = section_imgs
    return out


def _first_timestamp(section) -> str:
    return section.timestamps[0] if section.timestamps else ""


def _load_template_text(filename: str) -> str:
    """Read a template/CSS file shipped under report.data.templates."""
    return (
        _resource_files("skills.neurolearn.report.data.templates")
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )


def _jinja_env():
    """Build a small Jinja2 environment with HTML autoescape."""
    import jinja2
    env = jinja2.Environment(
        autoescape=jinja2.select_autoescape(["html", "htm"]),
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env


def render_html(
    outline: Outline,
    *,
    batch_dir: Path | str,
    lang: str = "en",
    include_screenshots: bool = True,
    max_images: int = _DEFAULT_MAX_IMAGES,
    image_max_width: int = _DEFAULT_MAX_WIDTH,
    meta: dict[str, Any] | None = None,
    version: str = "",
) -> str:
    """Render the outline to a self-contained HTML string.

    Images are embedded as base64 data: URIs so the HTML stands alone
    (important for `--keep-html` debugging — user can open the file
    directly without dragging the batch_dir along).
    """
    batch_dir = Path(batch_dir)

    section_images = _prepare_section_images(
        outline,
        batch_dir,
        max_images=max_images,
        max_width=image_max_width,
        include_screenshots=include_screenshots,
    )

    # Inject images onto a lightweight view-model — the template
    # consumes `s.images` (list of {src, caption}) without mutating
    # the underlying Outline dataclass.
    class _SectionView:
        def __init__(self, s, images):
            self.title = s.title
            self.summary = s.summary
            self.key_points = s.key_points
            self.timestamps = s.timestamps
            self.image_refs = s.image_refs
            self.images = images

    class _OutlineView:
        def __init__(self, o, images_by_idx):
            self.title = o.title
            self.summary = o.summary
            self.sections = [
                _SectionView(s, images_by_idx.get(i, []))
                for i, s in enumerate(o.sections)
            ]

    env = _jinja_env()
    tmpl_text = _load_template_text("base.html")
    css_text = _load_template_text("base.css")
    template = env.from_string(tmpl_text)

    html = template.render(
        outline=_OutlineView(outline, section_images),
        css_inline=css_text,
        lang=lang or "en",
        meta=meta or {},
        version=version,
    )
    return html


# ---------------------------------------------------------------------------
# PDF rendering — WeasyPrint
# ---------------------------------------------------------------------------


def render_pdf(
    outline: Outline,
    *,
    output_path: Path | str,
    batch_dir: Path | str,
    lang: str = "en",
    include_screenshots: bool = True,
    max_images: int = _DEFAULT_MAX_IMAGES,
    image_max_width: int = _DEFAULT_MAX_WIDTH,
    meta: dict[str, Any] | None = None,
    version: str = "",
    keep_html: bool = False,
) -> Path:
    """Render Outline → PDF at output_path. Returns the path on success.

    keep_html=True also writes the intermediate HTML alongside the PDF
    (same stem, .html extension) for debugging.
    """
    from skills.neurolearn.report._macos import (
        prime_native_libs_for_weasyprint,
    )
    prime_native_libs_for_weasyprint()
    try:
        import weasyprint
    except ImportError as e:
        raise RuntimeError(
            "WeasyPrint is required for PDF output. "
            "Install with: uv sync --extra report"
        ) from e
    except OSError as e:
        raise RuntimeError(
            "WeasyPrint failed to load native libraries (pango/cairo/gobject). "
            "On macOS install via:  brew install pango cairo gdk-pixbuf libffi "
            "  (already installed → try restarting the shell so brew libs are "
            "on DYLD_FALLBACK_LIBRARY_PATH). "
            f"Original error: {e}"
        ) from e

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    html = render_html(
        outline,
        batch_dir=batch_dir,
        lang=lang,
        include_screenshots=include_screenshots,
        max_images=max_images,
        image_max_width=image_max_width,
        meta=meta,
        version=version,
    )

    if keep_html:
        html_path = output_path.with_suffix(".html")
        html_path.write_text(html, encoding="utf-8")

    # base_url=batch_dir lets WeasyPrint resolve any non-data refs
    # (we use data URIs by default, but be defensive).
    weasyprint.HTML(
        string=html, base_url=str(Path(batch_dir))
    ).write_pdf(target=str(output_path))

    return output_path


# ---------------------------------------------------------------------------
# Markdown → PDF — for the orchestrated visual-report flow
# ---------------------------------------------------------------------------


_IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")', re.I)


def render_markdown_pdf(
    markdown_text: str,
    *,
    batch_dir: Path | str,
    output_path: Path | str,
    max_images: int = _DEFAULT_MAX_IMAGES,
    image_max_width: int = _DEFAULT_MAX_WIDTH,
    keep_html: bool = False,
) -> Path:
    """Render an already-authored Markdown report (e.g. one Claude or the
    outliner produced) to PDF, embedding any referenced keyframes.

    Image references use normal Markdown image syntax pointing at frames
    inside the batch, e.g. `![6:00 — expedition cheatsheet](frames/<id>_00360.jpg)`.
    Each `src` is resolved through the same path-traversal-safe + downscale
    pipeline as the outline renderer, then inlined as a data: URI. Unknown
    or out-of-batch paths are dropped (the image is removed) rather than
    leaving a broken link. Caps embedded images at `max_images`.
    """
    from skills.neurolearn.report._macos import prime_native_libs_for_weasyprint
    prime_native_libs_for_weasyprint()
    try:
        import weasyprint
    except ImportError as e:
        raise RuntimeError(
            "WeasyPrint is required for PDF output. Install: uv sync --extra report"
        ) from e
    import markdown as _md

    batch_dir = Path(batch_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    body = _md.markdown(
        markdown_text, extensions=["extra", "sane_lists", "toc"],
    )

    # Inline + downscale referenced frames; drop anything unresolved.
    remaining = max_images if max_images > 0 else 0

    def _swap(m):
        nonlocal remaining
        prefix, src, suffix = m.group(1), m.group(2), m.group(3)
        if src.startswith("data:"):
            return m.group(0)
        if remaining <= 0:
            return prefix + "" + suffix  # over budget — empty src, tag stays valid
        path = _resolve_image_path(batch_dir, src)
        if path is None:
            return prefix + "" + suffix
        jpg = downscale_image(path, max_width=image_max_width)
        if jpg is None:
            return prefix + "" + suffix
        if len(jpg) > _MAX_DATA_URI_BYTES:
            jpg = downscale_image(path, max_width=600) or jpg
        remaining -= 1
        return prefix + _to_data_uri(jpg) + suffix

    body = _IMG_SRC_RE.sub(_swap, body)

    css = _load_template_text("base.css")
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{css}</style></head><body class='report'>{body}</body></html>"
    )
    if keep_html:
        output_path.with_suffix(".html").write_text(html, encoding="utf-8")

    weasyprint.HTML(string=html, base_url=str(batch_dir)).write_pdf(
        target=str(output_path)
    )
    return output_path
