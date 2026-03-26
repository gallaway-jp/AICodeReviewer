# src/aicodereviewer/backends/copilot.py
"""
GitHub Copilot backend using the official ``github-copilot-sdk``.

Communicates with the Copilot CLI in **server mode** via JSON-RPC instead
of shelling out to ``copilot -p "…"``.  This gives structured model listing,
real-time streaming, and eliminates the old command-line-length workarounds.

Prerequisites:
    1. GitHub Copilot CLI installed and in PATH (e.g.
       ``winget install GitHub.Copilot`` on Windows).
    2. Authenticated (run ``copilot`` then ``/login``, or set
       ``GH_TOKEN`` / ``GITHUB_TOKEN`` / ``COPILOT_GITHUB_TOKEN``).
    3. Active GitHub Copilot subscription.
    4. Python >= 3.11 (SDK requirement).

Install the SDK::

    pip install github-copilot-sdk>=0.1.30

.. note::
    The ``github-copilot-sdk`` is currently in **Technical Preview** and
    may introduce breaking changes in future releases (pinned to >=0.1.30
    in requirements).
"""
import asyncio
import concurrent.futures
import logging
import os
import shutil
import threading
from typing import Any, Callable, Optional

from .base import AIBackend
from .models import _resolve_copilot_exe
from aicodereviewer.config import config

logger = logging.getLogger(__name__)


class CopilotBackend(AIBackend):
    """
    AI backend that uses the official ``github-copilot-sdk`` to communicate
    with the Copilot CLI via JSON-RPC.

    A private daemon thread hosts a persistent :class:`asyncio.AbstractEventLoop`
    so the async SDK can be used behind the synchronous :class:`AIBackend`
    interface without requiring any callers to be async-aware.

    Configuration (``config.ini``):

    .. code-block:: ini

        [backend]
        type = copilot

        [copilot]
        copilot_path = copilot   ; path / name of the copilot CLI executable
        timeout = 300            ; seconds to wait for a complete response
        model = auto             ; model name, or "auto" to let the CLI decide
    """

    def __init__(self, **kwargs: Any) -> None:
        _raw_path: str = config.get("copilot", "copilot_path", "copilot").strip()
        # On Windows, shutil.which("copilot") often resolves to a .bat/.ps1
        # wrapper that the github-copilot-sdk rejects.  Resolve to the real
        # native binary (.exe on Windows) before any SDK calls.
        self.copilot_path: str = _resolve_copilot_exe(_raw_path)
        if self.copilot_path != _raw_path:
            logger.debug(
                "Resolved copilot CLI path: %r → %r", _raw_path, self.copilot_path
            )
        self.timeout: int = int(float(config.get("copilot", "timeout", "300")))
        self.model: str = config.get("copilot", "model", "auto").strip()

        self._stream_callback: Optional[Callable[[str], None]] = None
        self._active_session = None      # set while a request is in-flight
        self._client = None              # lazily created on first use
        # asyncio.Lock for guarding async client creation; instantiated lazily
        # on the background loop to avoid cross-loop contamination.
        self._async_client_lock: Optional[asyncio.Lock] = None

        # Spin up a private daemon event loop so all SDK coroutines run on
        # a dedicated thread; callers remain fully synchronous.
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._loop.run_forever,
            name="CopilotSDK-loop",
            daemon=True,
        )
        self._loop_thread.start()

    # ── AIBackend interface ────────────────────────────────────────────────

    def set_stream_callback(
        self, callback: Optional[Callable[[str], None]]
    ) -> None:
        """Register a callable that receives incremental response tokens.

        The callback is invoked from the SDK loop thread; it must be
        thread-safe (e.g. schedule GUI updates via ``widget.after()``).

        Args:
            callback: Called with each incremental text token, or ``None``
                      to remove a previously registered callback.
        """
        self._stream_callback = callback

    def get_review(
        self,
        code_content: str,
        review_type: str = "best_practices",
        lang: str = "en",
        spec_content: Optional[str] = None,
    ) -> str:
        system_prompt = self._build_system_prompt(
            review_type, lang, self._project_context, self._detected_frameworks,
        )
        user_message = self._build_user_message(code_content, review_type, spec_content)
        return self._run_sdk(system_prompt, user_message)

    def get_fix(
        self,
        code_content: str,
        issue_feedback: str,
        review_type: str = "best_practices",
        lang: str = "en",
    ) -> Optional[str]:
        system_prompt = self._build_system_prompt("fix", lang)
        user_message = self._build_fix_message(code_content, issue_feedback, review_type)
        result = self._run_sdk(system_prompt, user_message)
        if result and not result.startswith("Error:"):
            return result.strip()
        return None

    def validate_connection(self) -> bool:
        """Check Copilot CLI is installed, reachable via the SDK, and authenticated."""
        found = shutil.which(self.copilot_path)
        if not found:
            logger.error(
                "GitHub Copilot CLI ('%s') not found in PATH.", self.copilot_path
            )
            logger.error(
                "Install from "
                "https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli"
            )
            return False

        try:
            # _ensure_client() is an async method – submit it to our loop.
            client = self._submit(self._ensure_client())
            models = self._submit(client.list_models())
            if models is not None:
                logger.debug(
                    "Copilot CLI reachable via SDK. %d model(s) available.",
                    len(models) if models else 0,
                )
                return True
            # list_models returned None – treat as unauthenticated / not ready
            logger.error(
                "GitHub Copilot CLI is not authenticated. "
                "Run 'copilot' and use /login, or set GH_TOKEN / GITHUB_TOKEN."
            )
            return False
        except Exception as exc:
            logger.error("Failed to connect to Copilot CLI via SDK: %s", exc)
            return False

    def cancel(self) -> None:
        """Destroy any in-flight session to interrupt a running review."""
        session = self._active_session
        if session is not None:
            try:
                asyncio.run_coroutine_threadsafe(session.destroy(), self._loop)
                logger.info("Cancelled active Copilot session.")
            except Exception as exc:
                logger.warning("Error cancelling Copilot session: %s", exc)

    def close(self) -> None:
        """Shut down the Copilot client, active session, and private event loop."""
        if getattr(self, "_loop", None) is None:
            return
        if self._loop.is_closed():
            return

        try:
            if self._active_session is not None:
                future = asyncio.run_coroutine_threadsafe(self._active_session.destroy(), self._loop)
                try:
                    future.result(timeout=2)
                except Exception:
                    pass
                self._active_session = None

            if self._client is not None:
                future = asyncio.run_coroutine_threadsafe(self._client.stop(), self._loop)
                try:
                    future.result(timeout=3)
                except Exception:
                    pass
                self._client = None

            async def _shutdown_loop() -> None:
                pending = [
                    task for task in asyncio.all_tasks(self._loop)
                    if task is not asyncio.current_task(self._loop) and not task.done()
                ]
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)

            future = asyncio.run_coroutine_threadsafe(_shutdown_loop(), self._loop)
            try:
                future.result(timeout=3)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop_thread.join(timeout=3)
        finally:
            if not self._loop.is_closed():
                self._loop.close()

    # ── private helpers ────────────────────────────────────────────────────

    def _submit(self, coro: Any) -> Any:
        """Submit *coro* to the background event loop and block until done.

        Raises the coroutine's exception (if any) in the calling thread.
        """
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=self.timeout)

    async def _ensure_client(self) -> Any:
        """Async-safe lazy initializer for :class:`CopilotClient`.

        Always awaited *from within* the background loop, so it can safely
        ``await client.start()`` without deadlocking against :meth:`_submit`.
        """
        # asyncio.Lock must be created inside the loop that will use it.
        if self._async_client_lock is None:
            self._async_client_lock = asyncio.Lock()

        async with self._async_client_lock:
            if self._client is None:
                # Late import keeps the SDK optional until first use.
                from copilot import CopilotClient, PermissionHandler  # github-copilot-sdk

                options: dict = {
                    "cli_path": self.copilot_path,
                    "auto_restart": True,
                    "log_level": "warning",
                }
                github_token = (
                    os.environ.get("COPILOT_GITHUB_TOKEN")
                    or os.environ.get("GH_TOKEN")
                    or os.environ.get("GITHUB_TOKEN")
                )
                if github_token:
                    options["github_token"] = github_token

                self._client = CopilotClient(options)
                self._permission_handler = PermissionHandler.approve_all
                await self._client.start()
                logger.debug("CopilotClient started (CLI process managed by SDK).")
        return self._client

    async def _run_sdk_async(self, system_prompt: str, user_message: str) -> str:
        """Create a session, stream the response, and return the full text.

        A fresh session is created and destroyed for every call so the
        backend remains stateless, mirroring the old subprocess approach.
        """
        # _ensure_client() is always awaited – never submitted to self._loop
        # from another coroutine on that same loop (no deadlock).
        client = await self._ensure_client()

        session_config: dict = {
            "streaming": True,
            "system_message": {"content": system_prompt},
            "on_permission_request": getattr(self, "_permission_handler", None),
            # Single-shot requests don't need context compaction.
            "infinite_sessions": {"enabled": False},
        }
        if self.model and self.model.lower() != "auto":
            session_config["model"] = self.model

        session = await client.create_session(session_config)
        self._active_session = session

        full_text: list[str] = []
        idle_event = asyncio.Event()

        def on_event(event: Any) -> None:
            etype = (
                event.type.value
                if hasattr(event.type, "value")
                else str(event.type)
            )
            if etype == "assistant.message_delta":
                delta = getattr(event.data, "delta_content", None) or ""
                if delta and self._stream_callback:
                    try:
                        self._stream_callback(delta)
                    except Exception:
                        # Never let a GUI callback error break the backend.
                        pass
            elif etype == "assistant.message":
                content = getattr(event.data, "content", None) or ""
                full_text.append(content)
            elif etype == "session.idle":
                idle_event.set()

        session.on(on_event)

        try:
            await session.send({"prompt": user_message})
            await asyncio.wait_for(idle_event.wait(), timeout=self.timeout)
        except asyncio.TimeoutError:
            return "Error: GitHub Copilot timed out."
        finally:
            self._active_session = None
            try:
                await session.destroy()
            except Exception:
                pass

        result = "".join(full_text).strip()
        return result or "Error: No output from GitHub Copilot."

    def _run_sdk(self, system_prompt: str, user_message: str) -> str:
        """Synchronous wrapper around :meth:`_run_sdk_async`."""
        try:
            return self._submit(self._run_sdk_async(system_prompt, user_message))
        except (TimeoutError, concurrent.futures.TimeoutError):
            return "Error: GitHub Copilot timed out."
        except Exception as exc:
            logger.error("Copilot backend error: %s", exc)
            return f"Error: {exc}"
