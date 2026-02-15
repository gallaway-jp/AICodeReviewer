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
    logger.debug("shutil.which('%s') returned: %s", cmd, path)
    logger.debug("Current PATH: %s", os.environ.get("PATH", "")[:200])
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


# Module-level cache for discovered Copilot models
_copilot_models_cache: List[str] = []


def get_copilot_models(copilot_path: str = "") -> List[str]:
    """Return cached list of Copilot models, discovering them lazily if needed.

    Args:
        copilot_path: Path to the copilot executable. If empty, uses config.
    """
    global _copilot_models_cache
    if not _copilot_models_cache:
        # Lazy discovery if cache is empty
        if not copilot_path:
            copilot_path = config.get("copilot", "copilot_path", "copilot")
        _discover_copilot_models(copilot_path)
    return list(_copilot_models_cache)


def _discover_copilot_models(copilot_path: str = "copilot") -> List[str]:
    """Discover available models by parsing ``copilot --help`` output.

    Looks for the ``--model`` option's choices list in the help text.
    Results are cached in ``_copilot_models_cache``.
    """
    global _copilot_models_cache
    import re

    rc, stdout, stderr = _run_quiet([copilot_path, "--help"], timeout=5)
    combined = (stdout or "") + "\n" + (stderr or "")

    models: List[str] = []
    # The help text shows: --model  ... {model1,model2,...}
    # Look for a brace-enclosed, comma-separated list near "--model"
    m = re.search(r"--model\b[^{]*\{([^}]+)\}", combined)
    if m:
        raw = m.group(1)
        models = [s.strip() for s in raw.split(",") if s.strip()]

    if models:
        _copilot_models_cache = sorted(models)
        logger.debug("Discovered %d Copilot models: %s",
                     len(models), _copilot_models_cache)
    else:
        logger.debug("Could not parse model list from copilot --help")

    return list(_copilot_models_cache)


# ── AWS Bedrock model discovery ────────────────────────────────────────────

_bedrock_models_cache: List[str] = []


def get_bedrock_models(region: str = "") -> List[str]:
    """Return cached list of Bedrock models, discovering them lazily if needed.

    Args:
        region: AWS region. If empty, uses config.
    """
    global _bedrock_models_cache
    if not _bedrock_models_cache:
        if not region:
            region = config.get("aws", "region", "us-east-1")
        _discover_bedrock_models(region)
    return list(_bedrock_models_cache)


def _discover_bedrock_models(region: str = "us-east-1") -> List[str]:
    """Discover available Bedrock models using AWS CLI.

    Results are cached in ``_bedrock_models_cache``.
    """
    global _bedrock_models_cache
    import json as _json

    rc, stdout, stderr = _run_quiet(
        ["aws", "bedrock", "list-foundation-models",
         "--region", region,
         "--query", "modelSummaries[?modelLifecycleStatus=='ACTIVE'].modelId",
         "--output", "json"],
        timeout=15,
    )

    models: List[str] = []
    if rc == 0 and stdout:
        try:
            model_ids = _json.loads(stdout)
            if isinstance(model_ids, list):
                models = sorted([m for m in model_ids if isinstance(m, str)])
        except Exception as e:
            logger.debug("Failed to parse Bedrock model list: %s", e)

    if models:
        _bedrock_models_cache = models
        logger.debug("Discovered %d Bedrock models", len(models))
    else:
        logger.debug("Could not discover Bedrock models")

    return list(_bedrock_models_cache)


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
    """Check GitHub Copilot CLI (standalone) prerequisites."""
    import time
    start_time = time.time()
    logger.debug("Starting Copilot health check...")
    
    report = HealthReport(backend="copilot")
    checks = []

    copilot_path = config.get("copilot", "copilot_path", "copilot").strip()

    # 1. Copilot CLI installed & verified as genuine standalone CLI
    logger.debug("Checking if '%s' exists in PATH...", copilot_path)
    cli_check = _check_command_exists(copilot_path, "GitHub Copilot CLI")
    logger.debug("Command exists check took %.3f seconds", time.time() - start_time)
    if not cli_check.passed:
        cli_check.fix_hint = t("health.hint_copilot_install")
        logger.debug("Copilot CLI not found in PATH")
    else:
        # Verify it is the real standalone CLI, not a leftover .BAT
        # from the retired gh-copilot extension
        # Use short timeout (3s) for version check to fail fast
        found_path = shutil.which(copilot_path) or copilot_path
        logger.debug("Found copilot at '%s', verifying with --version...", found_path)
        verify_start = time.time()
        rc, stdout, stderr = _run_quiet([found_path, "--version"], timeout=3)
        verify_time = time.time() - verify_start
        logger.debug("Version check took %.3f seconds (rc=%d)", verify_time, rc)
        
        version_out = stdout.strip() or stderr.strip()
        if rc == 0 and version_out:
            cli_check = CheckResult(
                name="GitHub Copilot CLI",
                passed=True,
                detail=t("health.copilot_verified",
                         version=version_out.splitlines()[0]),
            )
        elif rc == -2:  # Timeout
            cli_check = CheckResult(
                name="GitHub Copilot CLI",
                passed=False,
                detail=t("health.copilot_timeout", path=found_path),
                fix_hint=t("health.hint_copilot_install"),
            )
        else:
            cli_check = CheckResult(
                name="GitHub Copilot CLI",
                passed=False,
                detail=t("health.copilot_not_genuine", path=found_path),
                fix_hint=t("health.hint_copilot_install"),
            )
    checks.append(cli_check)

    if cli_check.passed:
        # 2. Authentication – check config directory or env-var tokens
        home = os.path.expanduser("~")
        copilot_config_dirs = [
            os.path.join(home, ".copilot"),
            os.path.join(home, ".config", "github-copilot"),
        ]
        has_config = any(os.path.isdir(d) for d in copilot_config_dirs)
        has_token = bool(os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
        auth_ok = has_config or has_token
        checks.append(CheckResult(
            name=t("health.copilot_auth"),
            passed=auth_ok,
            detail=(t("health.copilot_auth_ok") if auth_ok
                    else t("health.copilot_auth_fail")),
            fix_hint="" if auth_ok else t("health.hint_copilot_auth"),
        ))

        # 3. Model availability
        model = config.get("copilot", "model", "auto").strip()
        if not model or model.lower() == "auto":
            # Discover models even when auto, so the GUI combobox can use them
            _discover_copilot_models(copilot_path)
            checks.append(CheckResult(
                name=t("health.copilot_model"),
                passed=True,
                detail=t("health.copilot_model_auto"),
            ))
        else:
            # Dynamically discover valid models from copilot --help
            discovered = _discover_copilot_models(copilot_path)
            if discovered:
                model_ok = model in discovered
            else:
                # If we couldn't discover models, accept anything
                model_ok = True
            checks.append(CheckResult(
                name=t("health.copilot_model"),
                passed=model_ok,
                detail=(t("health.copilot_model_ok", model=model) if model_ok
                        else t("health.copilot_model_fail", model=model)),
                fix_hint="" if model_ok else t("health.hint_copilot_model"),
            ))

    report.checks = checks
    report.ready = all(c.passed for c in checks)
    report.summary = (t("health.ready") if report.ready
                      else t("health.not_ready", count=len(report.failed_checks)))
    
    total_time = time.time() - start_time
    logger.debug("Copilot health check completed in %.3f seconds (ready=%s)", 
                 total_time, report.ready)
    return report


# ── Local LLM model discovery ──────────────────────────────────────────────

_local_models_cache: List[str] = []


def get_local_models(api_url: str = "") -> List[str]:
    """Return cached list of local LLM models, discovering them lazily if needed.

    Args:
        api_url: The local LLM API URL. If empty, uses config.
    """
    global _local_models_cache
    if not _local_models_cache:
        if not api_url:
            api_url = config.get("local_llm", "api_url", "http://localhost:1234/v1")
        _discover_local_models(api_url)
    return list(_local_models_cache)


def _discover_local_models(api_url: str = "http://localhost:1234/v1") -> List[str]:
    """Discover available local LLM models by querying the API.

    Expects OpenAI-compatible /v1/models endpoint.
    Results are cached in ``_local_models_cache``.
    """
    global _local_models_cache
    import json as _json
    import urllib.request
    import urllib.error

    models: List[str] = []
    try:
        # Query the models endpoint (OpenAI-compatible)
        models_url = api_url.rstrip("/") + "/models"
        with urllib.request.urlopen(models_url, timeout=5) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and "data" in data:
                # Extract model IDs from the response
                model_list = data["data"]
                if isinstance(model_list, list):
                    models = sorted([m.get("id", m) if isinstance(m, dict) else m 
                                    for m in model_list if m])
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError, _json.JSONDecodeError) as e:
        logger.debug("Failed to discover local LLM models: %s", e)

    if models:
        _local_models_cache = models
        logger.debug("Discovered %d local LLM models", len(models))
    else:
        logger.debug("Could not discover local LLM models")

    return list(_local_models_cache)


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

def _run_connection_test(backend_type: str) -> CheckResult:
    """Create a backend instance and test actual connectivity."""
    from aicodereviewer.backends import create_backend
    try:
        client = create_backend(backend_type)
        ok = client.validate_connection()
        if ok:
            return CheckResult(
                name=t("health.conn_test"),
                passed=True,
                detail=t("health.conn_test_ok"),
            )
        else:
            return CheckResult(
                name=t("health.conn_test"),
                passed=False,
                detail=t("health.conn_test_fail"),
                fix_hint=t("health.hint_conn_test"),
            )
    except Exception as exc:
        return CheckResult(
            name=t("health.conn_test"),
            passed=False,
            detail=t("health.conn_test_error", error=str(exc)[:200]),
            fix_hint=t("health.hint_conn_test"),
        )


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
    report = fn()

    # If all prerequisite checks passed, run a live connection test
    if report.ready:
        conn_check = _run_connection_test(backend_type)
        report.checks.append(conn_check)
        report.ready = all(c.passed for c in report.checks)
        report.summary = (t("health.ready") if report.ready
                          else t("health.not_ready",
                                 count=len(report.failed_checks)))

    return report
