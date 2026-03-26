from .feature_flags import ENABLE_BULK_ARCHIVE


class MessageToolbar:
    def build_actions(self) -> list[tuple[str, object]]:
        actions = [("Refresh", self._handle_refresh)]
        if ENABLE_BULK_ARCHIVE:
            actions.append(("Bulk archive", self._handle_bulk_archive))
        return actions

    def _handle_refresh(self) -> None:
        return None

    def _handle_bulk_archive(self) -> None:
        self._open_bulk_archive_dialog()

    def _open_bulk_archive_dialog(self) -> None:
        return None