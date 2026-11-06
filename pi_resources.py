import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile


MOUNT = "/opt/pi-host"
SETUP = (
    "sudo apt-get update && sudo apt-get install -y --no-install-recommends "
    "python3 python3-venv yt-dlp && "
    'mkdir -p "$HOME/.pi" && setup=$(mktemp -d "$HOME/.pi/host-setup.XXXXXX") && '
    'sudo cp -R /opt/pi-host/. "$setup/" && '
    'sudo chown -R "$(id -u):$(id -g)" "$setup" && '
    'python3 "$setup/pi_resources.py" install'
)
IGNORE = shutil.ignore_patterns("node_modules", ".venv", "__pycache__", ".profile")


def copy(source, target):
    if source.is_dir():
        shutil.copytree(source, target, ignore=IGNORE)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def snapshot():
    host = Path(os.environ.get("PI_CODING_AGENT_DIR", Path.home() / ".pi/agent")).expanduser().absolute()
    if not host.is_dir():
        raise ValueError(f"Pi agent directory not found: {host}")
    cache = Path.home() / ".cache/ai-devcontainer"
    cache.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="pi-", dir=cache))
    agent = root / "agent"
    agent.mkdir()
    for name in ("extensions", "skills", "prompts", "themes", "agents", "npm", "git"):
        source = host / name
        if source.exists():
            copy(source, agent / name)
        elif name in ("extensions", "skills"):
            (agent / name).mkdir()
    settings_file = host / "settings.json"
    settings = json.loads(settings_file.read_text()) if settings_file.exists() else {}

    def resource(value):
        prefix = value[0] if value.startswith(("!", "+", "-")) else ""
        path = value[len(prefix):]
        if path.startswith("builtin:"):
            return value
        source = Path(path).expanduser()
        if not source.is_absolute():
            source = host / source
        source = Path(os.path.abspath(source))
        try:
            relative = source.relative_to(host)
        except ValueError:
            target = agent / "host-resources" / str(len(external)) / source.name
            if source not in external:
                copy(source, target)
                external[source] = "./" + str(target.relative_to(agent))
            return prefix + external[source]
        if relative.parts and not (agent / relative.parts[0]).exists():
            copy(host / relative.parts[0], agent / relative.parts[0])
        return prefix + "./" + str(relative)

    external = {}
    for kind in ("extensions", "skills", "prompts", "themes"):
        if kind in settings:
            settings[kind] = [resource(value) for value in settings[kind]]
    for index, package in enumerate(settings.get("packages", [])):
        source = package if isinstance(package, str) else package["source"]
        if source.startswith((".", "/", "~")):
            mapped = resource(source)
            if isinstance(package, dict):
                package["source"] = mapped
            else:
                settings["packages"][index] = mapped
    shared_skills = Path.home() / ".agents/skills"
    if shared_skills.is_dir():
        copy(shared_skills, agent / "host-agent-skills")
        settings.setdefault("skills", []).append("./host-agent-skills")
    (agent / "settings.json").write_text(json.dumps(settings, indent=2) + "\n")
    shutil.copy2(__file__, root / "pi_resources.py")
    return root


def merge(base, existing):
    if isinstance(base, dict) and isinstance(existing, dict):
        return {**base, **{key: merge(base.get(key), value) for key, value in existing.items()}}
    if isinstance(base, list) and isinstance(existing, list):
        return existing + [value for value in base if value not in existing]
    return existing


def shell_command(command):
    if isinstance(command, str):
        return command
    if isinstance(command, list):
        return shlex.join(command)
    return " && ".join(f"({shell_command(value)})" for value in command.values())


def configure(base, existing):
    config = merge(base, existing)
    mounts = config.setdefault("mounts", [])
    targets = {MOUNT, "/home/vscode/.pi/agent/extensions/kagi-websearch.json"}
    config["mounts"] = [mount for mount in mounts if not (
        mount.get("target") in targets if isinstance(mount, dict)
        else any(part in {f"target={target}", f"dst={target}", f"destination={target}"}
                 for part in mount.split(",") for target in targets)
    )]
    root = snapshot()
    config["mounts"].append(f"source={root},target={MOUNT},type=bind,readonly")
    command = shell_command(config.get("postCreateCommand", ""))
    if SETUP not in command:
        config["postCreateCommand"] = f"({command}) && {SETUP}" if command else SETUP
    return config


def install():
    source = Path(__file__).resolve().parent / "agent"
    target = Path.home() / ".pi/agent"
    target.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="host-backup-", dir=target.parent))
    for item in source.iterdir():
        dest = target / item.name
        if dest.exists() or dest.is_symlink():
            dest.rename(backup / item.name)
        copy(item, dest)
    for manifest in source.rglob("package.json"):
        directory = target / manifest.parent.relative_to(source)
        command = "ci" if (directory / "package-lock.json").exists() else "install"
        subprocess.run(["npm", command, "--omit=dev", "--legacy-peer-deps"], cwd=directory, check=True)
        playwright = directory / "node_modules/playwright-core/cli.js"
        if playwright.exists():
            subprocess.run(["node", str(playwright), "install", "--with-deps", "chromium"], check=True)
    for requirements in source.rglob("requirements.txt"):
        directory = target / requirements.parent.relative_to(source)
        venv = directory / ".venv"
        subprocess.run(["python3", "-m", "venv", str(venv)], check=True)
        subprocess.run([str(venv / "bin/pip"), "install", "-r", str(directory / "requirements.txt")], check=True)


if __name__ == "__main__":
    if sys.argv[1] == "install":
        install()
    else:
        existing = json.loads(Path(sys.argv[1]).read_text()) if Path(sys.argv[1]).exists() else {}
        print(json.dumps(configure(json.load(sys.stdin), existing), indent=2))
