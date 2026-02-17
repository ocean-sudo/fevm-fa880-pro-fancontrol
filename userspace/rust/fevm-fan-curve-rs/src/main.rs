use serde::Deserialize;
use std::env;
use std::fs;
use std::io;
use std::path::Path;
use std::thread;
use std::time::Duration;

type Curve = Vec<(f64, i32)>;

#[derive(Debug, Deserialize, Default)]
struct FileConfig {
    #[serde(default)]
    general: General,
    #[serde(default)]
    sensors: Sensors,
    #[serde(default)]
    curves: Curves,
}

#[derive(Debug, Deserialize)]
struct General {
    fan1_path: Option<String>,
    fan2_path: Option<String>,
    poll_sec: Option<f64>,
    min_duty: Option<i32>,
    max_duty: Option<i32>,
    failsafe_duty: Option<i32>,
}

impl Default for General {
    fn default() -> Self {
        Self {
            fan1_path: None,
            fan2_path: None,
            poll_sec: None,
            min_duty: None,
            max_duty: None,
            failsafe_duty: None,
        }
    }
}

#[derive(Debug, Deserialize)]
struct Sensors {
    cpu_names: Option<Vec<String>>,
    mem_names: Option<Vec<String>>,
    mem_fallback_to_cpu: Option<bool>,
}

impl Default for Sensors {
    fn default() -> Self {
        Self {
            cpu_names: None,
            mem_names: None,
            mem_fallback_to_cpu: None,
        }
    }
}

#[derive(Debug, Deserialize)]
struct Curves {
    cpu: Option<Vec<(f64, i32)>>,
    mem: Option<Vec<(f64, i32)>>,
}

impl Default for Curves {
    fn default() -> Self {
        Self { cpu: None, mem: None }
    }
}

#[derive(Debug)]
struct Config {
    fan1_path: String,
    fan2_path: String,
    poll_sec: f64,
    min_duty: i32,
    max_duty: i32,
    failsafe_duty: i32,
    cpu_sensor_names: Vec<String>,
    mem_sensor_names: Vec<String>,
    mem_fallback_to_cpu: bool,
    cpu_curve: Curve,
    mem_curve: Curve,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            fan1_path: "/sys/devices/platform/fevm-ip3-wmi/fan1_duty".to_string(),
            fan2_path: "/sys/devices/platform/fevm-ip3-wmi/fan2_duty".to_string(),
            poll_sec: 1.0,
            min_duty: 20,
            max_duty: 100,
            failsafe_duty: 70,
            cpu_sensor_names: vec!["k10temp".to_string()],
            mem_sensor_names: vec!["spd5118".to_string()],
            mem_fallback_to_cpu: true,
            cpu_curve: vec![(40.0, 20), (55.0, 35), (65.0, 55), (75.0, 75), (85.0, 100)],
            mem_curve: vec![(35.0, 20), (50.0, 40), (60.0, 60), (70.0, 80), (80.0, 100)],
        }
    }
}

fn load_config(path: &str) -> Result<Config, Box<dyn std::error::Error>> {
    let mut cfg = Config::default();
    if !Path::new(path).exists() {
        return Ok(cfg);
    }

    let raw = fs::read_to_string(path)?;
    let file_cfg: FileConfig = toml::from_str(&raw)?;

    if let Some(v) = file_cfg.general.fan1_path {
        cfg.fan1_path = v;
    }
    if let Some(v) = file_cfg.general.fan2_path {
        cfg.fan2_path = v;
    }
    if let Some(v) = file_cfg.general.poll_sec {
        cfg.poll_sec = v;
    }
    if let Some(v) = file_cfg.general.min_duty {
        cfg.min_duty = v;
    }
    if let Some(v) = file_cfg.general.max_duty {
        cfg.max_duty = v;
    }
    if let Some(v) = file_cfg.general.failsafe_duty {
        cfg.failsafe_duty = v;
    }

    if let Some(v) = file_cfg.sensors.cpu_names {
        cfg.cpu_sensor_names = v;
    }
    if let Some(v) = file_cfg.sensors.mem_names {
        cfg.mem_sensor_names = v;
    }
    if let Some(v) = file_cfg.sensors.mem_fallback_to_cpu {
        cfg.mem_fallback_to_cpu = v;
    }

    if let Some(v) = file_cfg.curves.cpu {
        cfg.cpu_curve = v;
    }
    if let Some(v) = file_cfg.curves.mem {
        cfg.mem_curve = v;
    }

    Ok(cfg)
}

fn find_hwmons_by_name(name: &str) -> Vec<String> {
    let mut out = Vec::new();
    if let Ok(entries) = fs::read_dir("/sys/class/hwmon") {
        for entry in entries.flatten() {
            let p = entry.path();
            let name_file = p.join("name");
            if let Ok(actual) = fs::read_to_string(name_file) {
                if actual.trim() == name {
                    out.push(p.to_string_lossy().to_string());
                }
            }
        }
    }
    out
}

fn resolve_hwmons(names: &[String]) -> Vec<String> {
    let mut out = Vec::new();
    for name in names {
        for hw in find_hwmons_by_name(name) {
            if !out.contains(&hw) {
                out.push(hw);
            }
        }
    }
    out
}

fn read_temp_millic(path: &Path) -> io::Result<f64> {
    let raw = fs::read_to_string(path)?;
    let v: i32 = raw.trim().parse().map_err(|_| io::ErrorKind::InvalidData)?;
    Ok(v as f64 / 1000.0)
}

fn max_temp_in_hwmons(hwmons: &[String]) -> Result<f64, Box<dyn std::error::Error>> {
    let mut temps: Vec<f64> = Vec::new();
    for hw in hwmons {
        for entry in fs::read_dir(hw)? {
            let entry = entry?;
            let name = entry.file_name();
            let name = name.to_string_lossy();
            if name.starts_with("temp") && name.ends_with("_input") {
                if let Ok(v) = read_temp_millic(&entry.path()) {
                    temps.push(v);
                }
            }
        }
    }

    temps
        .into_iter()
        .reduce(f64::max)
        .ok_or_else(|| "no temp*_input found".into())
}

fn lerp_curve(temp_c: f64, curve: &Curve) -> i32 {
    if temp_c <= curve[0].0 {
        return curve[0].1;
    }
    if temp_c >= curve[curve.len() - 1].0 {
        return curve[curve.len() - 1].1;
    }

    for w in curve.windows(2) {
        let (t0, d0) = w[0];
        let (t1, d1) = w[1];
        if temp_c >= t0 && temp_c <= t1 {
            let ratio = (temp_c - t0) / (t1 - t0);
            return (d0 as f64 + ratio * (d1 - d0) as f64).round() as i32;
        }
    }

    curve[curve.len() - 1].1
}

fn clamp_duty(duty: i32, min_duty: i32, max_duty: i32) -> i32 {
    duty.clamp(min_duty, max_duty)
}

fn write_duty(path: &str, duty: i32, min_duty: i32, max_duty: i32) -> io::Result<()> {
    fs::write(path, clamp_duty(duty, min_duty, max_duty).to_string())
}

fn config_path_from_args() -> String {
    let args: Vec<String> = env::args().collect();
    let mut idx = 1usize;
    while idx < args.len() {
        if args[idx] == "--config" && idx + 1 < args.len() {
            return args[idx + 1].clone();
        }
        idx += 1;
    }
    "/etc/fevm-fan-curve.toml".to_string()
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let config_path = config_path_from_args();
    let cfg = load_config(&config_path)?;

    let cpu_hwmons = resolve_hwmons(&cfg.cpu_sensor_names);
    if cpu_hwmons.is_empty() {
        return Err(format!("CPU hwmon not found: {:?}", cfg.cpu_sensor_names).into());
    }

    let mut mem_hwmons = resolve_hwmons(&cfg.mem_sensor_names);
    if mem_hwmons.is_empty() {
        if cfg.mem_fallback_to_cpu {
            mem_hwmons = cpu_hwmons.clone();
            eprintln!("mem hwmon not found, fallback to CPU");
        } else {
            return Err(format!("MEM hwmon not found: {:?}", cfg.mem_sensor_names).into());
        }
    }

    eprintln!("cpu_hwmons={:?} mem_hwmons={:?}", cpu_hwmons, mem_hwmons);

    loop {
        let result: Result<(), Box<dyn std::error::Error>> = (|| {
            let cpu_t = max_temp_in_hwmons(&cpu_hwmons)?;
            let mem_t = max_temp_in_hwmons(&mem_hwmons)?;
            let cpu_duty = lerp_curve(cpu_t, &cfg.cpu_curve);
            let mem_duty = lerp_curve(mem_t, &cfg.mem_curve);
            write_duty(&cfg.fan1_path, cpu_duty, cfg.min_duty, cfg.max_duty)?;
            write_duty(&cfg.fan2_path, mem_duty, cfg.min_duty, cfg.max_duty)?;
            Ok(())
        })();

        if let Err(e) = result {
            eprintln!("loop error: {e}; applying failsafe");
            let _ = write_duty(&cfg.fan1_path, cfg.failsafe_duty, cfg.min_duty, cfg.max_duty);
            let _ = write_duty(&cfg.fan2_path, cfg.failsafe_duty, cfg.min_duty, cfg.max_duty);
        }

        thread::sleep(Duration::from_secs_f64(cfg.poll_sec));
    }
}
