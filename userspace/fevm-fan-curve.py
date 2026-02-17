#!/usr/bin/env python3
import argparse
import glob
import logging
import os
import signal
import time
from typing import Dict, List, Sequence, Tuple

try:
    import tomllib as toml_reader  # Python 3.11+
except ModuleNotFoundError:
    try:
        import tomli as toml_reader  # Python <= 3.10
    except ModuleNotFoundError:
        toml_reader = None

Curve = List[Tuple[float, int]]

DEFAULT_CONFIG: Dict[str, object] = {
    "fan1_path": "/sys/devices/platform/fevm-ip3-wmi/fan1_duty",  # CPU fan
    "fan2_path": "/sys/devices/platform/fevm-ip3-wmi/fan2_duty",  # Memory fan
    "poll_sec": 1.0,
    "min_duty": 20,
    "max_duty": 100,
    "failsafe_duty": 70,
    "cpu_sensor_names": ["k10temp"],
    "mem_sensor_names": ["spd5118"],
    "mem_fallback_to_cpu": True,
    "cpu_curve": [(40, 20), (55, 35), (65, 55), (75, 75), (85, 100)],
    "mem_curve": [(35, 20), (50, 40), (60, 60), (70, 80), (80, 100)],
}

RUNNING = True


def _sigterm_handler(signum, frame):
    del signum, frame
    global RUNNING
    RUNNING = False


def parse_curve(raw: Sequence[Sequence[object]], key: str) -> Curve:
    points: Curve = []
    for idx, point in enumerate(raw):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError(f"{key}[{idx}] must be [temp_c, duty]")
        temp_c = float(point[0])
        duty = int(point[1])
        points.append((temp_c, duty))

    if not points:
        raise ValueError(f"{key} must not be empty")

    prev_t = None
    for temp_c, _ in points:
        if prev_t is not None and temp_c <= prev_t:
            raise ValueError(f"{key} temperatures must be strictly increasing")
        prev_t = temp_c

    return points


def load_config(path: str) -> Dict[str, object]:
    cfg = {
        "fan1_path": str(DEFAULT_CONFIG["fan1_path"]),
        "fan2_path": str(DEFAULT_CONFIG["fan2_path"]),
        "poll_sec": float(DEFAULT_CONFIG["poll_sec"]),
        "min_duty": int(DEFAULT_CONFIG["min_duty"]),
        "max_duty": int(DEFAULT_CONFIG["max_duty"]),
        "failsafe_duty": int(DEFAULT_CONFIG["failsafe_duty"]),
        "cpu_sensor_names": list(DEFAULT_CONFIG["cpu_sensor_names"]),
        "mem_sensor_names": list(DEFAULT_CONFIG["mem_sensor_names"]),
        "mem_fallback_to_cpu": bool(DEFAULT_CONFIG["mem_fallback_to_cpu"]),
        "cpu_curve": list(DEFAULT_CONFIG["cpu_curve"]),
        "mem_curve": list(DEFAULT_CONFIG["mem_curve"]),
    }

    if not os.path.exists(path):
        return cfg

    if toml_reader is None:
        raise RuntimeError("No TOML parser: use Python 3.11+ or install tomli")

    with open(path, "rb") as f:
        data = toml_reader.load(f)

    general = data.get("general", {})
    sensors = data.get("sensors", {})
    curves = data.get("curves", {})

    if "fan1_path" in general:
        cfg["fan1_path"] = str(general["fan1_path"])
    if "fan2_path" in general:
        cfg["fan2_path"] = str(general["fan2_path"])
    if "poll_sec" in general:
        cfg["poll_sec"] = float(general["poll_sec"])
    if "min_duty" in general:
        cfg["min_duty"] = int(general["min_duty"])
    if "max_duty" in general:
        cfg["max_duty"] = int(general["max_duty"])
    if "failsafe_duty" in general:
        cfg["failsafe_duty"] = int(general["failsafe_duty"])

    if "cpu_names" in sensors:
        cfg["cpu_sensor_names"] = [str(x) for x in sensors["cpu_names"]]
    if "mem_names" in sensors:
        cfg["mem_sensor_names"] = [str(x) for x in sensors["mem_names"]]
    if "mem_fallback_to_cpu" in sensors:
        cfg["mem_fallback_to_cpu"] = bool(sensors["mem_fallback_to_cpu"])

    if "cpu" in curves:
        cfg["cpu_curve"] = parse_curve(curves["cpu"], "curves.cpu")
    if "mem" in curves:
        cfg["mem_curve"] = parse_curve(curves["mem"], "curves.mem")

    return cfg


def find_hwmons_by_name(name: str) -> List[str]:
    found = []
    for p in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            with open(os.path.join(p, "name"), "r", encoding="utf-8") as f:
                if f.read().strip() == name:
                    found.append(p)
        except FileNotFoundError:
            continue
    return found


def resolve_hwmons(names: Sequence[str]) -> List[str]:
    dedup = []
    seen = set()
    for name in names:
        for hwmon in find_hwmons_by_name(name):
            if hwmon not in seen:
                dedup.append(hwmon)
                seen.add(hwmon)
    return dedup


def read_temp_millic(path: str) -> float:
    with open(path, "r", encoding="utf-8") as f:
        return int(f.read().strip()) / 1000.0


def max_temp_in_hwmons(hwmon_paths: Sequence[str]) -> float:
    temps = []
    for hwmon in hwmon_paths:
        for t in glob.glob(os.path.join(hwmon, "temp*_input")):
            try:
                temps.append(read_temp_millic(t))
            except Exception:
                continue
    if not temps:
        raise RuntimeError(f"no temp*_input found under {hwmon_paths}")
    return max(temps)


def lerp_curve(temp_c: float, curve: Curve) -> int:
    if temp_c <= curve[0][0]:
        return curve[0][1]
    if temp_c >= curve[-1][0]:
        return curve[-1][1]

    for (t0, d0), (t1, d1) in zip(curve, curve[1:]):
        if t0 <= temp_c <= t1:
            ratio = (temp_c - t0) / (t1 - t0)
            return int(round(d0 + ratio * (d1 - d0)))

    return curve[-1][1]


def clamp_duty(duty: int, min_duty: int, max_duty: int) -> int:
    return max(min_duty, min(max_duty, duty))


def write_duty(path: str, duty: int, min_duty: int, max_duty: int):
    duty = clamp_duty(duty, min_duty, max_duty)
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(duty))


def main() -> int:
    parser = argparse.ArgumentParser(description="FEVM fan curve daemon")
    parser.add_argument("--config", default="/etc/fevm-fan-curve.toml", help="TOML config path")
    parser.add_argument("--log-level", default="INFO", help="DEBUG/INFO/WARNING/ERROR")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    signal.signal(signal.SIGTERM, _sigterm_handler)
    signal.signal(signal.SIGINT, _sigterm_handler)

    cfg = load_config(args.config)

    fan1_path = str(cfg["fan1_path"])
    fan2_path = str(cfg["fan2_path"])
    poll_sec = float(cfg["poll_sec"])
    min_duty = int(cfg["min_duty"])
    max_duty = int(cfg["max_duty"])
    failsafe_duty = int(cfg["failsafe_duty"])
    cpu_curve: Curve = list(cfg["cpu_curve"])
    mem_curve: Curve = list(cfg["mem_curve"])

    cpu_hwmons = resolve_hwmons(cfg["cpu_sensor_names"])
    mem_hwmons = resolve_hwmons(cfg["mem_sensor_names"])

    if not cpu_hwmons:
        raise SystemExit(f"CPU hwmon not found, names={cfg['cpu_sensor_names']}")

    if not mem_hwmons:
        if bool(cfg["mem_fallback_to_cpu"]):
            mem_hwmons = cpu_hwmons
            logging.warning("memory hwmon not found, fallback to CPU sensor")
        else:
            raise SystemExit(f"MEM hwmon not found, names={cfg['mem_sensor_names']}")

    logging.info("cpu_hwmons=%s mem_hwmons=%s", cpu_hwmons, mem_hwmons)
    logging.info("fan1=%s fan2=%s poll=%.2fs", fan1_path, fan2_path, poll_sec)

    while RUNNING:
        try:
            cpu_t = max_temp_in_hwmons(cpu_hwmons)
            mem_t = max_temp_in_hwmons(mem_hwmons)

            cpu_duty = lerp_curve(cpu_t, cpu_curve)
            mem_duty = lerp_curve(mem_t, mem_curve)

            write_duty(fan1_path, cpu_duty, min_duty, max_duty)
            write_duty(fan2_path, mem_duty, min_duty, max_duty)

            logging.debug(
                "cpu=%.1fC mem=%.1fC -> fan1=%d fan2=%d",
                cpu_t,
                mem_t,
                clamp_duty(cpu_duty, min_duty, max_duty),
                clamp_duty(mem_duty, min_duty, max_duty),
            )
        except Exception as e:
            logging.exception("fan loop error: %s; applying failsafe duty", e)
            try:
                write_duty(fan1_path, failsafe_duty, min_duty, max_duty)
                write_duty(fan2_path, failsafe_duty, min_duty, max_duty)
            except Exception:
                logging.exception("failed to write failsafe duty")

        time.sleep(poll_sec)

    logging.info("shutdown requested, exit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
