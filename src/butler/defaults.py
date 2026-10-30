"""Credential-free installation defaults. Each call returns independent objects."""


def butler_defaults():
    return {'agent': {'provider': 'codex', 'data_dir': 'data'},
            'server': {'host': '127.0.0.1', 'port': 8770, 'token': ''},
            'codex': {'model': ''},
            'wxbot': {'url': 'http://127.0.0.1:8765', 'token': ''},
            'dispatch': {'actions_enabled': False},
            'message_routes': []}


def wxbot_defaults():
    return {'model': {'backend': 'butler'},
            'wechat': {'typing': {'mode':'chunked','chunk_size':5,'chunk_interval':.25}},
            'butler': {'url': 'http://127.0.0.1:8770', 'token': '', 'timeout': 660},
            'outbound': {'enabled': True, 'host': '127.0.0.1', 'port': 8765, 'token': ''},
            'queue': {'database': 'cache/wxbot_queue.sqlite3'}}


def log_defaults():
    return {'server': {'host': '127.0.0.1', 'port': 8788},
            'sources': {'home': 'data', 'wxbot_config': 'config.wxbot.toml',
                        'butler_config': 'config.butler.toml', 'groups_file': 'data/cache/butler_groups.json'}}


def telegram_defaults():
    return {'telegram': {'enabled': False, 'api_id': 0, 'api_hash': '', 'sources': ['@zaobaosg'],
                         'session': 'data/telegram/account', 'state_dir': 'data/telegram',
                         'butler_config': 'config.butler.toml', 'scan_interval': 10}}


def telegram_bot_defaults():
    return {'telegram_bot': {'token': '', 'allowed_user_ids': [], 'butler_config': 'config.butler.toml',
                             'state_dir': 'data/telegram-bot', 'proxy_url': ''}}
