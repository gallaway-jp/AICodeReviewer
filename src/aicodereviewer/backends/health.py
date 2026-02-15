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
_local_models_cache_key: tuple = ()  # (api_url, api_type) tuple
_auto_loaded_models: dict = {}  # {(api_url, api_type): model_id} - tracks models we auto-loaded


def get_local_models(api_url: str = "", api_type: str = "") -> List[str]:
    """Return cached list of local LLM models, discovering them lazily if needed.

    Args:
        api_url: The local LLM API URL. If empty, uses config.
        api_type: The local LLM API type (lmstudio, ollama, openai, anthropic). If empty, uses config.
    """
    global _local_models_cache, _local_models_cache_key
    
    if not api_url:
        api_url = config.get("local_llm", "api_url", "http://localhost:1234")
    if not api_type:
        api_type = config.get("local_llm", "api_type", "lmstudio")
    
    # Normalize values
    api_url = api_url.rstrip("/")
    api_type = api_type.strip().lower()
    
    # Check if cached data is still valid for the current api_url and api_type
    current_key = (api_url, api_type)
    if _local_models_cache and _local_models_cache_key == current_key:
        return list(_local_models_cache)
    
    # Cache is invalid or empty, discover models for the current settings
    _discover_local_models(api_url, api_type)
    return list(_local_models_cache)


def _discover_local_models(api_url: str = "http://localhost:1234", api_type: str = "lmstudio") -> List[str]:
    """Discover available local LLM models by querying the API.

    Handles different API types:
    - LM Studio: /api/v1/models (auto-loads first model if none loaded)
    - Ollama: /api/tags (auto-loads first model if none pulled)
    - OpenAI-compatible: /v1/models (auto-loads first model if none available)
    - Anthropic-compatible: No public models endpoint
    
    Results are cached in ``_local_models_cache`` with a cache key.
    If no models are loaded, automatically loads the first available model.
    """
    global _local_models_cache, _local_models_cache_key, _auto_loaded_models
    import json as _json
    import urllib.request
    import urllib.error

    models: List[str] = []
    api_url = api_url.rstrip("/")
    api_type = api_type.strip().lower()
    
    # Determine the models endpoint based on API type
    if api_type == "lmstudio":
        models_url = f"{api_url}/api/v1/models"
        try:
            # Query the models endpoint
            with urllib.request.urlopen(models_url, timeout=5) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict) and "models" in data:
                    model_list = data["models"]
                    if isinstance(model_list, list):
                        # Extract loaded model instance IDs
                        for m in model_list:
                            if isinstance(m, dict):
                                loaded_instances = m.get("loaded_instances", [])
                                for instance in loaded_instances:
                                    if isinstance(instance, dict):
                                        instance_id = instance.get("id")
                                        if instance_id:
                                            models.append(instance_id)
                        
                        # If no loaded instances, list available (downloaded) models instead
                        if not models:
                            for m in model_list:
                                if isinstance(m, dict):
                                    model_key = m.get("key")
                                    if model_key:
                                        models.append(model_key)
                        
                        models = sorted(set(models))  # Remove duplicates and sort
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError, _json.JSONDecodeError) as e:
            logger.debug("Failed to discover %s models from %s: %s", api_type, models_url, e)
    
    elif api_type == "ollama":
        models_url = f"{api_url}/api/tags"
        try:
            # Query the models endpoint
            with urllib.request.urlopen(models_url, timeout=5) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict) and "models" in data:
                    model_list = data["models"]
                    if isinstance(model_list, list):
                        models = sorted([m.get("name", m) if isinstance(m, dict) else m 
                                        for m in model_list if m])
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError, _json.JSONDecodeError) as e:
            logger.debug("Failed to discover %s models from %s: %s", api_type, models_url, e)
    
    elif api_type == "openai":
        models_url = f"{api_url}/v1/models"
        try:
            # Query the models endpoint
            with urllib.request.urlopen(models_url, timeout=5) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict) and "data" in data:
                    model_list = data["data"]
                    if isinstance(model_list, list):
                        models = sorted([m.get("id", m) if isinstance(m, dict) else m 
                                        for m in model_list if m])
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError, _json.JSONDecodeError) as e:
            logger.debug("Failed to discover %s models from %s: %s", api_type, models_url, e)
    
    elif api_type == "anthropic":
        # Anthropic doesn't have a public /models endpoint
        logger.debug("Anthropic-compatible endpoints do not expose models list. Using 'default'.")
        _local_models_cache = ["default"]
        _local_models_cache_key = (api_url, api_type)
        return ["default"]
    else:
        logger.debug("Unknown api_type '%s'. Cannot discover models.", api_type)
        return []

    # If no models available, try to auto-load first available model
    if not models:
        loaded_model = _auto_load_model(api_url, api_type)
        if loaded_model:
            models = [loaded_model]
            logger.info("Auto-loaded model '%s' on %s", loaded_model, api_type)

    if models:
        _local_models_cache = models
        logger.debug("Discovered %d %s models", len(models), api_type)
    else:
        logger.debug("Could not discover %s models", api_type)
        _local_models_cache = []
    
    # Update cache key to invalidate if api_url or api_type changes
    _local_models_cache_key = (api_url, api_type)

    return list(_local_models_cache)


def _auto_load_model(api_url: str, api_type: str) -> Optional[str]:
    """Automatically load the first available model if none are currently loaded.
    
    Tracks which models we auto-load so they can be unloaded on exit.
    
    Returns:
        The model ID/name that was loaded, or None if loading failed.
    """
    global _auto_loaded_models
    import json as _json
    import urllib.request
    import urllib.error
    
    model_loaded = None
    cache_key = (api_url, api_type)
    
    try:
        if api_type == "lmstudio":
            # Get list of all available (downloaded) models
            list_url = f"{api_url}/api/v1/models"
            with urllib.request.urlopen(list_url, timeout=5) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict) and "models" in data and data["models"]:
                    # Find first model that isn't loaded yet
                    for model in data["models"]:
                        if isinstance(model, dict):
                            model_key = model.get("key")
                            loaded_instances = model.get("loaded_instances", [])
                            
                            # Skip if already loaded
                            if loaded_instances:
                                continue
                            
                            if model_key:
                                # Load the model
                                load_url = f"{api_url}/api/v1/models/load"
                                load_data = _json.dumps({"model": model_key}).encode("utf-8")
                                req = urllib.request.Request(load_url, data=load_data, 
                                                            headers={"Content-Type": "application/json"})
                                
                                with urllib.request.urlopen(req, timeout=30) as load_resp:
                                    result = _json.loads(load_resp.read().decode("utf-8"))
                                    if result.get("status") == "loaded":
                                        model_loaded = result.get("instance_id") or model_key
                                        _auto_loaded_models[cache_key] = model_loaded
                                        logger.info("Auto-loaded LM Studio model: %s", model_loaded)
                                        break
        
        elif api_type == "ollama":
            # Get list of pulled models
            tags_url = f"{api_url}/api/tags"
            with urllib.request.urlopen(tags_url, timeout=5) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict) and "models" in data and data["models"]:
                    # Get first model
                    first_model = data["models"][0]
                    model_name = first_model.get("name")
                    
                    if model_name:
                        # Load model by sending empty generate request
                        gen_url = f"{api_url}/api/generate"
                        gen_data = _json.dumps({"model": model_name, "prompt": ""}).encode("utf-8")
                        req = urllib.request.Request(gen_url, data=gen_data,
                                                    headers={"Content-Type": "application/json"})
                        
                        with urllib.request.urlopen(req, timeout=30) as gen_resp:
                            # Read response (may be streaming)
                            for line in gen_resp:
                                try:
                                    result = _json.loads(line.decode("utf-8"))
                                    if result.get("done"):
                                        model_loaded = model_name
                                        _auto_loaded_models[cache_key] = model_loaded
                                        logger.info("Auto-loaded Ollama model: %s", model_loaded)
                                        break
                                except _json.JSONDecodeError:
                                    continue
        
        elif api_type == "openai":
            # Get list of available models
            models_url = f"{api_url}/v1/models"
            with urllib.request.urlopen(models_url, timeout=5) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict) and "data" in data and data["data"]:
                    # For OpenAI-compatible APIs, models are typically already loaded
                    # Just return the first model without explicitly loading
                    first_model = data["data"][0]
                    model_loaded = first_model.get("id") or first_model.get("model")
                    logger.debug("OpenAI-compatible model available: %s", model_loaded)
                    # Don't track as auto-loaded since we didn't explicitly load it
    
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError, _json.JSONDecodeError) as e:
        logger.debug("Failed to auto-load model for %s: %s", api_type, e)
    
    return model_loaded


def _cleanup_auto_loaded_models():
    """Unload any models that were auto-loaded by AICodeReviewer.
    
    Called on program exit via atexit handler.
    """
    global _auto_loaded_models
    import json as _json
    import urllib.request
    import urllib.error
    
    for (api_url, api_type), model_id in list(_auto_loaded_models.items()):
        try:
            if api_type == "lmstudio":
                # Unload via LM Studio API
                unload_url = f"{api_url}/api/v1/models/unload"
                unload_data = _json.dumps({"instance_id": model_id}).encode("utf-8")
                req = urllib.request.Request(unload_url, data=unload_data,
                                            headers={"Content-Type": "application/json"})
                
                with urllib.request.urlopen(req, timeout=10) as resp:
                    logger.info("Unloaded auto-loaded LM Studio model: %s", model_id)
            
            elif api_type == "ollama":
                # Unload via Ollama API (keep_alive=0)
                gen_url = f"{api_url}/api/generate"
                gen_data = _json.dumps({
                    "model": model_id,
                    "prompt": "",
                    "keep_alive": 0
                }).encode("utf-8")
                req = urllib.request.Request(gen_url, data=gen_data,
                                            headers={"Content-Type": "application/json"})
                
                with urllib.request.urlopen(req, timeout=10) as resp:
                    logger.info("Unloaded auto-loaded Ollama model: %s", model_id)
        
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError, _json.JSONDecodeError) as e:
            logger.debug("Failed to unload model %s: %s", model_id, e)
    
    _auto_loaded_models.clear()


# Register cleanup handler
import atexit
atexit.register(_cleanup_auto_loaded_models)


# ── Local LLM health ──────────────────────────────────────────────────────

def check_local_llm() -> HealthReport:
    """Check Local LLM server prerequisites."""
    report = HealthReport(backend="local")
    checks = []

    api_url = config.get("local_llm", "api_url", "http://localhost:1234")
    api_type = config.get("local_llm", "api_type", "lmstudio")
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
