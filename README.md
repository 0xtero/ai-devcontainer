# Devcontainer Tool

Bash script to spin up a devcontainer pre-loaded with git, GitHub CLI, neovim, your `~/.pi` and `~/.config/nvim` configs, and port 4000 exposed.

## Dependencies

- [devcontainer](https://github.com/devcontainers/cli) CLI
- Docker
- Python 3 on the host
- Host Pi configuration in `~/.pi/agent` (or `PI_CODING_AGENT_DIR`)
- Dotfiles at `~/code/dotfiles`, including `install.sh --devcontainer`

Keep `devcontainer-tool.sh` and `pi_resources.py` together.

## Usage

```bash
./devcontainer-tool.sh create /path/to/project
./devcontainer-tool.sh start [path]
./devcontainer-tool.sh attach [path]
./devcontainer-tool.sh stop [path]
```

| Command | Description |
|---------|-------------|
| `create <path>` | Snapshots host Pi resources and writes `.devcontainer/devcontainer.json`. If one already exists, prompts to merge config and refresh the snapshot, with the old config backed up as `.bak`. |
| `start [path]` | Builds and starts the container for the workspace. Defaults to current directory. |
| `attach [path]` | Opens an interactive shell inside the running container. Defaults to current directory. |
| `stop [path]` | Stops the container for the workspace. Defaults to current directory. |

Each workspace directory is its own container — run `start /project/a` and `start /project/b` side by side. `attach` and `stop` target the container matching the given path.

## Host Pi resources

Each `create` captures a separate copy of the host's extensions, skills, settings, npm package manifests and lockfiles, git packages, prompts, themes, and agent definitions. Symlinks are followed so their targets remain available inside the container. Skills from `~/.agents/skills` and local paths listed in Pi settings are also copied. External paths must be literal files or directories, not globs.

Snapshots are kept in private directories under `~/.cache/ai-devcontainer`, outside the project repository. They can contain extension credentials, such as the Kagi configuration. The snapshot is mounted read-only and copied into the container after the dotfiles installer finishes. Existing container resources are backed up under `~/.pi/host-backup-*`. The existing `auth.json` bind mount remains shared with the host.

Host `node_modules`, Python virtual environments, browser profiles, and session history are not copied. npm dependencies are installed inside the container, using `npm ci` where a lockfile exists. Python environments are created for bundled `requirements.txt` files. Chromium is installed for extensions using Playwright Core. Python's venv support and `yt-dlp` are installed for the current host skills. Setup needs network access and runs the copied packages' installation scripts.

Host edits after `create` are not reflected in that snapshot. Run `create` again, accept the update, and rebuild the container to refresh it. Keep snapshots while their generated configs are in use. Old snapshots can be deleted once those configs and containers are no longer needed.

Existing post-create commands are retained and run before Pi setup. Object-form commands are run in sequence so Pi setup starts only after all of them succeed.

## Tests

```bash
python3 -m unittest -v test_pi_resources.py
bash -n devcontainer-tool.sh
bash -n test_devcontainer_deploy.sh
```

The tests use temporary host fixtures and mock dependency installation.

`test_devcontainer_deploy.sh` is a full end-to-end run (~5-10 minutes): it creates a fresh Debian devcontainer, deploys the dotfiles via `install.sh --devcontainer`, verifies the deployed environment, and removes the container. Needs Docker running and the dotfiles at `~/code/dotfiles`. Run it directly:

```bash
./test_devcontainer_deploy.sh
```

Should also work in VS Code.
VS Code detects `.devcontainer` automatically; reopen the folder in-container when prompted.
Add your VS Code extensions in devcontainer.json after creation
