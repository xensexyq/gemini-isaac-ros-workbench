#!/usr/bin/env bash
# 仅验证容器和算法组件，绝不启动相机或枚举 SDK 设备。
set -euo pipefail
umask 0002
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME=gemini-isaac-ros-live
if docker inspect "$NAME" >/dev/null 2>&1; then
  echo '已有实机容器，请先结束当前会话；本检查不会复用或打断它。' >&2
  exit 2
fi
RUN="$ROOT/runs/$(date +%Y%m%d-%H%M%S)-camera-validation"
mkdir -p "$RUN/logs" "$RUN/reports"
CREATED=0
finish() {
  CODE=$?
  if [[ "$CREATED" == 1 ]]; then "$ROOT/scripts/live.sh" stop > "$RUN/logs/stop.log" 2>&1 || true; fi
  printf '%s\n' "$CODE" > "$RUN/reports/exit-code.txt"
  echo "无相机检查退出码：$CODE；证据：$RUN"
}
trap finish EXIT
bash -n "$ROOT/scripts/live.sh" "$ROOT/scripts/build_camera_image.sh" "$0"
"$ROOT/scripts/live.sh" start > "$RUN/logs/start.log"
CREATED=1
"$ROOT/scripts/live.sh" start > "$RUN/logs/start-idempotent.log"
"$ROOT/scripts/live.sh" status > "$RUN/reports/container-status.txt"
docker inspect "$NAME" > "$RUN/reports/container-inspect.json"
python3 - "$RUN/reports/container-inspect.json" > "$RUN/reports/container-policy.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))[0]
h=x['HostConfig']
assert not h['Privileged'] and h['ReadonlyRootfs']
assert h['NetworkMode']=='none' and h['CapDrop']==['ALL']
assert 'c 189:* rw' in h['DeviceCgroupRules']
assert any(m['Source']=='/dev/bus/usb' and m['Destination']=='/dev/bus/usb' and m['RW'] for m in x['Mounts'])
assert any(s.startswith('no-new-privileges') for s in h['SecurityOpt'])
print(json.dumps({'status':'PASS','usb_bus_mount':True,'privileged':False,
                  'readonly_root':True,'network':'none','capabilities':'dropped'},indent=2))
PY
"$ROOT/scripts/live.sh" exec python3 -c 'import ast, pathlib; ast.parse(pathlib.Path("/workspaces/isaac_ros-dev/scripts/orbbec_live.launch.py").read_text())'
"$ROOT/scripts/live.sh" exec ros2 pkg executables orbbec_camera > "$RUN/reports/orbbec-executables.txt"
"$ROOT/scripts/live.sh" exec python3 -c '
import hashlib,json,pathlib,subprocess,xml.etree.ElementTree as ET
root=pathlib.Path("/opt/orbbec_ws/install")
version=ET.parse(root/"share/orbbec_camera/package.xml").findtext("version")
assert version=="2.10.6", version
sdk=root/"lib/libOrbbecSDK.so.2.10.6"
assert sdk.is_file(),sdk
ldd=subprocess.check_output(["ldd",str(root/"lib/liborbbec_camera.so")],text=True)
assert "not found" not in ldd,ldd
print(json.dumps({"wrapper_version":version,"sdk_library_sha256":hashlib.sha256(sdk.read_bytes()).hexdigest(),"shared_libraries":"PASS"},indent=2))
' > "$RUN/reports/driver.json"
"$ROOT/scripts/live.sh" exec ros2 launch orbbec_camera gemini_330_series.launch.py --show-args > "$RUN/reports/official-launch-args.txt"
"$ROOT/scripts/live.sh" exec ros2 launch /workspaces/isaac_ros-dev/scripts/orbbec_live.launch.py --show-args > "$RUN/reports/live-launch-args.txt"
"$ROOT/scripts/live.sh" exec python3 /workspaces/isaac_ros-dev/scripts/gpu_smoke.py > "$RUN/reports/gpu.json"
C_RUN="/workspaces/isaac_ros-dev/${RUN#"$ROOT/"}"
"$ROOT/scripts/live.sh" exec python3 /workspaces/isaac_ros-dev/scripts/check_live_startup.py \
  "$C_RUN/reports/startup.json" "$C_RUN/logs/startup.log" > "$RUN/logs/check.log"
printf '%s\n' "$RUN" > "$ROOT/runs/latest-camera-validation.txt"
