"""Bounded, cached dependency checks; installation always requires approval."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from urllib.request import Request, urlopen

import click
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from skills.neurolearn.config import CONFIG_DIR, Config

PACKAGES = (
    "yt-dlp", "youtube-transcript-api", "bgutil-ytdlp-pot-provider",
    "yt-dlp-ejs", "curl-cffi",
)
CHECK_INTERVAL = 24 * 60 * 60
REMINDER_INTERVAL = 7 * CHECK_INTERVAL
CHECK_TIMEOUT = 5.0
REQUEST_TIMEOUT = 0.8
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


def installed_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def fetch_latest(name: str) -> dict:
    """Use PyPI metadata, not executable remote data or an arbitrary URL."""
    if name not in PACKAGES:
        raise ValueError("Unknown dependency")
    request = Request(f"https://pypi.org/pypi/{name}/json", headers={
        "User-Agent": "neurolearn-update-check", "Accept": "application/json",
    })
    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Update metadata is too large")
    data = json.loads(raw)
    raw_version = data["info"]["version"]
    if not isinstance(raw_version, str) or len(raw_version) > 80:
        raise ValueError("Invalid release version")
    version = Version(raw_version)
    if version.is_prerelease or version.is_devrelease:
        raise ValueError("Latest metadata is not a stable release")
    files = data.get("urls", [])
    if not files or all(item.get("yanked", False) for item in files):
        raise ValueError("Latest release has no non-yanked distribution")
    requires = data["info"].get("requires_python") or ""
    if not isinstance(requires, str) or len(requires) > 200:
        raise ValueError("Invalid Python requirement")
    SpecifierSet(requires)  # Reject malformed metadata before caching it.
    return {"version": str(version), "requires_python": requires}


def fetch_releases(names: tuple[str, ...]) -> dict:
    """Kill/reap the metadata worker on timeout, including stalled DNS/reads.

    Socket timeouts alone do not bound DNS resolution or a trickling response.
    The worker emits at most five small validated metadata records.
    """
    if any(name not in PACKAGES for name in names):
        raise ValueError("Unknown dependency")
    result = subprocess.run(
        [sys.executable, "-m", "skills.neurolearn.updates", "--fetch-metadata", *names],
        cwd=Path(__file__).resolve().parents[2],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        timeout=CHECK_TIMEOUT, check=True,
    )
    if len(result.stdout) > 4096:
        raise ValueError("Unexpected metadata worker response")
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        raise ValueError("Invalid metadata worker response")
    return {name: data.get(name, {}) for name in names}


def _cache_path() -> Path:
    environment = os.path.normcase(str(Path(sys.prefix).resolve()))
    key = hashlib.sha256(environment.encode()).hexdigest()[:20]
    return CONFIG_DIR / "updates" / f"{key}.json"


def _read_state(path: Path) -> dict:
    try:
        if path.stat().st_size > 64 * 1024:
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".updates-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(state, stream)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _recent(value, now: float, interval: float) -> bool:
    return (isinstance(value, (int, float)) and math.isfinite(value)
            and 0 <= now - value < interval)


def _rows(versions: dict, state: dict) -> list[dict]:
    results = state.get("results", {})
    if not isinstance(results, dict):
        results = {}
    rows = []
    for name, installed in versions.items():
        result = results.get(name, {})
        row = {"package": name, "installed": installed, "latest": None, "status": "unknown"}
        try:
            latest = Version(result["version"])
            if latest.is_prerelease or latest.is_devrelease:
                raise ValueError("Unstable release")
            row["latest"] = str(latest)
            compatible = SpecifierSet(result.get("requires_python", "")).contains(
                ".".join(map(str, sys.version_info[:3])), prereleases=True,
            )
            if not compatible:
                row["status"] = "python_incompatible"
            elif installed is None:
                row["status"] = "not_installed"
            elif latest > Version(installed):
                row["status"] = "update_available"
            else:
                row["status"] = "current"
        except (KeyError, TypeError, ValueError):
            pass
        rows.append(row)
    return rows


def check_updates(*, force: bool = False, notify: bool = False) -> dict:
    """Cache attempts (including failures) per environment; never install."""
    now = time.time()
    path = _cache_path()
    state = _read_state(path)
    versions = installed_versions()
    locked = False
    lock = path.with_suffix(".lock")
    error = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # A killed check must not disable checks forever. Ordinary checks use
        # five short requests, so a five-minute lease leaves ample headroom.
        try:
            if now - lock.stat().st_mtime > 300:
                lock.unlink()
        except FileNotFoundError:
            pass
        try:
            with lock.open("x", encoding="utf-8"):
                pass
            locked = True
        except FileExistsError:
            error = "Another update check is running"
        if locked:
            state = _read_state(path)  # Another process may have just finished.
            if force or not _recent(state.get("attempted_at"), now, CHECK_INTERVAL):
                state["attempted_at"] = now
                state["results"] = {}  # Failed refreshes must not look current.
                _write_state(path, state)
                try:
                    state["results"] = fetch_releases(tuple(versions))
                except Exception:
                    state["results"] = {}
                _write_state(path, state)
            rows = _rows(versions, state)
            available = [r for r in rows if r["status"] in ("update_available", "not_installed")]
            fingerprint = json.dumps(available, sort_keys=True)
            if notify and available and (
                state.get("notification") != fingerprint
                or not _recent(state.get("notified_at"), now, REMINDER_INTERVAL)
            ):
                message = "; ".join(
                    f"{r['package']} {r['installed'] or 'not installed'} -> {r['latest']}"
                    for r in available
                )
                click.echo(f"[neurolearn] Dependency updates: {message}. "
                           "Run `neurolearn update-deps` to review and approve. "
                           "The resolver checks project compatibility.", err=True)
                state.update(notification=fingerprint, notified_at=now)
                _write_state(path, state)
    except OSError:
        error = "Update cache is unavailable; no network check was attempted or completed"
    finally:
        if locked:
            try:
                lock.unlink(missing_ok=True)
            except OSError:
                pass
    return {"environment": str(Path(sys.prefix).resolve()),
            "checked_at": state.get("attempted_at"), "error": error,
            "packages": _rows(versions, state)}


def maybe_notify_updates(cfg: Config) -> None:
    if not cfg.update_check_enabled or os.environ.get("NEUROLEARN_NO_UPDATE_CHECK") == "1":
        return
    try:
        check_updates(notify=True)
    except Exception:
        # This optional advisory must never prevent the requested transcript.
        pass


def _show(report: dict) -> None:
    click.echo(f"Environment: {report['environment']}")
    for row in report["packages"]:
        click.echo(f"{row['package']}: {row['installed'] or 'not installed'} -> "
                   f"{row['latest'] or 'unknown'} ({row['status']})")
    if report.get("error"):
        click.echo(report["error"], err=True)
    if any(row["status"] == "unknown" for row in report["packages"]):
        click.echo("Some release metadata could not be checked; this does not mean up to date.", err=True)


@click.command("check-updates")
@click.option("--json", "as_json", is_flag=True, help="Print machine-readable results.")
def check_updates_cmd(as_json: bool) -> None:
    """Check the latest stable YouTube dependencies now (never install)."""
    report = check_updates(force=True)
    if as_json:
        click.echo(json.dumps(report))
    else:
        _show(report)


def update_project() -> Path:
    """Only update the checkout and venv that actually run this module."""
    root = Path(__file__).resolve().parents[2]
    try:
        metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        valid = metadata.get("project", {}).get("name") == "neurolearn"
    except (OSError, ValueError):
        valid = False
    if (not valid or not (root / "uv.lock").is_file()
            or Path(sys.prefix).resolve() != (root / ".venv").resolve()):
        raise click.ClickException(
            "This updater requires NeuroLearn's uv checkout and its .venv. "
            "For another installation, update with its original package manager; "
            "no global packages were changed."
        )
    return root


def _interactive() -> bool:
    return sys.stdin.isatty()


@click.command("update-deps")
@click.option("--yes", is_flag=True, help="Explicitly approve updating the displayed environment.")
def update_deps_cmd(yes: bool) -> None:
    """Review and approve a targeted YouTube dependency update."""
    root = update_project()
    uv = shutil.which("uv")
    if not uv:
        raise click.ClickException("uv is required to update this checkout.")
    report = check_updates(force=True)
    _show(report)
    click.echo(f"Project: {root}\nUpdate packages: {', '.join(PACKAGES)}\n"
               "The resolver selects stable versions allowed by this project's constraints, "
               "including yt-dlp's matching EJS version. The bgutil provider server "
               "requires a separate matching update. Existing extras are retained.")
    if not yes:
        if not _interactive():
            raise click.ClickException("Approval required: rerun interactively or pass --yes after approval.")
        if not click.confirm("Update these dependencies now?", default=False):
            click.echo("Cancelled; dependencies unchanged.")
            return
    env = dict(os.environ, UV_PROJECT_ENVIRONMENT=str(Path(sys.prefix).resolve()))
    command = [uv, "lock", "--project", str(root)]
    for name in PACKAGES:
        command.extend(["--upgrade-package", name])
    try:
        subprocess.run(command, cwd=root, env=env, check=True, timeout=300)
        subprocess.run([uv, "sync", "--project", str(root), "--inexact", "--locked"],
                       cwd=root, env=env, check=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        raise click.ClickException(
            "Dependency update failed; the lockfile or environment may be partially updated. "
            f"Resolve the package-manager error and retry. ({type(exc).__name__})"
        ) from exc
    click.echo("Dependency update completed. Restart NeuroLearn and run `neurolearn doctor`.")


if __name__ == "__main__":
    # Private, read-only worker entrypoint: no credentials, installation or
    # arbitrary URLs/commands. Invoked only with fixed dependency names.
    if len(sys.argv) < 3 or sys.argv[1] != "--fetch-metadata":
        raise SystemExit(2)
    names = sys.argv[2:]
    if len(names) > len(PACKAGES) or any(name not in PACKAGES for name in names):
        raise SystemExit(2)
    releases = {}
    for name in names:
        try:
            releases[name] = fetch_latest(name)
        except Exception:
            releases[name] = {}
    print(json.dumps(releases))
