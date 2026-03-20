from unittest.mock import patch


def test_get_copilot_models_cache_is_keyed_by_cli_path():
    from aicodereviewer.backends import models as m

    m._copilot_models_cache.clear()

    with patch.object(m, "_discover_copilot_models") as mock_discover:
        mock_discover.side_effect = lambda path: m._copilot_models_cache.__setitem__(path, [path]) or [path]

        first = m.get_copilot_models("copilot-a")
        second = m.get_copilot_models("copilot-b")

    assert first == ["copilot-a"]
    assert second == ["copilot-b"]
    assert mock_discover.call_args_list[0].args == ("copilot-a",)
    assert mock_discover.call_args_list[1].args == ("copilot-b",)


def test_get_kiro_models_cache_is_keyed_by_cli_path_and_distro():
    from aicodereviewer.backends import models as m

    m._kiro_models_cache.clear()

    with patch.object(m, "_discover_kiro_models") as mock_discover:
        mock_discover.side_effect = (
            lambda path, distro: m._kiro_models_cache.__setitem__((path, distro), [f"{path}:{distro}"]) or [f"{path}:{distro}"]
        )

        first = m.get_kiro_models("kiro-a", "Ubuntu")
        second = m.get_kiro_models("kiro-b", "Debian")

    assert first == ["kiro-a:Ubuntu"]
    assert second == ["kiro-b:Debian"]
    assert mock_discover.call_args_list[0].args == ("kiro-a", "Ubuntu")
    assert mock_discover.call_args_list[1].args == ("kiro-b", "Debian")


def test_get_bedrock_models_cache_is_keyed_by_region():
    from aicodereviewer.backends import models as m

    m._bedrock_models_cache.clear()

    with patch.object(m, "_discover_bedrock_models") as mock_discover:
        mock_discover.side_effect = lambda region: m._bedrock_models_cache.__setitem__(region, [f"model-{region}"]) or [f"model-{region}"]

        first = m.get_bedrock_models("us-east-1")
        second = m.get_bedrock_models("eu-west-1")

    assert first == ["model-us-east-1"]
    assert second == ["model-eu-west-1"]
    assert mock_discover.call_args_list[0].args == ("us-east-1",)
    assert mock_discover.call_args_list[1].args == ("eu-west-1",)