from __future__ import annotations

from typing import Any, TypeVar

from .app_bootstrap import AppBootstrapHelper
from .app_local_http import AppLocalHttpHelper
from .app_lifecycle import AppLifecycleHelper
from .app_runtime import AppRuntimeHelper
from .app_shell_layout import AppShellLayoutHelper
from .app_surfaces import AppSurfaceHelper

HelperT = TypeVar("HelperT")


class AppCompositionHelper:
    def __init__(self, host: Any) -> None:
        self.host = host

    def bootstrap(self) -> AppBootstrapHelper:
        return self._resolve("_app_bootstrap_delegate", AppBootstrapHelper)

    def lifecycle(self) -> AppLifecycleHelper:
        return self._resolve("_app_lifecycle_delegate", AppLifecycleHelper)

    def runtime(self) -> AppRuntimeHelper:
        return self._resolve("_app_runtime_delegate", AppRuntimeHelper)

    def surfaces(self) -> AppSurfaceHelper:
        return self._resolve("_app_surface_delegate", AppSurfaceHelper)

    def shell_layout(self) -> AppShellLayoutHelper:
        return self._resolve("_app_shell_layout_delegate", AppShellLayoutHelper)

    def local_http(self) -> AppLocalHttpHelper:
        return self._resolve("_app_local_http_delegate", AppLocalHttpHelper)

    def _resolve(self, attr_name: str, helper_type: type[HelperT]) -> HelperT:
        helper = getattr(self.host, attr_name, None)
        if helper is None:
            helper = helper_type(self.host)
            setattr(self.host, attr_name, helper)
        return helper