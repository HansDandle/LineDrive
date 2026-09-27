"""
Torrent Client Manager for LineDrive
Handles integration with various torrent clients (qBittorrent, Transmission, Deluge)
"""

import requests
import json
import base64
from pathlib import Path


class TorrentClientManager:
    def __init__(self, config):
        self.config = config
        self.torrent_config = config.get('torrent_client', {})
        self.client_type = self.torrent_config.get('type', 'qbittorrent').lower()
        self.base_url = self.torrent_config.get('url', 'http://localhost:8080')
        self.username = self.torrent_config.get('username', 'admin')
        self.password = self.torrent_config.get('password', '')
        self.session = requests.Session()
        self.authenticated = False

    def authenticate(self):
        """Authenticate with the torrent client"""
        try:
            if self.client_type == 'qbittorrent':
                return self._authenticate_qbittorrent()
            elif self.client_type == 'transmission':
                return self._authenticate_transmission()
            elif self.client_type == 'deluge':
                return self._authenticate_deluge()
            else:
                print(f"❌ Unsupported torrent client: {self.client_type}")
                return False
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False

    def _authenticate_qbittorrent(self):
        """Authenticate with qBittorrent Web API"""
        login_url = f"{self.base_url}/api/v2/auth/login"
        login_data = {
            'username': self.username,
            'password': self.password
        }
        
        response = self.session.post(login_url, data=login_data, timeout=10)
        
        if response.status_code == 200 and response.text.strip() == "Ok.":
            print("✅ qBittorrent authentication successful")
            self.authenticated = True
            return True
        else:
            print(f"❌ qBittorrent authentication failed: {response.status_code} - {response.text}")
            return False

    def _authenticate_transmission(self):
        """Authenticate with Transmission (uses HTTP Basic Auth)"""
        if self.username and self.password:
            auth_string = f"{self.username}:{self.password}"
            encoded_auth = base64.b64encode(auth_string.encode()).decode()
            self.session.headers.update({
                'Authorization': f'Basic {encoded_auth}'
            })
        
        # Test connection with session-get
        test_data = {
            'method': 'session-get',
            'arguments': {}
        }
        
        try:
            response = self.session.post(f"{self.base_url}/rpc", json=test_data, timeout=10)
            if response.status_code in [200, 409]:  # 409 is CSRF token error, but means we're connected
                print("✅ Transmission authentication successful")
                self.authenticated = True
                return True
        except Exception as e:
            print(f"❌ Transmission authentication failed: {e}")
        
        return False

    def _authenticate_deluge(self):
        """Authenticate with Deluge Web API"""
        # Deluge uses a different authentication method
        login_url = f"{self.base_url}/json"
        login_data = {
            'method': 'auth.login',
            'params': [self.password],
            'id': 1
        }
        
        response = self.session.post(login_url, json=login_data, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('result') is True:
                print("✅ Deluge authentication successful")
                self.authenticated = True
                return True
        
        print(f"❌ Deluge authentication failed")
        return False

    def add_torrent(self, magnet_link, category=None, save_path=None):
        """Add a torrent to the client (only accepts magnet links)"""
        if not self.authenticated and not self.authenticate():
            return {'success': False, 'error': 'Authentication failed'}
        
        # Validate that we have a proper magnet link
        if not magnet_link or not isinstance(magnet_link, str):
            return {'success': False, 'error': 'No magnet link provided'}
        
        if not magnet_link.startswith('magnet:'):
            return {'success': False, 'error': f'Invalid magnet link format: {magnet_link[:100]}...' if len(magnet_link) > 100 else f'Invalid magnet link format: {magnet_link}'}

        try:
            if self.client_type == 'qbittorrent':
                return self._add_torrent_qbittorrent(magnet_link, category, save_path)
            elif self.client_type == 'transmission':
                return self._add_torrent_transmission(magnet_link, save_path)
            elif self.client_type == 'deluge':
                return self._add_torrent_deluge(magnet_link, save_path)
            else:
                return {'success': False, 'error': f'Unsupported client: {self.client_type}'}
        except Exception as e:
            return {'success': False, 'error': f'Add torrent error: {str(e)}'}

    def _add_torrent_qbittorrent(self, magnet_link, category=None, save_path=None):
        """Add torrent to qBittorrent"""
        add_url = f"{self.base_url}/api/v2/torrents/add"
        
        data = {
            'urls': magnet_link,
            'autoTMM': 'false',  # Disable automatic torrent management
        }
        
        if category:
            data['category'] = category
        if save_path:
            data['savepath'] = save_path
        
        response = self.session.post(add_url, data=data, timeout=30)
        
        if response.status_code == 200:
            if response.text.strip() == "Ok.":
                print(f"✅ Torrent added to qBittorrent successfully")
                return {'success': True, 'message': 'Torrent added successfully'}
            else:
                print(f"⚠️ qBittorrent response: {response.text}")
                return {'success': True, 'message': f'Torrent added: {response.text}'}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            print(f"❌ Failed to add torrent to qBittorrent: {error_msg}")
            return {'success': False, 'error': error_msg}

    def _add_torrent_transmission(self, magnet_link, save_path=None):
        """Add torrent to Transmission"""
        data = {
            'method': 'torrent-add',
            'arguments': {
                'filename': magnet_link,
                'paused': False
            }
        }
        
        if save_path:
            data['arguments']['download-dir'] = save_path
        
        response = self.session.post(f"{self.base_url}/rpc", json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('result') == 'success':
                print(f"✅ Torrent added to Transmission successfully")
                return {'success': True, 'message': 'Torrent added successfully'}
        
        error_msg = f"Transmission error: {response.text}"
        print(f"❌ Failed to add torrent to Transmission: {error_msg}")
        return {'success': False, 'error': error_msg}

    def _add_torrent_deluge(self, magnet_link, save_path=None):
        """Add torrent to Deluge"""
        data = {
            'method': 'core.add_torrent_magnet',
            'params': [magnet_link, {}],
            'id': 1
        }
        
        if save_path:
            data['params'][1]['download_location'] = save_path
        
        response = self.session.post(f"{self.base_url}/json", json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('result'):
                print(f"✅ Torrent added to Deluge successfully")
                return {'success': True, 'message': 'Torrent added successfully'}
        
        error_msg = f"Deluge error: {response.text}"
        print(f"❌ Failed to add torrent to Deluge: {error_msg}")
        return {'success': False, 'error': error_msg}

    def test_connection(self):
        """Test connection to torrent client"""
        try:
            if self.authenticate():
                return {'success': True, 'message': f'Connected to {self.client_type} successfully'}
            else:
                return {'success': False, 'error': f'Failed to connect to {self.client_type}'}
        except Exception as e:
            return {'success': False, 'error': f'Connection test failed: {str(e)}'}