# 本机智能体运行说明

本方案将模型推理放在现有电脑上，不购买服务器、不订阅云服务。模型与设备数据在本机处理；下载官方运行时和模型时需要联网。

## 本次环境

- Ollama 0.34.2 官方 Windows 便携发行包。
- 运行目录：`D:\codex-runtime\industrial-diagnosis\ollama-0.34.2`。
- 模型目录：`D:\codex-runtime\industrial-diagnosis\models`。
- 专用接口：`http://127.0.0.1:11435`，仅本机访问。
- 候选模型：`qwen3:4b`，约 2.5 GB，Q4_K_M。实际下载、推理与评测状态以实验记录为准。
- 当前电脑检查到 RTX 4080 Laptop GPU 12 GB 显存、约 32 GB 内存。该硬件是现有资源，不计入传感器采购预算。
- 未创建系统服务、开机启动或云账户；未调用收费 API。模型仍消耗本机存储、显存和电力。

## 使用

在项目目录运行：

```powershell
.\start-local-model.ps1
.\run.ps1 -Provider ollama -Model qwen3:4b -ModelUrl http://127.0.0.1:11435 -Port 8767
```

打开 `http://127.0.0.1:8767/`。模拟设备用于开发验证；真实串口需要另外提供核对过的配置。

模型默认关闭思考输出，温度参数为 0，上下文配置 16384，单次输出上限 1800 token。模型调用最多七轮、工具调用最多十六次，采用 180 秒协作式预算。调用失败会明确显示失败，不以规则答案冒充模型输出。

生成式模型可能误解工具记录。工具直接记录与模型解读分开展示，引用编号有效不等于语义正确；恢复状态由程序校验。即使模型声称已恢复，也不能覆盖系统的复测状态。

## 来源和许可证

- [Ollama v0.34.2 官方发行页](https://github.com/ollama/ollama/releases/tag/v0.34.2)。ZIP 的 SHA256 已核对：`8f3fd071a2a2f9497b562f43502c77c2b701a99d1ee5dfda28da8c786373063b`。
- [Ollama v0.34.2 LICENSE](https://github.com/ollama/ollama/blob/v0.34.2/LICENSE)：核心项目为 MIT；捆绑运行组件保留各自声明。本次本地使用，不制作第三方运行时再分发包。
- [Ollama Qwen3 4B 模型页](https://ollama.com/library/qwen3:4b)。
- [Qwen3-4B 原始权重 LICENSE](https://huggingface.co/Qwen/Qwen3-4B/blob/main/LICENSE)：Apache-2.0。原始权重许可与本项目原创代码许可分开，不给项目擅自指定许可证。
- [Ollama FAQ](https://docs.ollama.com/faq)：模型目录、监听地址、并发和关闭云功能等运行选项。

官方运行时及模型文件放在 D 盘，均不放进项目 Git 提交。运行时来源与散列记录在 D 盘 `runtime-manifest.json`。正式发布或另行打包前，应重新核对全部随附许可及署名要求。
