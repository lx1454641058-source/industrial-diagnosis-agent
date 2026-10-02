# 工业数据采集故障排查智能体

本项目用于毕业设计，目标是低成本真实传感器采集与智能体辅助故障排查。当前软件提供真实串口接口、模拟设备、诊断工具、证据存储和本地网页。真实硬件与实际大模型效果尚待独立验收。

原始实现，无复制的第三方界面或图像。未给项目擅自指定许可证，第三方依赖来源见 `docs/SOURCES.md`。

## 启动演示

在本目录打开 PowerShell：

```powershell
.\run.ps1
```

浏览器访问 http://127.0.0.1:8766/ 。保持终端运行，按 Ctrl+C 退出。

演示默认不需要第三方包，不联网调用模型。页面明确显示“模拟设备”和“规则基线”。规则基线按固定诊断顺序检查，不理解任意自然语言，不能作为智能体效果证明。

也可以使用自己的 Python 3.10 或更高版本：

```powershell
python -m diagnosis.server --mode demo --provider baseline
```

## 软件结构

- `diagnosis/protocol.py`：只读 Modbus RTU 编解码、CRC 校验、寄存器换算。
- `diagnosis/acquisition.py`：真实串口与模拟后端、采集线程、数据有效性。
- `diagnosis/storage.py`：本地 SQLite 数据与诊断记录，不上传。
- `diagnosis/tools.py`：允许列表中的诊断工具，校验调用参数。
- `diagnosis/agent.py`：有次数和时间边界的模型工具调用循环、规则基线。
- `diagnosis/knowledge.py`：带来源的原创参考摘要，不复制整份设备手册。
- `diagnosis/server.py` 与 `static/`：本机服务、趋势图、故障实验、报告下载。
- `configs/sen0438.example.json`：候选传感器映射，未确认项保留待核验。
- `tests/`：协议、采集、证据、模型契约及 HTTP 集成检查。

## 接入真实硬件

1. 阅读 `docs/HARDWARE.md`，核对实际设备型号、供电和接线。
2. 执行 `setup.ps1`，只安装 BSD-3-Clause 的 pyserial 3.5 到 `.runtime`，不改系统环境。
3. 将候选配置复制到 `work/device.json`，核对串口、设备地址、格式、寄存器及负温处理。只有核对完毕才能将 `hardware_confirmed` 设为 `true`。
4. 启动：

```powershell
.\run.ps1 -Mode serial -Profile work/device.json
```

当前只发送功能码 03/04 的单播读取请求，不修改设备寄存器。真实模式禁止故障模拟按钮。模拟与真实模式按配置分目录存储，避免混用历史记录。

参数比对需要独立核对的参考记录，可用 `-ReferenceProfile work/verified-reference.json` 指定。没有参考时会明确显示“无法比较”，不会将当前配置与自己比较后认定正确。参考记录也不能替代读取或人工核查实物拨码设置。

## 接入本地大模型

接口按 Ollama 官方工具调用协议实现。本机专用 Ollama 0.34.2 已部署到 D 盘项目运行时目录；Qwen3 4B 下载及验证状态见进度记录。服务仅绑定本机 11435，未创建开机启动项或系统服务，未调用收费 API。

专用服务和模型准备完成后：

```powershell
.\start-local-model.ps1
.\run.ps1 -Provider ollama -Model 'qwen3:4b' -ModelUrl 'http://127.0.0.1:11435' -Port 8767
```

也可连接用户已有的本机服务（默认端口 11434）：

```powershell
.\run.ps1 -Provider ollama -Model '填写实际已安装的模型名'
```

真实串口和模型可同时开启：

```powershell
.\run.ps1 -Mode serial -Profile work/device.json -Provider ollama -Model '填写实际已安装的模型名'
```

模型不可用、格式错误或引用不存在的证据时，诊断标记失败，不偷偷切换为规则答案。工具返回消息保留在会话中供模型选择后续动作。最终报告必须带证据编号；引用存在不等于推理一定正确，仍需人工标注的模型评测。

页面分开展示“工具直接记录”和“模型解读”。`completed` 仅表示本轮调用结束；`interpretation_verified=false` 表示模型文字尚未经人工核验。恢复标记由系统依据复测结果计算。180 秒为协作式执行预算：每次模型或工具调用检查剩余时间；OS 串口调用自身依靠串口超时，不能保证硬实时截止。

## 验证与演示边界

```powershell
python -m unittest discover -s tests -v
```

测试里的脚本模型仅检查接口契约与工具循环，不是大模型能力测试。模拟故障只证明软件流程，不证明真实硬件已调通。短期三次复测不等于长期稳定性。

网页使用系统字体和原创绘图，不依赖 CDN。报告下载为 JSON，含问题、数据来源、工具轨迹、证据引用及状态，可用于后续实验分析。

继续开发与待验收内容见 `work/supervisor-state.md`。本项目不修改父目录的无人机项目。
