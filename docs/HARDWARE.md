# Hardware Facts

## Device Scope
- Product: FEVM FA880 PRO
- OS: Linux (tested target: Arch-based distros)

## WMI Interface (validated from Windows-side behavior)
- WMI GUID: `99D89064-8D50-42BB-BEA9-155B2E5D0FCD`
- Namespace: `root\\WMI`
- Class: `PowerSwitchInterface` (`Ip3PowerSwitch`)
- Method: `SetFanControl`
- Method ID: `3`

## Method Contract
- Input:
- `FanNumber` (`uint8`): `1` = CPU fan, `2` = memory fan
- `FanDuty` (`uint8`): `0..100`
- Output:
- `ResultStatus` (`uint8`): `0` means success

## Linux Sysfs exposed by this driver
- `/sys/devices/platform/fevm-ip3-wmi/fan1_duty`
- `/sys/devices/platform/fevm-ip3-wmi/fan2_duty`

## Notes
- This WMI method is write-oriented. Current duty readback is not available.
- BIOS/EC may still clamp or reshape effective duty silently.
