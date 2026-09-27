"""
Home Assistant integration over MQTT auto-discovery.

LineDrive announces a "LineDrive" device with sensors (status, now recording, next recording,
tuners free, last failure) and buttons (stop recording, free tuner N). HA creates the entities
itself; nothing to add to configuration.yaml.

Config (config.json):
    "mqtt": {"host": "mosquitto", "port": 1883, "username": "", "password": "",
             "discovery_prefix": "homeassistant"}
"""
import json
import threading
import time

BASE = 'linedrive'
STATE_TOPIC = f'{BASE}/state'
AVAIL_TOPIC = f'{BASE}/availability'
CMD_TOPIC = f'{BASE}/cmd'


class MqttBridge:
    def __init__(self, cfg, get_state, on_command, tuner_count=2, version=''):
        """get_state() -> dict published to STATE_TOPIC; on_command(name, arg) handles button presses"""
        import paho.mqtt.client as mqtt
        self.cfg = cfg
        self.get_state = get_state
        self.on_command = on_command
        self.tuner_count = tuner_count
        self.version = version
        self.prefix = cfg.get('discovery_prefix', 'homeassistant')
        self._last = None
        self._wake = threading.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='linedrive')
        if cfg.get('username'):
            self.client.username_pw_set(cfg['username'], cfg.get('password') or None)
        self.client.will_set(AVAIL_TOPIC, 'offline', retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    # --- lifecycle ---------------------------------------------------------------

    def start(self):
        self.client.connect_async(self.cfg.get('host', 'localhost'), int(self.cfg.get('port', 1883)), keepalive=60)
        self.client.loop_start()
        threading.Thread(target=self._publish_loop, daemon=True).start()

    def poke(self):
        """Publish soon (call when something changed: recording started/finished/failed)"""
        self._wake.set()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[MQTT] Connect failed: {reason_code}")
            return
        print("[MQTT] Connected; announcing LineDrive to Home Assistant")
        self._announce()
        client.publish(AVAIL_TOPIC, 'online', retain=True)
        client.subscribe(f'{CMD_TOPIC}/#')
        self._last = None
        self.poke()

    def _on_message(self, client, userdata, msg):
        parts = msg.topic[len(CMD_TOPIC) + 1:].split('/')
        try:
            self.on_command(parts[0], parts[1] if len(parts) > 1 else None)
        except Exception as e:
            print(f"[MQTT] Command {msg.topic} failed: {e}")
        self.poke()

    def _publish_loop(self):
        while True:
            try:
                state = self.get_state()
                payload = json.dumps(state, default=str)
                # Minutes-left changes every minute anyway; skip identical payloads between those
                if payload != self._last and self.client.is_connected():
                    self.client.publish(STATE_TOPIC, payload, retain=True)
                    self._last = payload
            except Exception as e:
                print(f"[MQTT] State update failed: {e}")
            self._wake.wait(30)
            self._wake.clear()

    # --- discovery ---------------------------------------------------------------

    def _device(self):
        return {'identifiers': ['linedrive'], 'name': 'LineDrive', 'manufacturer': 'LineDrive',
                'model': 'HDHomeRun DVR', 'sw_version': self.version}

    def _config(self, component, object_id, payload):
        payload.update({
            'unique_id': f'linedrive_{object_id}',
            'default_entity_id': f'{component}.linedrive_{object_id}',
            'device': self._device(),
            'availability_topic': AVAIL_TOPIC,
        })
        self.client.publish(f'{self.prefix}/{component}/linedrive/{object_id}/config',
                            json.dumps(payload), retain=True)

    def _announce(self):
        state = {'state_topic': STATE_TOPIC}
        self._config('sensor', 'status', dict(state, name='Status', icon='mdi:record-rec',
                     value_template='{{ value_json.status }}',
                     json_attributes_topic=STATE_TOPIC))
        self._config('binary_sensor', 'recording', dict(state, name='Recording', device_class='running',
                     value_template="{{ 'ON' if value_json.recording else 'OFF' }}"))
        self._config('sensor', 'now_recording', dict(state, name='Now recording', icon='mdi:television-play',
                     value_template="{{ value_json.recording_title or 'Nothing' }}"))
        self._config('sensor', 'next_recording', dict(state, name='Next recording', icon='mdi:calendar-clock',
                     value_template="{{ value_json.next_title or 'Nothing scheduled' }}"))
        self._config('sensor', 'next_recording_time', dict(state, name='Next recording time',
                     device_class='timestamp',
                     value_template='{{ value_json.next_start or None }}'))
        self._config('sensor', 'tuners_free', dict(state, name='Tuners free', icon='mdi:antenna',
                     value_template='{{ value_json.tuners_free }}', state_class='measurement'))
        self._config('sensor', 'last_failure', dict(state, name='Last failure', icon='mdi:alert-circle-outline',
                     value_template="{{ value_json.last_failure or 'None' }}"))
        self._config('button', 'stop_recording', {'name': 'Stop recording', 'icon': 'mdi:stop-circle',
                     'command_topic': f'{CMD_TOPIC}/stop'})
        for n in range(self.tuner_count):
            self._config('button', f'free_tuner_{n + 1}', {'name': f'Free tuner {n + 1}', 'icon': 'mdi:antenna',
                         'command_topic': f'{CMD_TOPIC}/free_tuner/{n}'})
