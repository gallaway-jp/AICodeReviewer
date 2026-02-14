# src/aicodereviewer/backends/health.py
"""
Backend prerequisite detection and health checking.

Provides non-blocking checks that determine whether the required
programs and services are available for each AI backend type,
returning structured diagnostic results with remediation guidance.
"""
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

from aicodereviewer.config import config
from aicodereviewer.i18n import t

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    """Single prerequisite check result."""
    name: str
    passed: bool
    detail: str = ""
    fix_hint: str = ""


@dataclass
class HealthReport:
    """Aggregated health report for a backend."""
    backend: str
    ready: bool = False
    checks: List[CheckResult] = field(default_factory=list)
    summary: str = ""

    @property
    def failed_checks(self) -> List[CheckResult]:
        return [c for c in self.checks if not c.passed]


# ── individual check helpers ───────────────────────────────────────────────

def _check_command_exists(cmd: str, friendly_name: str) -> CheckResult:
    """Check if a CLI command is available on PATH."""
    path = shutil.which(cmd)
    if path:
        return CheckResult(
            name=friendly_name,
            passed=True,
            detail=t("health.found_at", name=friendly_name, path=path),
        )
    return CheckResult(
        name=friendly_name,
        passed=False,
        detail=t("health.not_found", name=friendly_name),
        fix_hint=t(f"health.hint_install_{cmd}", name=friendly_name),
    )


def _run_quiet(cmd: list, timeout: int = 10) -> tuple:
    """Run a command silently, returning (returncode, stdout, stderr)."""
    kwargs = dict(capture_output=True, text=True, timeout=timeout,
                  encoding="utf-8", errors="replace")
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        r = subprocess.run(cmd, **kwargs)
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return -1, "", "Command not found"
    except subprocess.TimeoutExpired:
        return -2, "", "Timeout"
    except Exception as e:
        return -3, "", str(e)


# ── AWS Bedrock health ─────────────────────────────────────────────────────

def check_bedrock() -> HealthReport:
    """Check AWS Bedrock prerequisites."""
    report = HealthReport(backend="bedrock")
    checks = []

    # 1. AWS CLI installed
    aws_check = _check_command_exists("aws", "AWS CLI")
    if not aws_check.passed:
        aws_check.fix_hint = t("health.hint_aws_cli")
    checks.append(aws_check)

    # 2. AWS credentials configured
    if aws_check.passed:
        rc, stdout, stderr = _run_quiet(["aws", "sts", "get-caller-identity"])
        if rc == 0:
            checks.append(CheckResult(
                name=t("health.aws_credentials"),
                passed=True,
                detail=t("health.aws_creds_ok"),
            ))
        else:
            checks.append(CheckResult(
                name=t("health.aws_credentials"),
                passed=False,
                detail=t("health.aws_creds_fail", error=stderr.strip()[:200]),
                fix_hint=t("health.hint_aws_creds"),
            ))

    # 3. Model configured & accessible
    model_id = config.get("model", "model_id", "")
    if model_id:
        # If AWS CLI + credentials passed, verify the model exists and is accessible
        creds_ok = all(c.passed for c in checks)
        if creds_ok:
            try:
                region = config.get("aws", "region", "us-east-1")
                rc, stdout, stderr = _run_quiet(
                    ["aws", "bedrock", "get-foundation-model",
                     "--model-identifier", model_id,
                     "--region", region,
                     "--output", "json"],
                    timeout=15,
                )
                if rc == 0:
                    checks.append(CheckResult(
                        name=t("health.model_config"),
                        passed=True,
                        detail=t("health.model_exists", model=model_id),
                    ))
                else:
                    err_msg = stderr.strip()[:200] if stderr else ""
                    checks.append(CheckResult(
                        name=t("health.model_config"),
                        passed=False,
                        detail=t("health.model_not_exists", model=model_id),
                        fix_hint=t("health.hint_model_access"),
                    ))
            except Exception as exc:
                checks.append(CheckResult(
                    name=t("health.model_config"),
                    passed=False,
                    detail=t("health.model_check_error", error=str(exc)[:200]),
                    fix_hint=t("health.hint_model_access"),
                ))
        else:
            # Credentials not available, just report model is configured
            checks.append(CheckResult(
                name=t("health.model_config"),
                passed=True,
                detail=t("health.model_set", model=model_id),
            ))
    else:
        checks.append(CheckResult(
            name=t("health.model_config"),
            passed=False,
            detail=t("health.model_not_set"),
            fix_hint=t("health.hint_model"),
        ))

    report.checks = checks
    report.ready = all(c.passed for c in checks)
    report.summary = (t("health.ready") if report.ready
                      else t("health.not_ready", count=len(report.failed_checks)))
    return report


# ── Kiro CLI health ────────────────────────────────────────────────────────

def check_kiro() -> HealthReport:
    """Check Kiro CLI (WSL) prerequisites."""
    report = HealthReport(backend="kiro")
    checks = []

    # 1. WSL installed
    wsl_path = shutil.which("wsl")
    if wsl_path:
        rc, stdout, stderr = _run_quiet(["wsl", "--status"])
        wsl_ok = rc == 0
    else:
        wsl_ok = False

    checks.append(CheckResult(
        name="WSL",
        passed=wsl_ok,
        detail=(t("health.wsl_ok") if wsl_ok
                else t("health.wsl_not_found")),
        fix_hint="" if wsl_ok else t("health.hint_wsl"),
    ))

    # 2. WSL distro available
    if wsl_ok:
        distro = config.get("kiro", "wsl_distro", "").strip()
        rc, stdout, _ = _run_quiet(["wsl", "--list", "--quiet"])
        distros_raw = stdout.replace("\x00", "").strip().splitlines()
        distros = [d.strip() for d in distros_raw if d.strip()]
        if distro:
            found = distro in distros
            checks.append(CheckResult(
                name=t("health.wsl_distro"),
                passed=found,
                detail=(t("health.distro_found", distro=distro) if found
                        else t("health.distro_not_found", distro=distro,
                               available=", ".join(distros))),
                fix_hint="" if found else t("health.hint_distro"),
            ))
        elif distros:
            checks.append(CheckResult(
                name=t("health.wsl_distro"),
                passed=True,
                detail=t("health.distro_default", available=", ".join(distros)),
            ))
        else:
            checks.append(CheckResult(
                name=t("health.wsl_distro"),
                passed=False,
                detail=t("health.no_distros"),
                fix_hint=t("health.hint_distro"),
            ))

        # 3. Kiro CLI inside WSL — use login shell so ~/.local/bin is on PATH
        cli_cmd = config.get("kiro", "cli_command", "kiro").strip()
        wsl_kiro_cmd = ["wsl"]
        if distro:
            wsl_kiro_cmd += ["-d", distro]
        # Try the configured command and also kiro-cli as fallback
        candidates = [cli_cmd]
        if cli_cmd != "kiro-cli":
            candidates.append("kiro-cli")
        if cli_cmd != "kiro":
            candidates.append("kiro")

        kiro_found = False
        found_path = ""
        found_cmd = ""
        for candidate in candidates:
            # Use bash -lc so login shell PATH (~/.local/bin) is loaded
            cmd = wsl_kiro_cmd + ["--", "bash", "-lc",
                                  f"command -v {candidate} 2>/dev/null"]
            rc, stdout, _ = _run_quiet(cmd, timeout=15)
            path = stdout.replace("\x00", "").strip()
            if rc == 0 and path:
                kiro_found = True
                found_path = path
                found_cmd = candidate
                break

        checks.append(CheckResult(
            name=t("health.kiro_cli"),
            passed=kiro_found,
            detail=(t("health.kiro_found", path=found_path) if kiro_found
                    else t("health.kiro_not_found")),
            fix_hint="" if kiro_found else t("health.hint_kiro_install"),
        ))

        # 4. Kiro authentication check
        if kiro_found:
            auth_cmd = wsl_kiro_cmd + ["--", "bash", "-lc",
                                       f"{found_cmd} whoami 2>/dev/null || "
                                       f"{found_cmd} status 2>/dev/null"]
            rc, stdout, stderr = _run_quiet(auth_cmd, timeout=15)
            # If the command exits 0 and produces output, consider authenticated
            auth_ok = rc == 0 and bool(stdout.strip())
            checks.append(CheckResult(
                name=t("health.kiro_auth"),
                passed=auth_ok,
                detail=(t("health.kiro_auth_ok") if auth_ok
                        else t("health.kiro_auth_fail")),
                fix_hint="" if auth_ok else t("health.hint_kiro_auth"),
            ))

    report.checks = checks
    report.ready = all(c.passed for c in checks)
    report.summary = (t("health.ready") if report.ready
                      else t("health.not_ready", count=len(report.failed_checks)))
    return report


# ── GitHub Copilot CLI health ──────────────────────────────────────────────

def check_copilot() -> HealthReport:
    """Check GitHub Copilot CLI prerequisites."""
    report = HealthReport(backend="copilot")
    checks = []

    gh_path = config.get("copilot", "gh_path", "gh").strip()

    # 1. gh CLI installed
    gh_check = _check_command_exists(gh_path, "GitHub CLI (gh)")
    if not gh_check.passed:
        gh_check.fix_hint = t("health.hint_gh_install")
    checks.append(gh_check)

    if gh_check.passed:
        # 2. gh authenticated
        rc, stdout, stderr = _run_quiet([gh_path, "auth", "status"])
        auth_ok = rc == 0
        checks.append(CheckResult(
            name=t("health.gh_auth"),
            passed=auth_ok,
            detail=(t("health.gh_auth_ok") if auth_ok
                    else t("health.gh_auth_fail")),
            fix_hint="" if auth_ok else t("health.hint_gh_auth"),
        ))

        # 3. Copilot extension installed
        rc, stdout, _ = _run_quiet([gh_path, "extension", "list"])
        copilot_ext = "copilot" in stdout.lower() if rc == 0 else False
        checks.append(CheckResult(
            name=t("health.copilot_ext"),
            passed=copilot_ext,
            detail=(t("health.copilot_ext_ok") if copilot_ext
                    else t("health.copilot_ext_missing")),
            fix_hint="" if copilot_ext else t("health.hint_copilot_ext"),
        ))

    report.checks = checks
    report.ready = all(c.passed for c in checks)
    report.summary = (t("health.ready") if report.ready
                      else t("health.not_ready", count=len(report.failed_checks)))
    return report


# ── Local LLM health ──────────────────────────────────────────────────────

def check_local_llm() -> HealthReport:
    """Check Local LLM server prerequisites."""
    report = HealthReport(backend="local")
    checks = []

    api_url = config.get("local_llm", "api_url", "http://localhost:1234/v1")
    api_type = config.get("local_llm", "api_type", "openai")
    model = config.get("local_llm", "model", "default")

    # 1. URL configured
    checks.append(CheckResult(
        name=t("health.api_url"),
        passed=bool(api_url),
        detail=(t("health.api_url_set", url=api_url) if api_url
                else t("health.api_url_not_set")),
        fix_hint="" if api_url else t("health.hint_api_url"),
    ))

    # 2. Server reachable
    if api_url:
        import requests
        try:
            # Try the /models endpoint (OpenAI-compatible)
            test_url = api_url.rstrip("/")
            if api_type == "openai":
                test_url = test_url.rstrip("/v1").rstrip("/") + "/v1/models"
            resp = requests.get(test_url, timeout=5)
            reachable = resp.status_code < 500
            checks.append(CheckResult(
                name=t("health.server_reachable"),
                passed=reachable,
                detail=(t("health.server_ok", status=resp.status_code) if reachable
                        else t("health.server_error", status=resp.status_code)),
                fix_hint="" if reachable else t("health.hint_server"),
            ))
        except requests.ConnectionError:
            checks.append(CheckResult(
                name=t("health.server_reachable"),
                passed=False,
                detail=t("health.server_unreachable", url=api_url),
                fix_hint=t("health.hint_server"),
            ))
        except Exception as e:
            checks.append(CheckResult(
                name=t("health.server_reachable"),
                passed=False,
                detail=t("health.server_check_error", error=str(e)),
                fix_hint=t("health.hint_server"),
            ))

    # 3. Model configured
    checks.append(CheckResult(
        name=t("health.model_config"),
        passed=bool(model),
        detail=(t("health.model_set", model=model) if model
                else t("health.model_not_set")),
        fix_hint="" if model else t("health.hint_model"),
    ))

    report.checks = checks
    report.ready = all(c.passed for c in checks)
    report.summary = (t("health.ready") if report.ready
                      else t("health.not_ready", count=len(report.failed_checks)))
    return report


# ── Dispatcher ─────────────────────────────────────────────────────────────

def check_backend(backend_type: Optional[str] = None) -> HealthReport:
    """Run health checks for the given backend type."""
    if backend_type is None:
        backend_type = config.get("backend", "type", "bedrock")
    backend_type = backend_type.strip().lower()

    dispatchers = {
        "bedrock": check_bedrock,
        "kiro": check_kiro,
        "copilot": check_copilot,
        "local": check_local_llm,
    }
    fn = dispatchers.get(backend_type)
    if fn is None:
        return HealthReport(
            backend=backend_type,
            ready=False,
            summary=t("health.unknown_backend", backend=backend_type),
        )
    return fn()
