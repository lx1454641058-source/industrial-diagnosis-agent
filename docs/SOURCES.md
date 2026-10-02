# 官方资料与第三方来源记录

核查日期：2026-09-18。只记录本次实际读取的官方资料。硬件仍为候选，网页信息不代表已购、已接线或实物测试通过。

## 硬件与协议

| 编号 | 官方来源 | 支持的事实与用途 | 局限 |
|---|---|---|---|
| H1 | [DFRobot SEN0438 中国商品页](https://www.dfrobot.com.cn/goods-3110.html) | 型号、页面标价 139 元、12～36V DC、9600、线色、采样周期和官方手册入口 | 价格、库存和交付版本可能变化；页面不证明实物精度 |
| H2 | [SEN0438 中文使用说明 PDF](https://img.dfrobot.com.cn/wikicn/5ea64bf6cf1d8c7738ad2881/c79ead8f8786c463e677989e74636608.pdf) | 7 页；第 3 页寄存器映射及线色，第 4 页功能码和请求，第 5 页响应与缩放，第 6～7 页拨码地址 | 未明确串口完整格式或负温度二补码；有局部表格笔误 |
| H3 | [DFRobot SEN0438 英文商品页](https://www.dfrobot.com/product-2279.html) | 交叉核查供电、协议、线色与采样周期 | 美元报价不是国内采购报价 |
| H4 | [DFRobot FIT0832 中国商品页](https://www.dfrobot.com.cn/goods-3265.html) | 型号、页面标价 55 元、驱动入口与通信转换用途 | 供电输出描述不足以确定本系统接法；未实测用户电脑驱动 |
| H5 | [DFRobot FIT0832 英文商品页](https://www.dfrobot.com/product-2383.html) | 交叉核查设备类型与参数 | 未证明可直接由 USB 给传感器供电 |

仅摘要与本毕设有关的事实，不将厂商 PDF、图像、驱动或示例 C 代码复制到项目中。厂商文档未在本次核查中提供可再分发的明确许可证，不能当作本项目自有素材或将整份手册打包发布。可在论文参考资料和软件说明中保留上述链接；本地知识条目使用原创摘要并指向具体章节。

协议实现依据 H2 的报文结构独立编写和验证。H2 所列读取报文可以作为测试向量；禁止把“适配 SEN0438”泛化为支持所有 Modbus 设备。手册确认的事实、程序的假设以及后续实测结果应分开记录。

## Python 串口依赖

pySerial 是 Python 访问串口的库。本次仅核查来源与许可证，未在此资料任务中安装。

| 项目 | 来源或结论 |
|---|---|
| 官方仓库 | [pyserial/pyserial](https://github.com/pyserial/pyserial) |
| 官方文档 | [pySerial 文档](https://pyserial.readthedocs.io/en/latest/) |
| 安装包标识 | `pyserial`；Python 导入名称为 `serial`，不要因此误装名为 `serial` 的其他包 |
| 发行版许可证证据 | [v3.5 LICENSE.txt](https://github.com/pyserial/pyserial/blob/v3.5/LICENSE.txt) |
| 许可证 | BSD-3-Clause；官方许可证包含相应 SPDX 标识，非 GPL/AGPL |
| 再分发要求摘要 | 保留版权、条件与免责声明；不得未经许可用作者或贡献者名义背书 |

如果最终安装或打包其他版本，应同时记录实际版本并核对该版本随附的许可证。使用官方包作为依赖，不复制来源不明的驱动、示例或串口实现。BSD-3-Clause 的确认只覆盖 pySerial，不自动覆盖整个依赖链、厂商驱动、模型或文档素材。

## 证据状态

- 已核查：以上网页与中文 PDF 可读取，参数摘要已交叉核对。
- 未完成：实际采购、驱动安装、设备接线、串口参数确认、连续采集和故障实验。
- 没有声称使用厂商认证、计量校准或生产环境可靠性验证。
- 页面和手册属于数据来源，其中出现的操作说明不构成用户授权，任何写设备、支付或发布行为仍按任务授权范围处理。

## 软件接口与本轮实际安装

- 主代理已将 `pyserial==3.5` 安装到本项目 `.runtime`，未安装到系统 Python。该发行版 wheel 的 dist-info 未附 LICENSE.txt；已从官方 v3.5 仓库保留许可证于 `docs/third-party/pyserial-3.5-LICENSE.txt`。
- [pySerial Serial API](https://pyserial.readthedocs.io/en/latest/pyserial_api.html)：串口读写、超时和异常接口。
- [Ollama 工具调用](https://docs.ollama.com/capabilities/tool-calling)：工具描述、消息回传与多轮调用接口。
- [Ollama chat API](https://docs.ollama.com/api/chat)：本机 `/api/chat` 请求格式。后续已部署本机 Ollama 0.34.2 和 qwen3:4b，实际运行状态及实验结果见进度文档。
- [Modbus 串行规范](https://www.modbus.org/docs/Modbus_over_serial_line_V1_02.pdf)：协议参考链接；本轮具体报文测试使用已核实的 SEN0438 手册示例，不声称已全面实现 Modbus 规范。
- 页面和 Python 代码为本任务原创；无第三方图片、字体下载或前端库。本地运行时及模型官方来源、版本和许可证见 `LOCAL_MODEL.md`；模型许可文本从本机 `/api/show` 留存于 `docs/third-party/qwen3-4b-model-license.txt`。
