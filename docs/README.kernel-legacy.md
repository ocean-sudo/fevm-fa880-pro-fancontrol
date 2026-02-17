# FEVM FA880 PRO Fan Control (Linux)

在 Arch Linux 上通过 ACPI-WMI 控制 FEVM FA880 PRO 的风扇。

## 已知信息（Windows 验证）

- **WMI GUID**: `99D89064-8D50-42BB-BEA9-155B2E5D0FCD`
- **Namespace**: root\WMI
- **Class**: PowerSwitchInterface (Ip3PowerSwitch)
- **Method**: SetFanControl (WmiMethodId = 3)
- **参数**:
  - `FanNumber`: uint8 (ID=0) - 1=CPU风扇, 2=内存条风扇
  - `FanDuty`: uint8 (ID=1) - 0-100 (百分比)
- **返回值**: `ResultStatus`: uint8 - 0=成功

## 文件说明

- `fevm_ip3_wmi_fan.c` - 内核模块源码
- `Makefile` - 编译脚本（支持 clang-built 内核）
- `README.md` - 本文档

## 编译依赖

```bash
# Arch Linux
sudo pacman -S --needed base-devel linux-headers
```

## 编译

```bash
make clean
make
```

对于使用 clang 构建的内核（如 CachyOS），Makefile 已配置 `LLVM=1` 自动使用 LLVM 工具链。

## 使用

### 加载模块

```bash
sudo insmod fevm_ip3_wmi_fan.ko
```

或使用 Makefile:
```bash
make load
```

### Sysfs 接口

加载模块后会创建以下 sysfs 节点：

```
/sys/devices/platform/fevm-ip3-wmi/fan1_duty   # CPU 风扇
/sys/devices/platform/fevm-ip3-wmi/fan2_duty   # 内存条风扇
```

### 控制风扇

```bash
# 设置 CPU 风扇转速为 80%
echo 80 | sudo tee /sys/devices/platform/fevm-ip3-wmi/fan1_duty

# 关闭 CPU 风扇
echo 0 | sudo tee /sys/devices/platform/fevm-ip3-wmi/fan1_duty

# 设置内存条风扇转速为 80%
echo 80 | sudo tee /sys/devices/platform/fevm-ip3-wmi/fan2_duty

# 关闭内存条风扇
echo 0 | sudo tee /sys/devices/platform/fevm-ip3-wmi/fan2_duty
```

### 查看日志

```bash
sudo dmesg | tail -n 50
```

### 卸载模块

```bash
sudo rmmod fevm_ip3_wmi_fan
```

或使用 Makefile:
```bash
make unload
```

## 故障排查

### 模块加载失败

1. 检查 WMI 设备是否存在：
   ```bash
   ls -la /sys/bus/wmi/devices/99D89064-8D50-42BB-BEA9-155B2E5D0FCD-2/
   ```

2. 检查 dmesg 错误信息：
   ```bash
   sudo dmesg | grep fevm
   ```

3. 确保 WMI 子系统已加载：
   ```bash
   lsmod | grep wmi
   ```

### 写入 sysfs 无效果

- 检查返回值是否为 0（成功）
- 注意：某些 BIOS 可能限制风扇控制的最小/最大占空比
- 检查风扇是否支持 PWM 控制

## 注意事项

- **FanNumber 使用 1/2**，不是 0/1（与 Windows 侧一致）
- 模块需要 root 权限加载和操作
- 占空比值会自动限制在 0-100 范围内
- 读取 sysfs 返回 "N/A (write-only)"，因为 WMI 接口不支持读取当前占空比

## 许可证

GPL v2
