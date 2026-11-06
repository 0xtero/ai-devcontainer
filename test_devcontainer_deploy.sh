#!/usr/bin/env bash
# End-to-end deploy test: fresh Debian devcontainer -> dotfiles install.sh --devcontainer -> verify.
# Needs: Docker daemon running, devcontainer CLI, python3, dotfiles at ~/code/dotfiles.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOL="$SCRIPT_DIR/devcontainer-tool.sh"
DC="devcontainer"

for dep in docker "$DC" python3 "$TOOL"; do
    command -v "$dep" >/dev/null 2>&1 || { echo "FAIL: $dep not found on PATH" >&2; exit 1; }
done
docker info >/dev/null 2>&1 || { echo "FAIL: Docker daemon not running" >&2; exit 1; }

DOTFILES_HOST="$HOME/code/dotfiles"
[[ -x "$DOTFILES_HOST/install.sh" ]] || { echo "FAIL: $DOTFILES_HOST/install.sh missing" >&2; exit 1; }

WORKSPACE="$(mktemp -d "${TMPDIR:-/tmp}/dc-deploy-test.XXXXXX")"
cleanup() {
    "$TOOL" remove "$WORKSPACE" >/dev/null 2>&1 || true
    rm -rf "$WORKSPACE"
}
trap cleanup EXIT

FAILS=0
run_in() { "$DC" exec --workspace-folder "$WORKSPACE" sh -lc "$*" >/dev/null 2>&1; }
check() {
    if run_in "$2"; then echo "PASS: $1"; else echo "FAIL: $1"; FAILS=$((FAILS+1)); fi
}

echo "== Creating fresh devcontainer at $WORKSPACE"
"$TOOL" create "$WORKSPACE"

echo "== Building container and running deploy (apt, node, nvim, pi, dotfiles, Pi resources)"
"$DC" up --workspace-folder "$WORKSPACE" >/dev/null
echo "PASS: devcontainer up (deploy completed)"

echo "== Verifying deployment"
check "latest Debian base" '. /etc/os-release && test "$NAME" = "Debian GNU/Linux" && test "$VERSION_ID" -ge 12'
check "zsh is default shell" 's=$(getent passwd vscode | cut -d: -f7); test "${s##*/}" = zsh'
check "required commands" 'for c in git zsh tmux nvim pi rg fd tree-sitter make unzip node npm python3; do command -v "$c" >/dev/null || exit 1; done'
check "pi runs" 'pi --version >/dev/null'
check "shell/tmux/nvim configs" 'test -s ~/.zshrc -a -s ~/.p10k.zsh -a -s ~/.tmux.conf -a -s ~/.config/tmux/tmux.conf -a -d ~/.config/nvim'
check "cloned repos" 'test -d ~/.oh-my-zsh/.git -a -d ~/code/powerlevel10k/.git -a -d ~/Documents/code/pi-kagi-websearch/.git -a -d ~/Documents/code/ai-devcontainer/.git'
check "pi core files" 'test -s ~/.pi/agent/settings.json -a -s ~/.pi/agent/APPEND_SYSTEM.md -a -s ~/.pi/agent/mcp.json -a -s ~/.pi/agent/npm/package.json'
check "pi npm deps installed" 'test -d ~/.pi/agent/npm/node_modules'
check "extensions installed" 'cd ~/.pi/agent/extensions && test -s modeline.ts -a -s ask-user-question.ts -a -s kagi-websearch.ts -a -d browser -a -d interactive-subagents'
check "extension deps installed" 'test -d ~/.pi/agent/extensions/browser/node_modules -a -d ~/.pi/agent/extensions/interactive-subagents/node_modules'
check "skills installed" 'cd ~/.pi/agent/skills && for s in keyfactor keyfactor-acme orange pdf-reader youtube-transcript; do test -s "$s/SKILL.md" || exit 1; done'
check "pdf-reader venv built" 'test -x ~/.pi/agent/skills/pdf-reader/.venv/bin/python'
check "auth.json has real secret" '! grep -q "<SECRET>" ~/.pi/agent/auth.json'
check "kagi config has real secret" '! grep -q "<SECRET>" ~/.pi/agent/extensions/kagi-websearch.json'

if [[ "$FAILS" -gt 0 ]]; then
    echo "== RESULT: $FAILS check(s) FAILED"
    exit 1
fi
echo "== RESULT: all checks passed"
