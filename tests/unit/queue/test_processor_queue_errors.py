import pytest
import requests

from wxbot.main import build_processor


@pytest.mark.parametrize("backend", ["butler", "hermes", "openai", "ollama"])
def test_main_queue_keeps_transport_error_visible_to_worker(monkeypatch, backend):
    def fail(*args, **kwargs):
        raise requests.Timeout("result unknown")
    monkeypatch.setattr(requests, "post", fail)
    router = build_processor({"bot": {}, "wechat": {"mode": "main"}, "model": {"backend": backend}})
    with pytest.raises(requests.Timeout):
        router.handle("A", "建个提醒")


def test_independent_mode_keeps_existing_error_reply(monkeypatch):
    def fail(*args, **kwargs):
        raise requests.Timeout("result unknown")
    monkeypatch.setattr(requests, "post", fail)
    router = build_processor({"bot": {}, "wechat": {"mode": "independent"}, "model": {"backend": "butler"}})
    assert router.handle("A", "hi") == "抱歉，我这边暂时出了点问题，稍后再试。"
