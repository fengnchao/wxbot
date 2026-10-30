import pytest

from butler.channels.telegram.relay.settings import Settings, SettingsConflict, load


def test_missing_is_disabled_and_does_not_create_files(tmp_path):
    path = tmp_path / 'relay.toml'
    cfg = load(path)
    assert not cfg.enabled and not cfg.include_images and not cfg.channels
    assert not path.exists()


def test_versioned_atomic_edit_and_selector_preservation(tmp_path):
    settings = Settings(tmp_path / 'relay.toml')
    original = settings.read()
    changed = settings.update({'bot_username': '@relay_bot', 'bot_id': 123,
                               'desktop': {'window_class': 'Qt51514QWindowIcon'},
                               'channels': [{'key': 'news', 'name': 'News', 'username': '@daily_news'}]},
                              original['version'])
    assert changed['version'] != original['version']
    settings.update({'poll_interval': 3}, changed['version'])
    cfg = load(settings.path)
    assert cfg.desktop['window_class'] == 'Qt51514QWindowIcon'
    assert cfg.channels[0].username == 'daily_news'
    with pytest.raises(SettingsConflict):
        settings.update({'enabled': False}, original['version'])


@pytest.mark.parametrize('patch', [
    {'token': 'secret'}, {'enabled': True}, {'poll_interval': float('nan')},
    {'poll_interval': True}, {'include_images': 'yes'}, {'desktop': {'token': 'x'}},
    {'channels': [{'key': 'x', 'name': 'One'}, {'key': 'x', 'name': 'Two'}]},
    {'channels': [{'key': 'x', 'name': 'No stable identity', 'enabled': True}]},
])
def test_invalid_settings_leave_file_untouched(tmp_path, patch):
    settings = Settings(tmp_path / 'relay.toml')
    with pytest.raises(ValueError):
        settings.update(patch, settings.read()['version'])
    assert not settings.path.exists()


def test_enabled_requires_current_bot_target_and_identified_channel(tmp_path):
    settings = Settings(tmp_path / 'relay.toml')
    settings.update({'enabled': True, 'window_title': 'Telegram',
                     'bot_username': 'relay_bot', 'bot_id': 123,
                     'channels': [{'key': 'news', 'name': 'News', 'chat_id': -100123, 'enabled': True}]},
                    settings.read()['version'])
    cfg = load(settings.path)
    assert cfg.enabled and cfg.channels[0].chat_id == -100123


def test_duplicate_username_is_rejected_even_if_one_row_has_numeric_id(tmp_path):
    settings = Settings(tmp_path / 'relay.toml')
    with pytest.raises(ValueError):
        settings.update({'channels': [{'key': 'one', 'name': 'One', 'username': 'Daily_News', 'chat_id': -100123},
                                      {'key': 'two', 'name': 'Two', 'username': 'daily_news'}]},
                        settings.read()['version'])
