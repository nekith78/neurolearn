from concurrent.futures import ThreadPoolExecutor

import click
from click.testing import CliRunner

from skills.neurolearn.youtube_api import InvalidKey, NotConfigured, QuotaExhausted
from skills.neurolearn.youtube_fallback import fallback_notice_for_run


def test_one_notice_for_all_items_and_workers_per_cli_run():
    @click.command()
    def command():
        notice = fallback_notice_for_run()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(notice.report, [NotConfigured()] * 8))
        fallback_notice_for_run().report(QuotaExhausted())

    for _ in range(2):
        result = CliRunner().invoke(command, catch_exceptions=False)
        assert result.exit_code == 0
        assert result.stderr.count("yt-dlp") == 1
        assert "no key configured" in result.stderr


def test_rejected_key_guidance_appears_once_even_after_another_failure(capsys):
    notice = fallback_notice_for_run()
    notice.report(QuotaExhausted())
    notice.report(InvalidKey("sensitive API response"))
    notice.report(InvalidKey())
    err = capsys.readouterr().err
    assert err.count("yt-dlp") == 1
    assert "quota exhausted" in err
    assert err.count("config set-key youtube") == 1
    assert "sensitive API response" not in err
