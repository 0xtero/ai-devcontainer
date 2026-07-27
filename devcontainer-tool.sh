#!/usr/bin/env bash
set -euo pipefail

DEVCONTAINER_JSON='{
  "name": "AI Devcontainer",
  "image": "mcr.microsoft.com/devcontainers/base:debian",
  "features": {
    "ghcr.io/devcontainers/features/git:1": {},
    "ghcr.io/devcontainers/features/github-cli:1": {},
		"ghcr.io/devcontainers/features/common-utils": {
			"installZsh": true,
			"configureZshAsDefaultShell": true,
			"installOhMyZsh": false,
			"username": "vscode",
			"userUid": 1000,
			"userGid": 1000
		}
  },
  "mounts": [
    {
      "source": "${localEnv:HOME}/code/dotfiles",
      "target": "/workspaces/dotfiles",
      "type": "bind"
    },
    {
      "source": "${localEnv:HOME}/.pi/agent/extensions/kagi-websearch.json",
      "target": "/home/vscode/.pi/agent/extensions/kagi-websearch.json",
      "type": "bind"
    },
    {
      "source": "${localEnv:HOME}/.pi/agent/auth.json",
      "target": "/home/vscode/.pi/agent/auth.json",
      "type": "bind"
    }
  ],
  "containerEnv": {
    "EDITOR": "nvim",
    "VISUAL": "nvim"
  },
  "forwardPorts": [4000],
  "postCreateCommand": "sudo apt-get update && sudo apt-get install -y --no-install-recommends ripgrep fd-find tree-sitter-cli tmux && sudo ln -sf $(which fdfind) /usr/local/bin/fd && bash /workspaces/dotfiles/install.sh --devcontainer"
}'

create() {
  if [[ $# -lt 1 ]]; then
    echo "Usage: $0 create <path>" >&2
    exit 1
  fi
  local target="$1"
  local dc_dir="$target/.devcontainer"
  local dc_file="$dc_dir/devcontainer.json"

  mkdir -p "$dc_dir"

  if [[ -f "$dc_file" ]]; then
    read -rp "$dc_file already exists. Update it with missing base config? [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
      cp "$dc_file" "$dc_file.bak"
      if command -v python3 &>/dev/null; then
        local tmpbase
        tmpbase=$(mktemp)
        printf '%s\n' "$DEVCONTAINER_JSON" > "$tmpbase"
        python3 - "$dc_file" "$tmpbase" <<'PY' > "$dc_file.tmp"
import json, sys

def merge(base, existing):
    if isinstance(base, dict) and isinstance(existing, dict):
        for k, v in base.items():
            if k not in existing:
                existing[k] = v
            else:
                existing[k] = merge(v, existing[k])
        return existing
    if isinstance(base, list) and isinstance(existing, list):
        return existing + [x for x in base if x not in existing]
    return existing

with open(sys.argv[1]) as f:
    existing = json.load(f)
with open(sys.argv[2]) as f:
    base = json.load(f)
print(json.dumps(merge(base, existing), indent=2))
PY
        mv "$dc_file.tmp" "$dc_file"
        rm -f "$tmpbase"
        echo "Updated $dc_file"
      else
        echo "python3 not found; cannot merge. Skipping update." >&2
        exit 1
      fi
    else
      echo "Skipped."
    fi
  else
    printf '%s\n' "$DEVCONTAINER_JSON" > "$dc_file"
    echo "Created .devcontainer in $target"
  fi
}

start() {
  local path="${1:-.}"
  devcontainer up --workspace-folder "$path"
}

attach() {
  local path="${1:-.}"
  devcontainer exec --workspace-folder "$path" zsh || devcontainer exec --workspace-folder "$path" bash || devcontainer exec --workspace-folder "$path" sh
}

stop() {
  local path="${1:-.}"
  local id
  id=$(docker ps -q --filter "label=devcontainer.local_folder=$(cd "$path" && pwd)")
  [[ -n "$id" ]] && docker stop "$id"
}

remove() {
  local path="${1:-.}"
  local abs_path
  abs_path=$(cd "$path" && pwd)

  local running
  running=$(docker ps -q --filter "label=devcontainer.local_folder=$abs_path")
  if [[ -n "$running" ]]; then
    echo "Stopping running container(s)..."
    docker stop $running
  fi

  local containers
  containers=$(docker ps -aq --filter "label=devcontainer.local_folder=$abs_path")

  local images=""
  if [[ -n "$containers" ]]; then
    images=$(docker inspect --format='{{.Config.Image}}' $containers | sort -u)
    echo "Removing container(s)..."
    docker rm $containers
  fi

  if [[ -n "$images" ]]; then
    echo "Removing image(s): $images"
    docker rmi $images
  else
    echo "No devcontainer image found for $abs_path"
  fi
}

case "${1:-}" in
  create) shift; create "$@" ;;
  start)  shift; start "$@" ;;
  attach) shift; attach "$@" ;;
  stop)   shift; stop "$@" ;;
  remove) shift; remove "$@" ;;
  *)
    echo "Usage: $0 {create <path>|start [path]|attach [path]|stop [path]|remove [path]}" >&2
    exit 1
    ;;
esac
