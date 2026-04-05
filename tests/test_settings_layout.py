from aicodereviewer.gui.settings_layout import SettingsLayoutHelper


def test_settings_layout_state_for_narrow_width() -> None:
    state = SettingsLayoutHelper.build_state(860.0)

    assert state.wraplength == 740
    assert state.local_http_status_wraplength == 580
    assert state.local_http_copy_button_width == 80
    assert state.local_http_docs_height == 164
    assert state.addon_summary_height == 136
    assert state.addon_diagnostics_height == 146
    assert state.output_format_columns == 1
    assert state.stack_settings_buttons is True
    assert state.refresh_addons_sticky == "ew"
    assert state.contribution_wraplength == 680


def test_settings_layout_state_for_wide_width() -> None:
    state = SettingsLayoutHelper.build_state(1320.0)

    assert state.wraplength == 1200
    assert state.local_http_status_wraplength == 1040
    assert state.local_http_copy_button_width == 96
    assert state.local_http_docs_height == 126
    assert state.addon_summary_height == 110
    assert state.addon_diagnostics_height == 120
    assert state.output_format_columns == 3
    assert state.stack_settings_buttons is False
    assert state.refresh_addons_sticky == "w"
    assert state.contribution_wraplength == 1140