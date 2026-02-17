# FEVM FA880 PRO Fan Control

给 FEVM FA880 PRO 的 Linux 风扇控制项目，分为两层：
- `kernel/`：通过 ACPI-WMI 暴露 sysfs 写接口
- `userspace/`：按温度曲线动态写入占空比（先用 Python，Rust 原型已提供）

## 仓库结构

```text
kernel/
  fevm_ip3_wmi_fan.c
  Kconfig
  Makefile
  dkms.conf
  build-artifacts/        # 可选：本地历史编译产物快照（默认忽略）
userspace/
  fevm-fan-curve.py
  fevm-fan-curve.service
  config.example.toml
  rust/
    fevm-fan-curve-rs/
      Cargo.toml
      src/main.rs
docs/
  HARDWARE.md
  SAFETY.md
  README.kernel-legacy.md
LICENSES/
  GPL-2.0-only.txt
  MIT.txt
README.md
```

## 1. 前置条件

```bash
# Arch / CachyOS
sudo pacman -S --needed base-devel linux-headers python

# 如果你在 Python 3.10 且要读 TOML 配置
sudo pacman -S --needed python-tomli
```

## 2. 编译并加载内核模块

```bash
make -C kernel
sudo insmod kernel/fevm_ip3_wmi_fan.ko
```

验证 sysfs 节点：

```bash
ls -l /sys/devices/platform/fevm-ip3-wmi/
# 期待看到 fan1_duty fan2_duty
```

手动测试写入：

```bash
echo 60 | sudo tee /sys/devices/platform/fevm-ip3-wmi/fan1_duty
echo 60 | sudo tee /sys/devices/platform/fevm-ip3-wmi/fan2_duty
```

## 3. 安装 Python 曲线服务

```bash
sudo install -Dm755 userspace/fevm-fan-curve.py /usr/local/sbin/fevm-fan-curve.py
sudo install -Dm644 userspace/config.example.toml /etc/fevm-fan-curve.toml
sudo install -Dm644 userspace/fevm-fan-curve.service /etc/systemd/system/fevm-fan-curve.service
sudo systemctl daemon-reload
sudo systemctl enable --now fevm-fan-curve.service
```

查看运行状态：

```bash
systemctl status fevm-fan-curve.service
journalctl -u fevm-fan-curve.service -f
```

## 4. 调曲线

编辑 `/etc/fevm-fan-curve.toml`：

```toml
[general]
poll_sec = 1.0
min_duty = 20
max_duty = 100
failsafe_duty = 70

[sensors]
cpu_names = ["k10temp"]
mem_names = ["spd5118"]
mem_fallback_to_cpu = true

[curves]
cpu = [[40, 20], [55, 35], [65, 55], [75, 75], [85, 100]]
mem = [[35, 20], [50, 40], [60, 60], [70, 80], [80, 100]]
```

修改后重启服务：

```bash
sudo systemctl restart fevm-fan-curve.service
```

## 5. 停用与卸载

```bash
sudo systemctl disable --now fevm-fan-curve.service
sudo rm -f /etc/systemd/system/fevm-fan-curve.service
sudo rm -f /usr/local/sbin/fevm-fan-curve.py
sudo rm -f /etc/fevm-fan-curve.toml
sudo systemctl daemon-reload

sudo rmmod fevm_ip3_wmi_fan
```

## Rust 路线（后续切换）

当前生产建议仍用 Python；Rust 版本在：

- `userspace/rust/fevm-fan-curve-rs`

本地验证：

```bash
cargo check --manifest-path userspace/rust/fevm-fan-curve-rs/Cargo.toml
```

等 Rust 版在你机器长期跑稳后，把 systemd `ExecStart` 改成 Rust 可执行文件即可。

## DKMS（可选）

`kernel/dkms.conf` 已给出模板，你可以按发行版习惯接入打包流程。

## 许可证

- `kernel/*`：GPL-2.0-only
- `userspace/*`、`docs/*`：MIT

见 `LICENSES/GPL-2.0-only.txt` 与 `LICENSES/MIT.txt`。
