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

    pip install github-copilot-sdk>=0.2.1

.. note::
    The ``github-copilot-sdk`` is currently in **Technical Preview** and
    may introduce breaking changes in future releases (pinned to >=0.2.1
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
from aicodereviewer.tool_access import (
    ToolAccessAudit,
    ToolAccessAuditEntry,
    ToolReviewContext,
    extract_tool_path,
    normalize_relative_path,
    path_matches_globs,
    summarize_tool_payload,
)

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
        self.backend_name = "copilot"
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
        self._tool_access_lock = threading.Lock()
        self._tool_access_audit: ToolAccessAudit | None = None
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
        tool_context: ToolReviewContext | None = None,
    ) -> str:
        system_prompt = self._build_system_prompt(
            review_type, lang, self._project_context, self._detected_frameworks,
        )
        user_message = (
            code_content
            if tool_context is not None
            else self._build_user_message(code_content, review_type, spec_content)
        )
        return self._run_sdk(system_prompt, user_message, tool_context=tool_context)

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

    def get_review_recommendations(
        self,
        recommendation_context: str,
        lang: str = "en",
    ) -> str:
        system_prompt = self._build_recommendation_system_prompt(lang)
        user_message = self._build_recommendation_user_message(recommendation_context)
        return self._run_sdk(system_prompt, user_message)

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

    def validate_connection_diagnostic(self) -> dict[str, str | bool]:
        found = shutil.which(self.copilot_path)
        if not found:
            return {
                "ok": False,
                "category": "tool_compatibility",
                "detail": f"GitHub Copilot CLI ('{self.copilot_path}') was not found in PATH.",
                "fix_hint": "Install the standalone GitHub Copilot CLI and verify the configured executable path.",
                "origin": "connection_test",
            }

        try:
            client = self._submit(self._ensure_client())
            models = self._submit(client.list_models())
            if models is not None:
                return {
                    "ok": True,
                    "category": "none",
                    "detail": "",
                    "fix_hint": "",
                    "origin": "connection_test",
                }
            return {
                "ok": False,
                "category": "auth",
                "detail": "GitHub Copilot CLI is not authenticated.",
                "fix_hint": "Run 'copilot' and use /login, or configure GH_TOKEN / GITHUB_TOKEN.",
                "origin": "connection_test",
            }
        except TimeoutError as exc:
            return {
                "ok": False,
                "category": "timeout",
                "detail": str(exc),
                "fix_hint": "Retry the connection test and verify the Copilot CLI is responsive.",
                "origin": "connection_test",
            }
        except Exception as exc:
            lower_msg = str(exc).lower()
            category = "provider"
            if "auth" in lower_msg or "token" in lower_msg or "login" in lower_msg:
                category = "auth"
            elif "timeout" in lower_msg:
                category = "timeout"
            elif "not found" in lower_msg or "cli" in lower_msg:
                category = "tool_compatibility"
            return {
                "ok": False,
                "category": category,
                "detail": str(exc),
                "fix_hint": "Check Copilot authentication, CLI installation, and model availability.",
                "origin": "connection_test",
            }

    def supports_tool_file_access(self) -> bool:
        return True

    def reset_tool_access_audit(self) -> None:
        with self._tool_access_lock:
            self._tool_access_audit = None

    def current_tool_access_audit(self) -> ToolAccessAudit | None:
        with self._tool_access_lock:
            return self._tool_access_audit

    def consume_tool_access_audit(self) -> ToolAccessAudit | None:
        with self._tool_access_lock:
            audit = self._tool_access_audit
            self._tool_access_audit = None
            return audit

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
                from copilot import CopilotClient, SubprocessConfig  # github-copilot-sdk
                try:
                    from copilot import PermissionHandler  # type: ignore[attr-defined]
                except ImportError:
                    from copilot.session import PermissionHandler  # type: ignore[no-redef]

                client_config = SubprocessConfig(
                    cli_path=self.copilot_path,
                    log_level="warning",
                )
                github_token = (
                    os.environ.get("COPILOT_GITHUB_TOKEN")
                    or os.environ.get("GH_TOKEN")
                    or os.environ.get("GITHUB_TOKEN")
                )
                if github_token:
                    client_config.github_token = github_token

                self._client = CopilotClient(client_config)
                self._permission_handler = PermissionHandler.approve_all
                await self._client.start()
                logger.debug("CopilotClient started (CLI process managed by SDK).")
        return self._client

    def _ensure_tool_access_audit(self) -> ToolAccessAudit:
        with self._tool_access_lock:
            if self._tool_access_audit is None:
                self._tool_access_audit = ToolAccessAudit(
                    backend_name=self.backend_name,
                    model_name=self.model or "auto",
                    enabled=True,
                )
            return self._tool_access_audit

    @staticmethod
    def _tool_access_globs() -> list[str]:
        raw = config.get("tool_file_access", "sensitive_path_globs", "")
        return [item.strip() for item in str(raw).split(",") if item.strip()]

    @staticmethod
    def _tool_access_policy() -> str:
        return str(
            config.get("tool_file_access", "sensitive_path_policy", "deny")
        ).strip().lower() or "deny"

    @staticmethod
    def _is_workspace_list_tool(tool_name: str) -> bool:
        normalized = tool_name.lower().replace(".", "_")
        return normalized in {"list_dir", "list_directory", "ls"} or (
            "list" in normalized and "file" in normalized
        )

    @staticmethod
    def _is_workspace_read_tool(tool_name: str) -> bool:
        normalized = tool_name.lower().replace(".", "_")
        if normalized in {"view", "read", "open_file"}:
            return True
        return "read" in normalized and "file" in normalized

    @staticmethod
    def _is_harmless_meta_tool(tool_name: str) -> bool:
        normalized = tool_name.lower().replace(".", "_")
        return normalized in {"report_intent"}

    def _allow_read_permission(self, request: dict[str, Any], _invocation: dict[str, str]) -> dict[str, Any]:
        kind = str(request.get("kind", "")).strip().lower()
        audit = self._ensure_tool_access_audit()
        if kind == "read":
            audit.add_entry(
                ToolAccessAuditEntry(
                    phase="permission",
                    tool_name=None,
                    decision="allow",
                    decision_reason="approved read permission for workspace tool access",
                    requested_path=None,
                    relative_path=None,
                    args_summary=summarize_tool_payload(request),
                )
            )
            return {"kind": "approved"}
        audit.add_entry(
            ToolAccessAuditEntry(
                phase="permission",
                tool_name=None,
                decision="deny",
                decision_reason=f"denied non-read permission kind '{kind or 'unknown'}'",
                requested_path=None,
                relative_path=None,
                args_summary=summarize_tool_payload(request),
            )
        )
        return {"kind": "denied-no-approval-rule-and-could-not-request-from-user"}

    def _handle_pre_tool_use(self, input_data: dict[str, Any], workspace_root: str) -> dict[str, Any]:
        tool_name = str(input_data.get("toolName", "") or "")
        tool_args = input_data.get("toolArgs")
        requested_path = extract_tool_path(tool_args)
        audit = self._ensure_tool_access_audit()

        if self._is_workspace_list_tool(tool_name):
            audit.add_entry(
                ToolAccessAuditEntry(
                    phase="pre_tool_use",
                    tool_name=tool_name,
                    decision="allow",
                    decision_reason="allowed workspace file listing",
                    requested_path=requested_path,
                    relative_path=None,
                    args_summary=summarize_tool_payload(tool_args),
                )
            )
            return {"permissionDecision": "allow", "permissionDecisionReason": "workspace file listing allowed"}

        if self._is_harmless_meta_tool(tool_name):
            audit.add_entry(
                ToolAccessAuditEntry(
                    phase="pre_tool_use",
                    tool_name=tool_name,
                    decision="allow",
                    decision_reason="allowed harmless meta tool for tool-aware review",
                    requested_path=requested_path,
                    relative_path=None,
                    args_summary=summarize_tool_payload(tool_args),
                )
            )
            return {"permissionDecision": "allow", "permissionDecisionReason": "meta tool allowed"}

        if not self._is_workspace_read_tool(tool_name):
            audit.add_entry(
                ToolAccessAuditEntry(
                    phase="pre_tool_use",
                    tool_name=tool_name,
                    decision="deny",
                    decision_reason="denied unsupported tool for tool-aware review",
                    requested_path=requested_path,
                    relative_path=None,
                    args_summary=summarize_tool_payload(tool_args),
                )
            )
            return {"permissionDecision": "deny", "permissionDecisionReason": "Only workspace read tools are allowed"}

        if not requested_path:
            audit.add_entry(
                ToolAccessAuditEntry(
                    phase="pre_tool_use",
                    tool_name=tool_name,
                    decision="deny",
                    decision_reason="denied file-read tool call without a path argument",
                    requested_path=None,
                    relative_path=None,
                    args_summary=summarize_tool_payload(tool_args),
                )
            )
            return {"permissionDecision": "deny", "permissionDecisionReason": "File-read tools must include a path"}

        resolved_path, relative_path = normalize_relative_path(requested_path, workspace_root)
        if relative_path is None:
            audit.add_entry(
                ToolAccessAuditEntry(
                    phase="pre_tool_use",
                    tool_name=tool_name,
                    decision="deny",
                    decision_reason="denied file access outside the configured workspace root",
                    requested_path=resolved_path,
                    relative_path=None,
                    args_summary=summarize_tool_payload(tool_args),
                )
            )
            return {"permissionDecision": "deny", "permissionDecisionReason": "Requested file is outside the workspace root"}

        sensitive = path_matches_globs(relative_path, self._tool_access_globs())
        if sensitive and self._tool_access_policy() != "allow":
            audit.add_entry(
                ToolAccessAuditEntry(
                    phase="pre_tool_use",
                    tool_name=tool_name,
                    decision="deny",
                    decision_reason="denied sensitive file path by policy",
                    requested_path=resolved_path,
                    relative_path=relative_path,
                    sensitive=True,
                    args_summary=summarize_tool_payload(tool_args),
                )
            )
            return {"permissionDecision": "deny", "permissionDecisionReason": "Sensitive file path denied by policy"}

        audit.add_entry(
            ToolAccessAuditEntry(
                phase="pre_tool_use",
                tool_name=tool_name,
                decision="allow",
                decision_reason="allowed workspace file read",
                requested_path=resolved_path,
                relative_path=relative_path,
                sensitive=sensitive,
                args_summary=summarize_tool_payload(tool_args),
            )
        )
        return {"permissionDecision": "allow", "permissionDecisionReason": "Workspace file read allowed"}

    def _handle_post_tool_use(self, input_data: dict[str, Any], workspace_root: str) -> None:
        tool_name = str(input_data.get("toolName", "") or "")
        tool_args = input_data.get("toolArgs")
        requested_path = extract_tool_path(tool_args)
        resolved_path = None
        relative_path = None
        if requested_path:
            resolved_path, relative_path = normalize_relative_path(requested_path, workspace_root)
        self._ensure_tool_access_audit().add_entry(
            ToolAccessAuditEntry(
                phase="post_tool_use",
                tool_name=tool_name,
                decision=None,
                decision_reason=None,
                requested_path=resolved_path,
                relative_path=relative_path,
                sensitive=bool(relative_path and path_matches_globs(relative_path, self._tool_access_globs())),
                args_summary=summarize_tool_payload(tool_args),
                result_summary=summarize_tool_payload(input_data.get("toolResult")),
            )
        )

    async def _run_sdk_async(
        self,
        system_prompt: str,
        user_message: str,
        *,
        tool_context: ToolReviewContext | None = None,
    ) -> str:
        """Create a session, stream the response, and return the full text.

        A fresh session is created and destroyed for every call so the
        backend remains stateless, mirroring the old subprocess approach.
        """
        # _ensure_client() is always awaited – never submitted to self._loop
        # from another coroutine on that same loop (no deadlock).
        client = await self._ensure_client()

        session_config: dict[str, Any] = {
            "streaming": True,
            "system_message": {"content": system_prompt},
            # Single-shot requests don't need context compaction.
            "infinite_sessions": {"enabled": False},
        }
        if tool_context is not None:
            def _pre_tool_use(input_data: Any, _session: Any) -> Any:
                return self._handle_pre_tool_use(input_data, tool_context.workspace_root)

            def _post_tool_use(input_data: Any, _session: Any) -> None:
                self._handle_post_tool_use(input_data, tool_context.workspace_root)

            session_config["on_permission_request"] = self._allow_read_permission
            session_config["hooks"] = {
                "on_pre_tool_use": _pre_tool_use,
                "on_post_tool_use": _post_tool_use,
            }
            session_config["working_directory"] = tool_context.workspace_root
        else:
            session_config["on_permission_request"] = getattr(self, "_permission_handler", None)
        if self.model and self.model.lower() != "auto":
            session_config["model"] = self.model

        session = await client.create_session(**session_config)
        self._active_session = session

        final_response: str = ""

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

        session.on(on_event)

        try:
            response = await session.send_and_wait(user_message, timeout=self.timeout)
            if response is not None:
                final_response = (getattr(response.data, "content", None) or "").strip()
        except asyncio.TimeoutError:
            return "Error: GitHub Copilot timed out."
        except TimeoutError:
            return "Error: GitHub Copilot timed out."
        except Exception as exc:
            return f"Error: {exc}"
        finally:
            self._active_session = None
            try:
                await session.destroy()
            except Exception:
                pass

        result = final_response
        if tool_context is not None:
            audit = self._ensure_tool_access_audit()
            if audit.file_read_count == 0:
                audit.fallback_reason = "tool-aware review completed without any file-read tool usage"
                return "Error: Tool-aware file access was not used by the selected model."
        return result or "Error: No output from GitHub Copilot."

    def _run_sdk(
        self,
        system_prompt: str,
        user_message: str,
        *,
        tool_context: ToolReviewContext | None = None,
    ) -> str:
        """Synchronous wrapper around :meth:`_run_sdk_async`."""
        try:
            return self._submit(
                self._run_sdk_async(
                    system_prompt,
                    user_message,
                    tool_context=tool_context,
                )
            )
        except (TimeoutError, concurrent.futures.TimeoutError):
            return "Error: GitHub Copilot timed out."
        except Exception as exc:
            logger.error("Copilot backend error: %s", exc)
            return f"Error: {exc}"
