#!/bin/sh
set -eu
PROJECT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
APP="$HOME/Applications/Skill Pilot.app"
CLI="$HOME/.local/bin/skill-pilot"
PYTHON="$HOME/.local/share/uv/python/cpython-3.11-macos-aarch64-none/bin/python3.11"
mkdir -p "$APP/Contents/MacOS" "$(dirname "$CLI")"
cat > "$CLI" <<SCRIPT
#!/bin/sh
export PATH="/Users/j/.local/bin:/Users/j/bin:/Users/j/.nvm/versions/node/v24.21.0/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
if [ ! -x "$PYTHON" ]; then
  /usr/bin/osascript -e 'display alert "Skill Pilot 暂时打不开" message "找不到运行看板的 Python 3.11，请让助手重新安装启动入口。"' >/dev/null 2>&1
  echo '找不到运行看板的 Python 3.11，请让助手重新安装启动入口。' >&2
  exit 1
fi
cd "$PROJECT" || exit 1
export PYTHONDONTWRITEBYTECODE=1
exec "$PYTHON" -m skill_pilot "\$@"
SCRIPT
cat > "$APP/Contents/MacOS/SkillPilot" <<SCRIPT
#!/bin/sh
# Finder 启动不依赖终端环境；只读验收通过 open --env 显式传入。
/usr/bin/nohup "$CLI" ui >/dev/null 2>&1 < /dev/null &
exit 0
SCRIPT
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Skill Pilot</string>
<key>CFBundleDisplayName</key><string>Skill Pilot</string>
<key>CFBundleIdentifier</key><string>local.skill-pilot.dashboard</string>
<key>CFBundleVersion</key><string>7</string>
<key>CFBundleExecutable</key><string>SkillPilot</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>LSUIElement</key><true/>
</dict></plist>
PLIST
chmod +x "$CLI" "$APP/Contents/MacOS/SkillPilot"
/usr/bin/plutil -lint "$APP/Contents/Info.plist"
