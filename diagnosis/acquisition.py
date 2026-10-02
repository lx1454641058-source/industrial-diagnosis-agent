"""Original acquisition backends. Simulation metadata never enters agent tools."""
import math
import threading
import time

from .protocol import AcquisitionError, parse_response, request_frame, with_crc


class DemoBackend:
    source = 'simulation'
    scenarios = ('normal', 'usb_missing', 'timeout', 'crc_error', 'parameter_mismatch', 'invalid_value')

    def __init__(self, profile):
        self.profile = profile
        self.scenario = 'normal'
        self.ticks = 0

    def ports(self):
        return [] if self.scenario == 'usb_missing' else [{'device': self.profile.port, 'description': '虚拟 RS485 转换器（模拟）'}]

    def config(self):
        current = self.profile.public()
        if self.scenario == 'parameter_mismatch':
            current['baudrate'] = 19200 if self.profile.baudrate != 19200 else 9600
        return current

    def transact(self):
        self.ticks += 1
        if self.scenario == 'usb_missing':
            raise AcquisitionError('port_missing', '配置的串口未出现在枚举结果中')
        if self.scenario in ['timeout', 'parameter_mismatch']:
            return b''
        registers = [0] * self.profile.count
        temperature = 25 + math.sin(self.ticks / 5)
        humidity = 52 + math.cos(self.ticks / 7) * 3
        if self.scenario == 'invalid_value': humidity = 120
        registers[self.profile.temperature_offset] = round(temperature / self.profile.temperature_scale) & 0xFFFF
        registers[self.profile.humidity_offset] = round(humidity / self.profile.humidity_scale)
        payload = bytes([self.profile.unit, self.profile.function, self.profile.count * 2])
        payload += b''.join(x.to_bytes(2, 'big') for x in registers)
        frame = with_crc(payload)
        return frame[:-1] + bytes([frame[-1] ^ 1]) if self.scenario == 'crc_error' else frame


class SerialBackend:
    source = 'hardware'

    def __init__(self, profile):
        profile.validate()
        if not profile.hardware_confirmed or profile.port == 'DEMO':
            raise ValueError('真实模式要求先核对设备型号、寄存器映射及串口，并在配置中确认 hardware_confirmed')
        try:
            import serial
            import serial.tools.list_ports
        except ImportError as exc:
            raise ValueError('缺少 pyserial，请运行 setup.ps1 安装项目串口依赖') from exc
        self.serial = serial
        self.profile = profile

    def ports(self):
        # Do not expose USB serial numbers; names and descriptions suffice for diagnosis.
        try:
            return [{'device': p.device, 'description': p.description}
                    for p in self.serial.tools.list_ports.comports()]
        except OSError as exc:
            raise AcquisitionError('enumeration_error', '串口枚举失败，请检查系统设备状态') from exc

    def config(self):
        return self.profile.public()

    def transact(self):
        p = self.profile
        try:
            if p.port.casefold() not in [x['device'].casefold() for x in self.ports()]:
                raise AcquisitionError('port_missing', '配置的串口未出现在枚举结果中')
            with self.serial.Serial(port=p.port, baudrate=p.baudrate, bytesize=8,
                                    parity=p.parity, stopbits=p.stopbits, timeout=p.timeout,
                                    write_timeout=p.timeout) as port:
                port.reset_input_buffer()
                # Respect the RTU silent interval before a new frame.
                time.sleep(max(.004, 3.5 * 11 / p.baudrate))
                port.write(request_frame(p))
                port.flush()
                header = port.read(3)
                if len(header) != 3:
                    return header
                remaining = 2 if header[1] & 0x80 else header[2] + 2
                if remaining > 252:
                    raise AcquisitionError('length_error', '设备返回的帧长度异常')
                return header + port.read(remaining)
        except (self.serial.SerialException, OSError) as exc:
            raise AcquisitionError('serial_error', '串口打开或传输失败，请检查占用和设备连接') from exc


class Collector:
    def __init__(self, profile, backend, store, reference_profile=None):
        self.profile, self.backend, self.store = profile, backend, store
        # A live reference must be supplied independently; current settings are not evidence.
        self.reference_profile = reference_profile if reference_profile is not None else (profile if isinstance(backend, DemoBackend) else None)
        self.bus_lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.enabled = True
        self.current_streak = 0
        self.failure_count = 0
        self.session_success = False
        self.latest_id = None
        self.last_error = None

    def start(self):
        if self.thread and self.thread.is_alive(): return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True, name='sensor-collector')
        self.thread.start()

    def _loop(self):
        while not self.stop_event.is_set():
            if self.enabled: self.read_once()
            self.stop_event.wait(self.profile.interval)

    def read_once(self):
        with self.bus_lock:
            raw = b''
            try:
                raw = self.backend.transact()
                data = parse_response(raw, self.profile)
                sample_id = self.store.sample(self.backend.source, True, data, raw=raw.hex())
                self.current_streak += 1
                self.session_success = True
                self.last_error = None
                result = {'ok': True, 'sample_id': sample_id, **data}
            except AcquisitionError as exc:
                sample_id = self.store.sample(self.backend.source, False, code=exc.code,
                                             detail=str(exc), raw=raw.hex())
                self.current_streak = 0
                self.failure_count += 1
                self.last_error = exc.code
                result = {'ok': False, 'sample_id': sample_id, 'code': exc.code, 'detail': str(exc)}
            self.latest_id = sample_id
            return result

    def status(self):
        with self.bus_lock:
            latest = self.store.latest_success()
            age = None if latest is None else max(0, time.time() - latest['ts'])
            running = bool(self.thread and self.thread.is_alive() and self.enabled and not self.stop_event.is_set())
            fresh = bool(self.session_success and age is not None and age <= self.profile.stale_after)
            quality = ('stopped' if not running else 'error' if self.last_error else
                       'fresh' if fresh else 'stale' if latest else 'no_data')
            # Historical values stay visible but never gain a fresh status after restart.
            return {'source': self.backend.source, 'collector_running': running,
                    'quality': quality, 'age_seconds': None if age is None else round(age, 2),
                    'last_success': latest, 'consecutive_successes': self.current_streak,
                    'failure_count': self.failure_count,
                    'last_error': self.last_error, 'stale_after': self.profile.stale_after}

    def set_scenario(self, scenario):
        if not isinstance(self.backend, DemoBackend):
            raise ValueError('故障注入只允许在模拟模式使用')
        with self.bus_lock:
            if scenario == 'collector_stopped':
                self.enabled = False
            elif scenario in self.backend.scenarios:
                self.enabled = True
                self.backend.scenario = scenario
            else:
                raise ValueError('未知模拟场景')
            self.current_streak = 0
            self.store.event('simulation_scenario', scenario)

    def stop(self):
        self.stop_event.set()
        if self.thread: self.thread.join(timeout=10)
