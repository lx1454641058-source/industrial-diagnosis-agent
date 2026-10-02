"""Original read-only Modbus RTU codec; see docs/SOURCES.md for protocol sources."""
from dataclasses import asdict, dataclass
import math
import struct


class AcquisitionError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Profile:
    name: str = '演示映射（不代表真实设备）'
    port: str = 'DEMO'
    baudrate: int = 9600
    parity: str = 'N'
    stopbits: int = 1
    unit: int = 1
    function: int = 3
    address: int = 0
    count: int = 2
    temperature_offset: int = 0
    humidity_offset: int = 1
    temperature_scale: float = 0.1
    humidity_scale: float = 0.1
    temperature_signed: bool = True
    timeout: float = 0.6
    interval: float = 2.0
    stale_after: float = 8.0
    hardware_confirmed: bool = False
    source: str = 'demo-only'

    def validate(self):
        ints = ['baudrate', 'stopbits', 'unit', 'function', 'address', 'count',
                'temperature_offset', 'humidity_offset']
        if any(type(getattr(self, x)) is not int for x in ints):
            raise ValueError('整数字段类型不正确')
        if not isinstance(self.port, str) or not self.port or len(self.port) > 128:
            raise ValueError('端口名称无效')
        if self.baudrate not in [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]:
            raise ValueError('不支持的波特率')
        if self.parity not in ['N', 'E', 'O'] or self.stopbits not in [1, 2]:
            raise ValueError('串口格式无效')
        if not (1 <= self.unit <= 247 and self.function in [3, 4]):
            raise ValueError('只允许读取功能码 3/4 和单播地址 1～247')
        if not (0 <= self.address <= 65535 and 1 <= self.count <= 32
                and self.address + self.count <= 65536):
            raise ValueError('寄存器范围无效')
        if not all(0 <= x < self.count for x in [self.temperature_offset, self.humidity_offset]):
            raise ValueError('数据偏移超出寄存器范围')
        for field, low, high in [('timeout', .05, 3), ('interval', .5, 60),
                                 ('stale_after', 1, 300),
                                 ('temperature_scale', .0001, 100), ('humidity_scale', .0001, 100)]:
            value = getattr(self, field)
            if type(value) not in [int, float] or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f'{field} 超出允许范围')
        if type(self.hardware_confirmed) is not bool or type(self.temperature_signed) is not bool:
            raise ValueError('确认状态和符号设置必须是布尔值')
        if self.stale_after < self.interval + self.timeout:
            raise ValueError('失效时间应大于采集周期加超时')
        return self

    def public(self):
        return asdict(self)


def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def with_crc(data):
    return data + struct.pack('<H', crc16(data))


def request_frame(profile):
    profile.validate()
    return with_crc(struct.pack('>BBHH', profile.unit, profile.function, profile.address, profile.count))


def parse_response(frame, profile):
    if not frame:
        raise AcquisitionError('timeout', '没有收到响应，供电、接线、地址和参数均需排查')
    if len(frame) < 5:
        raise AcquisitionError('short_frame', '响应帧不完整')
    if crc16(frame[:-2]) != int.from_bytes(frame[-2:], 'little'):
        raise AcquisitionError('crc_error', '响应校验失败，可能存在通信干扰或格式问题')
    if frame[0] != profile.unit:
        raise AcquisitionError('address_error', '响应设备地址与请求不一致')
    if frame[1] == (profile.function | 0x80):
        if len(frame) != 5:
            raise AcquisitionError('length_error', '异常响应长度不正确')
        raise AcquisitionError('modbus_exception', f'设备返回 Modbus 异常码 {frame[2]}')
    if frame[1] != profile.function:
        raise AcquisitionError('function_error', '响应功能码与请求不一致')
    if frame[2] != profile.count * 2 or len(frame) != 5 + profile.count * 2:
        raise AcquisitionError('length_error', '寄存器数量或响应长度不正确')
    registers = list(struct.unpack('>' + 'H' * profile.count, frame[3:-2]))
    temp_raw = registers[profile.temperature_offset]
    if profile.temperature_signed and temp_raw >= 32768:
        temp_raw -= 65536
    temperature = round(temp_raw * profile.temperature_scale, 4)
    humidity = round(registers[profile.humidity_offset] * profile.humidity_scale, 4)
    if not (-100 <= temperature <= 200 and 0 <= humidity <= 100):
        raise AcquisitionError('value_error', '换算结果越界，应核对寄存器映射、缩放及传感器状态')
    return {'temperature': temperature, 'humidity': humidity, 'registers': registers}
