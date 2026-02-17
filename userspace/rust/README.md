# Rust 路线（预备）

`userspace/rust/fevm-fan-curve-rs` 是与 Python 版本同逻辑的原型实现，目的是后续替换时可直接对照行为。

当前建议：
- 生产先用 `userspace/fevm-fan-curve.py`
- 在你的机器上验证 Rust 版本后，再切换 systemd `ExecStart`
