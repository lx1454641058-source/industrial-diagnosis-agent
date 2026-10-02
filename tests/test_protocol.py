"""Original tests using the vendor's public request/response example as evidence."""
from dataclasses import replace
import unittest
from diagnosis.protocol import Profile, AcquisitionError, request_frame, parse_response, with_crc


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.profile = Profile(temperature_offset=1, humidity_offset=0)

    def test_official_request_vector(self):
        self.assertEqual(request_frame(self.profile).hex(' '), '01 03 00 00 00 02 c4 0b')

    def test_official_response_mapping(self):
        value = parse_response(bytes.fromhex('01 03 04 01 D7 00 D6 CA 69'), self.profile)
        self.assertEqual((value['humidity'], value['temperature']), (47.1, 21.4))

    def test_signed_temperature_option_not_hardware_claim(self):
        frame = with_crc(bytes.fromhex('01 03 04 01 f4 ff 9c'))
        self.assertEqual(parse_response(frame, self.profile)['temperature'], -10)
        with self.assertRaises(AcquisitionError):
            parse_response(frame, replace(self.profile, temperature_signed=False))

    def test_failure_frames(self):
        cases = [(b'', 'timeout'), (b'\x01\x03', 'short_frame'),
                 (bytes.fromhex('01 03 04 01 D7 00 D6 CA 68'), 'crc_error'),
                 (with_crc(bytes.fromhex('02 03 04 01 D7 00 D6')), 'address_error'),
                 (with_crc(bytes.fromhex('01 04 04 01 D7 00 D6')), 'function_error'),
                 (with_crc(bytes.fromhex('01 83 02')), 'modbus_exception'),
                 (with_crc(bytes.fromhex('01 03 02 01 D7')), 'length_error'),
                 (with_crc(bytes.fromhex('01 03 04 04 b0 00 D6')), 'value_error')]
        for frame, code in cases:
            with self.subTest(code=code), self.assertRaises(AcquisitionError) as error:
                parse_response(frame, self.profile)
            self.assertEqual(error.exception.code, code)

    def test_rejects_unsafe_or_invalid_profile(self):
        for values in [{'unit':0}, {'function':6}, {'address':65535,'count':2},
                       {'temperature_offset':2}, {'timeout':float('nan')},
                       {'interval':True}, {'hardware_confirmed':'true'}, {'stale_after':1}]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                replace(self.profile, **values).validate()


if __name__ == '__main__': unittest.main()
