# src/aicodereviewer/backends/models.py
"""
Model discovery and auto-loading for all backend types.

Provides lazy-cached model list retrieval for Copilot, Bedrock, and
local LLM backends.  Auto-loads the first available model when none are
already running (LM Studio / Ollama) and cleans up on exit.
"""
import atexit
import logging
import os
import subprocess
from typing import Dict, List, Optional, Tuple

from aicodereviewer.config import config

logger = logging.getLogger(__name__)


# ── Shared subprocess helper ───────────────────────────────────────────────

def _run_quiet(cmd: List[str], timeout: int = 10) -> tuple[int, str, str]:
    """Run a command silently, returning (returncode, stdout, stderr)."""
    try:
        if os.name == "nt":
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                encoding="utf-8", errors="replace",
            )
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return -1, "", "Command not found"
    except subprocess.TimeoutExpired:
        return -2, "", "Timeout"
    except Exception as e:
        return -3, "", str(e)


# ── GitHub Copilot model discovery ─────────────────────────────────────────

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

    _, stdout, stderr = _run_quiet([copilot_path, "--help"], timeout=5)
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

    rc, stdout, _ = _run_quiet(
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


# ── Local LLM model discovery ──────────────────────────────────────────────

_local_models_cache: List[str] = []
_local_models_cache_key: Tuple[str, str] = ("", "")  # (api_url, api_type) tuple
_auto_loaded_models: Dict[Tuple[str, str], str] = {}  # {(api_url, api_type): model_id} - tracks models we auto-loaded


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
    from typing import Any as _Any

    models: List[str] = []
    api_url = api_url.rstrip("/")
    api_type = api_type.strip().lower()

    # Determine the models endpoint based on API type
    if api_type == "lmstudio":
        models_url = f"{api_url}/api/v1/models"
        try:
            # Query the models endpoint
            with urllib.request.urlopen(models_url, timeout=5) as resp:
                data: _Any = _json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict) and "models" in data:
                    model_list: list[_Any] = data["models"]
                    if isinstance(model_list, list):
                        # Extract loaded model instance IDs
                        for m in model_list:
                            if isinstance(m, dict):
                                loaded_instances: list[_Any] = m.get("loaded_instances", [])
                                for instance in loaded_instances:
                                    if isinstance(instance, dict):
                                        instance_id: str = instance.get("id", "")
                                        if instance_id:
                                            models.append(instance_id)

                        # If no loaded instances, list available (downloaded) models instead
                        if not models:
                            for m in model_list:
                                if isinstance(m, dict):
                                    model_key: str = m.get("key", "")
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
                        models = sorted([
                            str(m.get("name", m)) if isinstance(m, dict) else str(m)
                            for m in model_list if m
                        ])
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
                        models = sorted([
                            str(m.get("id", m)) if isinstance(m, dict) else str(m)
                            for m in model_list if m
                        ])
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
    from typing import Any as _Any

    model_loaded: Optional[str] = None
    cache_key: Tuple[str, str] = (api_url, api_type)

    try:
        if api_type == "lmstudio":
            # Get list of all available (downloaded) models
            list_url = f"{api_url}/api/v1/models"
            with urllib.request.urlopen(list_url, timeout=5) as resp:
                data: _Any = _json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict) and "models" in data and data["models"]:
                    # Find first model that isn't loaded yet
                    model_entry: _Any
                    for model_entry in data["models"]:
                        if isinstance(model_entry, dict):
                            model_key: str = str(model_entry.get("key", ""))
                            loaded_instances: list[_Any] = model_entry.get("loaded_instances", [])

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
                                    result: _Any = _json.loads(load_resp.read().decode("utf-8"))
                                    if isinstance(result, dict) and result.get("status") == "loaded":
                                        model_loaded = str(result.get("instance_id", "")) or model_key
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
                    first_model: _Any = data["models"][0]
                    model_name: str = str(first_model.get("name", "")) if isinstance(first_model, dict) else ""

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
                                    if isinstance(result, dict) and result.get("done"):
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
                    if isinstance(first_model, dict):
                        model_loaded = str(first_model.get("id", "")) or str(first_model.get("model", ""))
                    logger.debug("OpenAI-compatible model available: %s", model_loaded)
                    # Don't track as auto-loaded since we didn't explicitly load it

    except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError, _json.JSONDecodeError) as e:
        logger.debug("Failed to auto-load model for %s: %s", api_type, e)

    return model_loaded


def _cleanup_auto_loaded_models() -> None:
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
atexit.register(_cleanup_auto_loaded_models)
