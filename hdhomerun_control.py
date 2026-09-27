"""
Minimal HDHomeRun control-protocol client (TCP port 65001, the protocol hdhomerun_config uses).

Used to free a tuner another app is holding open, e.g. a live-TV stream Jellyfin never closed:
    release_tuner('192.168.1.50', 0)
is the same as
    hdhomerun_config <device> set /tuner0/lockkey force
    hdhomerun_config <device> set /tuner0/channel none

Also finds HDHomeRuns on the network: discover().
"""
import socket
import struct
import zlib

import requests

TYPE_GETSET_REQ = 0x0004
TYPE_GETSET_RPY = 0x0005
TAG_GETSET_NAME = 0x03
TAG_GETSET_VALUE = 0x04
TAG_ERROR_MESSAGE = 0x05

CONTROL_PORT = 65001


def _tlv(tag, value):
    data = value.encode() + b'\0'
    n = len(data)
    length = bytes([n]) if n < 128 else bytes([(n & 0x7F) | 0x80, n >> 7])
    return bytes([tag]) + length + data


def _packet(ptype, payload):
    body = struct.pack('>HH', ptype, len(payload)) + payload
    return body + struct.pack('<I', zlib.crc32(body) & 0xFFFFFFFF)


def _parse_tags(payload):
    tags, i = {}, 0
    while i < len(payload):
        tag = payload[i]
        n = payload[i + 1]
        i += 2
        if n & 0x80:
            n = (n & 0x7F) | (payload[i] << 7)
            i += 1
        tags[tag] = payload[i:i + n].rstrip(b'\0').decode(errors='replace')
        i += n
    return tags


def getset(host, name, value=None, timeout=3):
    """Get (value=None) or set a device variable. Returns the value; raises RuntimeError on a device error."""
    payload = _tlv(TAG_GETSET_NAME, name)
    if value is not None:
        payload += _tlv(TAG_GETSET_VALUE, value)
    with socket.create_connection((host, CONTROL_PORT), timeout=timeout) as s:
        s.sendall(_packet(TYPE_GETSET_REQ, payload))
        header = b''
        while len(header) < 4:
            chunk = s.recv(4 - len(header))
            if not chunk:
                raise RuntimeError('HDHomeRun closed the connection')
            header += chunk
        ptype, length = struct.unpack('>HH', header)
        rest = b''
        while len(rest) < length + 4:
            chunk = s.recv(length + 4 - len(rest))
            if not chunk:
                break
            rest += chunk
    if ptype != TYPE_GETSET_RPY:
        raise RuntimeError(f'Unexpected reply type {ptype:#x}')
    tags = _parse_tags(rest[:length])
    if TAG_ERROR_MESSAGE in tags:
        raise RuntimeError(tags[TAG_ERROR_MESSAGE])
    return tags.get(TAG_GETSET_VALUE)


TYPE_DISCOVER_REQ = 0x0002
TYPE_DISCOVER_RPY = 0x0003
DISCOVER_PORT = 65001


def _local_ipv4s():
    """This machine's IPv4 addresses (for sending a discovery broadcast out of every adapter)"""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))  # no packet is sent; this just picks the default-route adapter
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return [ip for ip in ips if not ip.startswith('127.')] or ['']


def _broadcast_discover(timeout=1.5):
    """Device IPs that answer a discover broadcast (wildcard device type and id)"""
    payload = struct.pack('>BBI', 0x01, 4, 0xFFFFFFFF) + struct.pack('>BBI', 0x02, 4, 0xFFFFFFFF)
    packet = _packet(TYPE_DISCOVER_REQ, payload)
    found = set()
    for local in _local_ipv4s():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind((local, 0))
            s.settimeout(timeout)
            s.sendto(packet, ('255.255.255.255', DISCOVER_PORT))
            while True:
                data, addr = s.recvfrom(2048)
                if len(data) >= 4 and struct.unpack('>H', data[:2])[0] == TYPE_DISCOVER_RPY:
                    found.add(addr[0])
        except OSError:
            pass
        finally:
            try:
                s.close()
            except Exception:
                pass
    return found


def _cloud_discover():
    """Device IPs from Silicondust's discovery service (devices behind the same public IP)"""
    try:
        r = requests.get('https://api.hdhomerun.com/discover', timeout=5)
        return {d['LocalIP'].split(':')[0] for d in r.json() if d.get('LocalIP')}
    except Exception:
        return set()


def describe(ip, timeout=3):
    """Model/tuner details from a device's discover.json, or None if it isn't an HDHomeRun tuner"""
    try:
        d = requests.get(f'http://{ip}/discover.json', timeout=timeout).json()
    except Exception:
        return None
    if not d.get('TunerCount'):
        return None  # e.g. a storage/DVR engine rather than a tuner
    return {'ip': ip, 'name': d.get('FriendlyName') or 'HDHomeRun', 'model': d.get('ModelNumber', ''),
            'tuners': d.get('TunerCount'), 'device_id': d.get('DeviceID', ''),
            'firmware': d.get('FirmwareVersion', '')}


def discover():
    """HDHomeRun tuners on the network: [{'ip', 'name', 'model', 'tuners', ...}]. Broadcasts don't
    leave a Docker bridge network, so the cloud lookup covers that case."""
    ips = _broadcast_discover() | _cloud_discover()
    devices = [d for d in (describe(ip) for ip in sorted(ips)) if d]
    return sorted(devices, key=lambda d: d['ip'])


def parse_status(text):
    """'ch=8vsb:515000000 lock=8vsb ss=65 snq=77 seq=100 ...' -> {'ch': ..., 'lock': ..., 'ss': 65, ...}"""
    out = {}
    for part in (text or '').split():
        key, _, value = part.partition('=')
        out[key] = int(value) if value.isdigit() else value
    return out


def measure_signal(host, tuner, vchannel, timeout=6.0):
    """Tune a free tuner to a channel without streaming it and read the signal, like the HDHomeRun
    app's signal meter. Returns {'ss', 'snq', 'seq', 'locked', 'frequency', 'channels'} where
    channels are the virtual channels carried on the same frequency (they share the signal), or
    None if the tuner couldn't be used. Leaves the tuner idle."""
    import time
    base = f'/tuner{int(tuner)}'
    try:
        getset(host, base + '/vchannel', str(vchannel))
    except RuntimeError:
        return None  # in use, or the channel isn't in the lineup
    try:
        deadline = time.time() + timeout
        status = {}
        while time.time() < deadline:
            status = parse_status(getset(host, base + '/status'))
            if status.get('lock', 'none') != 'none' and status.get('seq'):
                break
            time.sleep(0.25)
        if status.get('lock', 'none') == 'none' or not status.get('seq'):
            return {'ss': status.get('ss', 0), 'snq': 0, 'seq': 0, 'locked': False,
                    'frequency': str(status.get('ch', '')), 'channels': [str(vchannel)]}
        # Symbol quality needs a moment to show errors; keep the worst of a few readings
        samples = [status]
        for _ in range(3):
            time.sleep(0.4)
            samples.append(parse_status(getset(host, base + '/status')))
        carried = []
        for line in (getset(host, base + '/streaminfo') or '').splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0].endswith(':') and not any(
                    flag in line for flag in ('(encrypted)', '(control)', '(no data)')):
                carried.append(parts[1])
        return {'ss': min(s.get('ss', 0) for s in samples), 'snq': min(s.get('snq', 0) for s in samples),
                'seq': min(s.get('seq', 0) for s in samples), 'locked': True,
                'frequency': str(status.get('ch', '')), 'channels': carried or [str(vchannel)]}
    finally:
        try:
            getset(host, base + '/channel', 'none')
        except (OSError, RuntimeError):
            pass


def release_tuner(host, tuner):
    """Force a tuner free, ending whatever stream holds it. Clearing the target as well frees it
    even when the client keeps its (now silent) connection open instead of hanging up."""
    getset(host, f'/tuner{int(tuner)}/lockkey', 'force')
    getset(host, f'/tuner{int(tuner)}/channel', 'none')
    try:
        getset(host, f'/tuner{int(tuner)}/target', 'none')
    except RuntimeError:
        pass  # some firmware refuses target changes for its own HTTP streams; channel none still stops it
