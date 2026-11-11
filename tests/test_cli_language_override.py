"""The explicit source language must reach acquisition, not just Click parsing."""
from types import SimpleNamespace
from unittest.mock import patch

from click.testing import CliRunner
import pytest

from skills.neurolearn.backends.base import BackendError
from skills.neurolearn.config import Config
from skills.neurolearn.transcribe import cli


@pytest.mark.parametrize('arguments,expected', [(['--language', 'en'], 'en'), (['--language', 'auto'], 'auto'), ([], 'ru')])
def test_transcribe_source_language_reaches_pipeline(tmp_path, arguments, expected):
    cfg = Config(language='ru', onboarding_complete=True)
    target = SimpleNamespace(url='https://www.youtube.com/watch?v=abcdefghijk', video_id='abcdefghijk')
    observed = []

    def stop_after_observing_language(target, active_config, **kwargs):
        observed.append(active_config.language)
        raise BackendError('Offline language propagation probe')

    with patch('skills.neurolearn.transcribe._ensure_config_or_skip_wizard'), \
         patch('skills.neurolearn.transcribe.load_config', return_value=cfg), \
         patch('skills.neurolearn.transcribe.resolve', return_value=([target], [])), \
         patch('skills.neurolearn.transcribe.run_pipeline', side_effect=stop_after_observing_language):
        result = CliRunner().invoke(cli, ['transcribe', target.url, '--output-dir', str(tmp_path), *arguments])

    assert observed == [expected], result.output
    assert 'Offline language propagation probe' in result.output
