"""
LineDrive VPN Management
Generic VPN support for secure connections with multiple providers
"""

import subprocess
import time
import requests
from config_manager import get_config

class VPNManager:
    def __init__(self, vpn_config=None):
        if vpn_config:
            self.vpn_config = vpn_config
        else:
            config = get_config()
            self.vpn_config = config.get_vpn_config()
        
        self.provider = self.vpn_config['provider']
        self.provider_config = self.vpn_config['providers'].get(self.provider, {})
        
    def is_enabled(self):
        """Check if VPN management is enabled"""
        return self.vpn_config['enabled']
    
    def is_connected(self):
        """Check if VPN is currently connected"""
        if not self.is_enabled():
            return True  # If VPN is disabled, consider it "connected" for functionality
            
        # Method 1: Try provider-specific status command
        if self.provider_config.get('status_command'):
            try:
                result = subprocess.run(
                    self.provider_config['status_command'].split(),
                    capture_output=True, text=True, timeout=10
                )
                
                output = result.stdout.lower() + result.stderr.lower()
                connected_keywords = self.provider_config.get('connected_keywords', ['connected'])
                
                for keyword in connected_keywords:
                    if keyword.lower() in output:
                        print(f"VPN Status: Connected via {self.provider}")
                        return True
                        
                print(f"VPN Status: Not connected ({self.provider})")
                return False
                
            except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
                print(f"VPN status check failed: {e}")
        
        # Method 2: Check IP address change (fallback)
        return self.check_ip_change()
    
    def check_ip_change(self):
        """Check if IP indicates VPN connection by comparing with known local IP"""
        try:
            response = requests.get(
                self.vpn_config['connection_check_url'], 
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                ip = data.get('ip', '')
                country = data.get('country', 'Unknown')
                
                print(f"Current IP: {ip} ({country})")
                
                # Basic heuristic: if we get a response, assume we have internet
                # More sophisticated checking would compare with baseline IP
                return True
                
        except Exception as e:
            print(f"IP check failed: {e}")
            return False
    
    def connect(self):
        """Connect to VPN"""
        if not self.is_enabled():
            print("VPN management is disabled")
            return True
            
        if self.is_connected():
            print("VPN already connected")
            return True
            
        connect_cmd = self.provider_config.get('connect_command')
        if not connect_cmd:
            print(f"No connect command configured for {self.provider}")
            return False
            
        print(f"Connecting to VPN via {self.provider}...")
        
        try:
            result = subprocess.run(
                connect_cmd.split(),
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode == 0:
                print("VPN connection command executed successfully")
                # Wait a moment for connection to establish
                time.sleep(3)
                
                # Verify connection
                if self.is_connected():
                    print("VPN connected successfully!")
                    return True
                else:
                    print("VPN command succeeded but connection verification failed")
                    return False
            else:
                print(f"VPN connection failed: {result.stderr}")
                return False
                
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
            print(f"VPN connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from VPN"""
        if not self.is_enabled():
            print("VPN management is disabled")
            return True
            
        disconnect_cmd = self.provider_config.get('disconnect_command')
        if not disconnect_cmd:
            print(f"No disconnect command configured for {self.provider}")
            return False
            
        print(f"Disconnecting VPN via {self.provider}...")
        
        try:
            result = subprocess.run(
                disconnect_cmd.split(),
                capture_output=True, text=True, timeout=15
            )
            
            if result.returncode == 0:
                print("VPN disconnected successfully")
                return True
            else:
                print(f"VPN disconnection failed: {result.stderr}")
                return False
                
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
            print(f"VPN disconnection error: {e}")
            return False
    
    def ensure_connected_for_torrents(self):
        """Ensure VPN is connected before torrent operations"""
        if not self.vpn_config['required_for_torrents']:
            return True
            
        if not self.is_connected():
            if self.vpn_config['auto_connect']:
                print("VPN required for torrents, attempting to connect...")
                return self.connect()
            else:
                print("❌ VPN connection required for torrent operations but auto-connect is disabled")
                print("Please connect your VPN manually or enable auto_connect in configuration")
                return False
        
        return True
    
    def get_status(self):
        """Get detailed VPN status information"""
        status = {
            'enabled': self.is_enabled(),
            'provider': self.provider,
            'connected': False,
            'ip_info': None
        }
        
        if status['enabled']:
            status['connected'] = self.is_connected()
            
            # Get IP information
            try:
                response = requests.get(
                    self.vpn_config['connection_check_url'], 
                    timeout=5
                )
                if response.status_code == 200:
                    status['ip_info'] = response.json()
            except:
                pass
                
        return status

# Global VPN manager instance
vpn_manager = None

def get_vpn_manager():
    """Get global VPN manager instance"""
    global vpn_manager
    if vpn_manager is None:
        vpn_manager = VPNManager()
    return vpn_manager

def check_vpn_for_torrents():
    """Convenience function to check VPN before torrent operations"""
    manager = get_vpn_manager()
    return manager.ensure_connected_for_torrents()

def get_vpn_status():
    """Convenience function to get VPN status"""
    manager = get_vpn_manager()
    return manager.get_status()

if __name__ == "__main__":
    # Test VPN functionality
    manager = VPNManager()
    
    print("=== VPN Manager Test ===")
    status = manager.get_status()
    
    print(f"VPN Enabled: {status['enabled']}")
    print(f"Provider: {status['provider']}")
    print(f"Connected: {status['connected']}")
    
    if status['ip_info']:
        ip_info = status['ip_info']
        print(f"Current IP: {ip_info.get('ip', 'Unknown')}")
        print(f"Location: {ip_info.get('city', 'Unknown')}, {ip_info.get('country', 'Unknown')}")
        print(f"ISP: {ip_info.get('org', 'Unknown')}")
    
    if status['enabled'] and not status['connected']:
        test_connect = input("\nWould you like to test VPN connection? [y/N]: ").strip().lower()
        if test_connect in ['y', 'yes']:
            if manager.connect():
                print("Connection test successful!")
            else:
                print("Connection test failed!")