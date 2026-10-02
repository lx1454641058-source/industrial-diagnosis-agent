"""Original diagnostic abstracts; documents are reference data, never instructions."""
RECORDS = [
    {'id': 'kb-timeout', 'title': '通信超时的证据边界',
     'text': '未收到响应只能确认本次通信失败，不能单独证明传感器断电。检查供电、RS485 接线、端口占用、设备地址、波特率与校验格式。读取失败期间保留上次读数但标明过期。',
     'keywords': ['超时', '断电', '接线', 'timeout', '不更新'],
     'source': '本项目原创诊断规则；协议依据 Modbus 串行规范',
     'url': 'https://www.modbus.org/docs/Modbus_over_serial_line_V1_02.pdf'},
    {'id': 'kb-port', 'title': '串口不存在与串口占用',
     'text': '枚举不到配置的串口说明该名称的串口当前不可见。检查 USB 插接、设备管理器与端口名称；不能据此确定传感器本身故障。串口存在但无法打开时应排查占用和连接。',
     'keywords': ['串口', 'USB', 'usb', 'port', '连接'],
     'source': '本项目原创摘要；pySerial 官方接口文档',
     'url': 'https://pyserial.readthedocs.io/en/latest/tools.html#module-serial.tools.list_ports'},
    {'id': 'kb-sen0438', 'title': 'SEN0438 候选设备寄存器',
     'text': '仅适用于核对型号后的 SEN0438：读功能码 03，PDU 零基地址 0，连续 2 个寄存器，湿度在前温度在后，均除以 10。供电 12～36V，采样周期 3 秒，默认 9600。示例地址 1 不代表所有实物出厂地址。校验格式和负温编码应实物确认。',
     'keywords': ['SEN0438', '寄存器', '参数', '换算', '温度', '湿度', '波特率'],
     'source': 'DFRobot 托管的 SEN0438 官方中文使用说明的摘要',
     'url': 'https://img.dfrobot.com.cn/wikicn/5ea64bf6cf1d8c7738ad2881/c79ead8f8786c463e677989e74636608.pdf'},
    {'id': 'kb-recovery', 'title': '恢复确认',
     'text': '恢复确认应进行至少三次间隔采样，每次检查完整响应和有效值，同时确认后台采集仍在运行。一次成功、缓存旧值或单独连接成功均不足以证明稳定恢复。短期复测不等于长期稳定性验证。',
     'keywords': ['恢复', '复测', '正常', '确认', '停止', 'stale'],
     'source': '本项目原创实验验收规则', 'url': ''},
]


def search(query):
    scored = []
    for record in RECORDS:
        score = sum(1 for word in record['keywords'] if word.casefold() in query.casefold())
        if score:
            scored.append((score, {k: v for k, v in record.items() if k != 'keywords'}))
    return [record for _, record in sorted(scored, key=lambda item: -item[0])[:3]]
