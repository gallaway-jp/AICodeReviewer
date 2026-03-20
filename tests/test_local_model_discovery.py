import json
from unittest.mock import patch


class _Resp:
    def __init__(self, payload=None):
        self.payload = payload or {}

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_get_local_models_does_not_auto_load_when_no_models_are_listed():
    from aicodereviewer.backends import models as m

    m._local_models_cache.clear()
    m._local_models_cache_key = ("", "")
    m._auto_loaded_models.clear()

    with patch("urllib.request.urlopen", return_value=_Resp({"models": []})) as mock_open, \
         patch.object(m, "_auto_load_model") as mock_auto_load:
        result = m.get_local_models("http://localhost:11434", "ollama")

    assert result == []
    mock_auto_load.assert_not_called()
    assert m._auto_loaded_models == {}
    assert mock_open.call_count == 1


def test_get_local_models_returns_listed_ollama_models_without_side_effects():
    from aicodereviewer.backends import models as m

    m._local_models_cache.clear()
    m._local_models_cache_key = ("", "")
    m._auto_loaded_models.clear()

    with patch("urllib.request.urlopen", return_value=_Resp({"models": [{"name": "llama3"}]})) as mock_open, \
         patch.object(m, "_auto_load_model") as mock_auto_load:
        result = m.get_local_models("http://localhost:11434", "ollama")

    assert result == ["llama3"]
    mock_auto_load.assert_not_called()
    assert m._auto_loaded_models == {}
    assert mock_open.call_count == 1