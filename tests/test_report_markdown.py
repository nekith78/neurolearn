"""Tests for render_markdown_pdf (report --from-markdown path)."""
import pytest


def _weasyprint_ok():
    import skills.neurolearn.report  # primes macOS native libs
    try:
        import weasyprint  # noqa: F401
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _weasyprint_ok(), reason="weasyprint/native libs unavailable")
def test_render_markdown_pdf_embeds_resolves_and_blocks_traversal(tmp_path):
    from PIL import Image
    from skills.neurolearn.report.renderer import render_markdown_pdf

    batch = tmp_path / "b"
    (batch / "frames").mkdir(parents=True)
    Image.new("RGB", (32, 24), (10, 20, 30)).save(batch / "frames" / "f_00010.jpg")

    md = (
        "# Guide\n\n"
        "Real frame:\n\n![ok](frames/f_00010.jpg)\n\n"
        "Missing frame (drop):\n\n![bad](frames/missing.jpg)\n\n"
        "Traversal attempt (block):\n\n![esc](../../../etc/passwd.jpg)\n"
    )
    out = batch / "r.pdf"
    render_markdown_pdf(md, batch_dir=batch, output_path=out, keep_html=True)

    assert out.exists() and out.stat().st_size > 0
    html = (batch / "r.html").read_text(encoding="utf-8")
    assert html.count("data:image/jpeg;base64") == 1   # only the real frame inlined
    assert "missing.jpg" not in html                    # unresolved → dropped
    assert "etc/passwd" not in html                     # traversal blocked


def test_data_uri_only_fetcher_blocks_non_data_urls():
    """The WeasyPrint url_fetcher must reject everything but data: URIs, so
    poisoned report HTML can't read local files via file:// / url() / SVG."""
    from skills.neurolearn.report.renderer import _data_uri_only_fetcher
    for blocked in (
        "file:///etc/passwd",
        "/etc/passwd",
        "../../secret.txt",
        "http://evil.example/x",
        "https://evil.example/x",
    ):
        with pytest.raises(ValueError):
            _data_uri_only_fetcher(blocked)
    # data: URIs are allowed (delegated to WeasyPrint's default fetcher) —
    # the call must not raise. (Return type varies across WeasyPrint
    # versions, so we only assert it succeeds.)
    if _weasyprint_ok():
        _data_uri_only_fetcher("data:text/plain;base64,aGVsbG8=")  # "hello"


@pytest.mark.skipif(not _weasyprint_ok(), reason="weasyprint/native libs unavailable")
def test_render_markdown_pdf_respects_max_images(tmp_path):
    from PIL import Image
    from skills.neurolearn.report.renderer import render_markdown_pdf

    batch = tmp_path / "b"
    (batch / "frames").mkdir(parents=True)
    for i in (10, 20, 30):
        Image.new("RGB", (16, 16), (i, i, i)).save(batch / "frames" / f"f_{i:05d}.jpg")
    md = "\n\n".join(f"![x](frames/f_{i:05d}.jpg)" for i in (10, 20, 30))
    out = batch / "r.pdf"
    render_markdown_pdf(md, batch_dir=batch, output_path=out, max_images=2, keep_html=True)
    html = (batch / "r.html").read_text(encoding="utf-8")
    assert html.count("data:image/jpeg;base64") == 2   # capped at max_images
