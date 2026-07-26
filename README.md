# Devcontainer Tool

Bash script to spin up a devcontainer pre-loaded with git, GitHub CLI, neovim, your `~/.pi` and `~/.config/nvim` configs, and port 4000 exposed.

## Dependencies

- [devcontainer](https://github.com/devcontainers/cli) CLI
- Docker

## Usage

```bash
./devcontainer-tool.sh create /path/to/project
./devcontainer-tool.sh start [path]
./devcontainer-tool.sh attach [path]
./devcontainer-tool.sh stop [path]
```

| Command | Description |
|---------|-------------|
| `create <path>` | Writes `.devcontainer/devcontainer.json` into the target directory. If one already exists, prompts to merge missing base config (backups the old file as `.bak`). |
| `start [path]` | Builds and starts the container for the workspace. Defaults to current directory. |
| `attach [path]` | Opens an interactive shell inside the running container. Defaults to current directory. |
| `stop [path]` | Stops the container for the workspace. Defaults to current directory. |

Each workspace directory is its own container — run `start /project/a` and `start /project/b` side by side. `attach` and `stop` target the container matching the given path.

Should also work in VS Code.
VS Code detects `.devcontainer` automatically; reopen the folder in-container when prompted.
Add your VS Code extensions in devcontainer.json after creation
