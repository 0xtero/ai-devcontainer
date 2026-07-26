# Devcontainer Tool

Bash script to spin up a devcontainer pre-loaded with git, GitHub CLI, neovim, your `~/.pi` and `~/.config/nvim` configs, and port 4000 exposed.

## Dependencies

- [devcontainer](https://github.com/devcontainers/cli) CLI
- Docker

## Usage

```bash
./devcontainer-tool.sh create /path/to/project
./devcontainer-tool.sh start
./devcontainer-tool.sh stop
```

- `create <path>` — writes `.devcontainer/devcontainer.json` into the target directory.
- `start` — builds/starts the container and drops you into an interactive shell.
- `stop` — stops the running container.

Should also work in VS Code. 
VS Code detects `.devcontainer` automatically; reopen the folder in-container when prompted.
Add your VS Code extensions in devcontainer.json after creation
