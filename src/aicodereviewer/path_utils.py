# src/aicodereviewer/path_utils.py
"""
Path conversion utilities for Windows/WSL interoperability.

Provides functions to translate between Windows native paths and WSL
(Windows Subsystem for Linux) mount paths, enabling seamless file access
from CLI tools running inside WSL.

Functions:
    windows_to_wsl_path: Convert Windows path to WSL /mnt/ path
    wsl_to_windows_path: Convert WSL /mnt/ path back to Windows
    is_wsl_available: Check if WSL is installed and operational
    get_wsl_distros: List installed WSL distributions
    run_in_wsl: Execute a command inside WSL and return output
"""
import os
import re
import subprocess
import logging
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)


def windows_to_wsl_path(windows_path: str) -> str:
    """
    Convert a Windows filesystem path to its WSL /mnt/ equivalent.

    Handles:
    - Drive-letter paths:  D:\\folder\\file  -> /mnt/d/folder/file
    - UNC paths:           \\\\server\\share -> /mnt/wsl/server/share  (requires manual mount)

    Args:
        windows_path: Absolute Windows path (drive letter or UNC).

    Returns:
        Corresponding WSL mount path.

    Raises:
        ValueError: If the path cannot be converted.
    """
    # Normalise to forward slashes for easier regex work
    normed = windows_path.replace("\\", "/")

    # Drive-letter path  e.g. D:/folder/file
    m = re.match(r"^([A-Za-z]):/(.*)$", normed)
    if m:
        drive = m.group(1).lower()
        rest = m.group(2).rstrip("/")
        return f"/mnt/{drive}/{rest}" if rest else f"/mnt/{drive}"

    # UNC path  e.g. //server/share/folder
    m = re.match(r"^//([^/]+)/(.*)$", normed)
    if m:
        server = m.group(1)
        rest = m.group(2).rstrip("/")
        logger.warning(
            "UNC paths require the network share to be mounted inside WSL. "
            "Consider mapping the share to a drive letter for reliable access."
        )
        return f"/mnt/wsl/{server}/{rest}" if rest else f"/mnt/wsl/{server}"

    raise ValueError(f"Cannot convert path to WSL format: {windows_path}")


def wsl_to_windows_path(wsl_path: str) -> str:
    """
    Convert a WSL /mnt/<drive>/… path back to a Windows path.

    Args:
        wsl_path: WSL path starting with /mnt/.

    Returns:
        Windows-native path string.

    Raises:
        ValueError: If the path does not follow the /mnt/<drive>/… pattern.
    """
    m = re.match(r"^/mnt/([a-z])/?(.*)", wsl_path)
    if m:
        drive = m.group(1).upper()
        rest = m.group(2).replace("/", "\\")
        return f"{drive}:\\{rest}" if rest else f"{drive}:\\"

    raise ValueError(f"Cannot convert WSL path to Windows format: {wsl_path}")


def is_wsl_available() -> bool:
    """
    Check whether WSL is installed and operational on the current system.

    Returns:
        True if ``wsl --status`` succeeds, False otherwise.
    """
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            ["wsl", "--status"],
            capture_output=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_wsl_distros() -> List[str]:
    """
    List the installed WSL distributions.

    Returns:
        List of distribution names (e.g. ``['Ubuntu', 'Debian']``).
    """
    if not is_wsl_available():
        return []
    try:
        result = subprocess.run(
            ["wsl", "--list", "--quiet"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        # wsl --list --quiet may emit UTF-16; decode defensively
        raw = result.stdout
        if not raw and result.stdout:
            raw = result.stdout
        names = [line.strip() for line in raw.splitlines() if line.strip()]
        # Filter out null characters from UTF-16 output
        names = [n.replace("\x00", "") for n in names if n.replace("\x00", "").strip()]
        return names
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def run_in_wsl(
    command: List[str],
    *,
    distro: Optional[str] = None,
    cwd: Optional[str] = None,
    timeout: int = 300,
    stdin_data: Optional[str] = None,
) -> Tuple[int, str, str]:
    """
    Execute a command inside WSL and capture its output.

    Args:
        command: Command and arguments to run inside WSL.
        distro: WSL distribution to use (None = default).
        cwd: Working directory *inside* WSL (WSL path format).
        timeout: Maximum seconds to wait for the command.
        stdin_data: Optional string to pass on stdin.

    Returns:
        Tuple of (return_code, stdout, stderr).

    Raises:
        FileNotFoundError: If WSL is not installed.
        subprocess.TimeoutExpired: If the command exceeds *timeout*.
    """
    wsl_cmd: List[str] = ["wsl"]
    if distro:
        wsl_cmd += ["-d", distro]
    if cwd:
        wsl_cmd += ["--cd", cwd]
    wsl_cmd += ["--"] + command

    logger.debug("WSL command: %s", " ".join(wsl_cmd))

    # Build subprocess args - use explicit calls to avoid type issues with **kwargs
    if os.name == "nt":
        if stdin_data is not None:
            result = subprocess.run(
                wsl_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
                input=stdin_data,
            )
        else:
            result = subprocess.run(
                wsl_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
    else:
        if stdin_data is not None:
            result = subprocess.run(
                wsl_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
                input=stdin_data,
            )
        else:
            result = subprocess.run(
                wsl_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
    return result.returncode, result.stdout, result.stderr


def ensure_wsl_tool(tool_name: str, distro: Optional[str] = None) -> bool:
    """
    Check whether a CLI tool is available inside WSL.

    Args:
        tool_name: Name of the executable to test (e.g. ``kiro``).
        distro: WSL distribution to check inside.

    Returns:
        True if ``which <tool_name>`` succeeds in WSL.
    """
    try:
        rc, stdout, _ = run_in_wsl(["which", tool_name], distro=distro, timeout=10)
        return rc == 0 and bool(stdout.strip())
    except Exception:
        return False
