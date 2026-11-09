"""Read-only parsing of Huawei VRP interface and transceiver diagnostics."""
import re


def interface_reading(port, status, optics):
    number = re.search(r'\d+/\d+/\d+', port)
    number = number.group() if number else ''
    header = r'^\s*XGigabitEthernet\s*' + re.escape(number) + r'\s+'
    state = re.search(header + r'current state\s*:\s*(UP|DOWN|Administratively DOWN)\s*$', status, re.I | re.M)
    values = dict(state='unknown', rx=None, tx=None, rx_bps=None, tx_bps=None,
                  rx_percent=None, tx_percent=None, rate_window_seconds=None,
                  rate_source='huawei-vrp', description='')
    if state:
        values['state'] = 'up' if state[1].upper() == 'UP' else 'down'
        description = re.search(r'^Description\s*:\s*(.*)$', status, re.M)
        values['description'] = description[1].strip() if description else ''
        # Peaks and cumulative byte/packet counters are not current rates.
        for direction, key in [('input', 'rx'), ('output', 'tx')]:
            rate = re.search(r'^\s*Last\s+(\d+)\s+seconds\s+' + direction + r' rate\s+(\d+)\s+bits/sec\b', status, re.I | re.M)
            if rate:
                values[key + '_bps'] = int(rate[2])
                values['rate_window_seconds'] = int(rate[1])
            percent = re.search(r'^\s*' + direction + r' bandwidth utilization\s*:\s*(\d+(?:\.\d+)?)%', status, re.I | re.M)
            if percent and float(percent[1]) <= 100:
                values[key + '_percent'] = float(percent[1])
    if re.search(header + r'transceiver information\s*:', optics, re.I | re.M):
        for key in ('rx', 'tx'):
            # Exact diagnostic label: never warning/threshold values.
            power = re.search(r'^\s*' + key + r' Power\(dBM\)\s*:\s*([+-]?\d+(?:\.\d+)?)\s*$', optics, re.I | re.M)
            if power:
                values[key] = float(power[1])
    return values
