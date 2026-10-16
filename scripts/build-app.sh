#!/bin/sh
set -eu
PROJECT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
SUPPORTED='import sys; assert sys.version_info >= (3, 11, 4)'

if [ -n "${SKILL_PILOT_PYTHON:-}" ]; then
  if "$SKILL_PILOT_PYTHON" -c "$SUPPORTED" >/dev/null 2>&1; then
    exec "$SKILL_PILOT_PYTHON" -B "$PROJECT/scripts/install.py"
  fi
  echo '指定的 Python 不可用，需要 Python 3.11.4 或更高版本。' >&2
  exit 1
fi

for candidate in python3 python3.14 python3.13 python3.12 python3.11 \
    /opt/homebrew/bin/python3 /usr/local/bin/python3 \
    "$HOME"/.local/share/uv/python/*/bin/python3 \
    "$HOME"/.pyenv/versions/*/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/*/bin/python3; do
  if "$candidate" -c "$SUPPORTED" >/dev/null 2>&1; then
    exec "$candidate" -B "$PROJECT/scripts/install.py"
  fi
done
echo '找不到可用的 Python，请先安装 Python 3.11.4 或更高版本，再重新运行安装。' >&2
exit 1
