"""
LineDrive Indexer Management
Generic indexer support for multiple torrent/usenet providers
"""

import requests
import time
from urllib.parse import urljoin, urlencode
from config_manager import get_config

class IndexerManager:
    def __init__(self, indexer_config=None):
        if indexer_config:
            self.indexer_config = indexer_config
        else:
            config = get_config()
            self.indexer_config = config.get_indexer_config()
        
        self.provider = self.indexer_config['provider']
        self.provider_config = self.indexer_config['providers'].get(self.provider, {})
        
    def is_enabled(self):
        """Check if indexer integration is enabled"""
        return self.indexer_config['enabled']
    
    def is_available(self):
        """Check if the indexer service is available"""
        if not self.is_enabled():
            return False
            
        try:
            url = self.provider_config.get('api_url', '')
            if not url:
                return False
                
            # Test connectivity with a simple ping
            response = requests.get(f"{url}/api/v1/indexers", 
                                  headers=self._get_headers(),
                                  timeout=5)
            return response.status_code == 200
            
        except Exception as e:
            print(f"Indexer availability check failed: {e}")
            return False
    
    def _get_headers(self):
        """Get authentication headers for API requests"""
        api_key = self.provider_config.get('api_key', '')
        if not api_key:
            return {}
            
        if self.provider == 'prowlarr':
            return {'X-Api-Key': api_key}
        elif self.provider == 'jackett':
            return {}  # Jackett uses API key in URL parameters
        else:
            return {'Authorization': f'Bearer {api_key}'}
    
    def _build_search_url(self, query, category=None):
        """Build search URL for the configured provider"""
        base_url = self.provider_config.get('api_url', '')
        if not base_url:
            return None
            
        if self.provider == 'prowlarr':
            # Prowlarr API format
            url = urljoin(base_url, '/api/v1/search')
            params = {'query': query, 'type': 'search'}
            if category:
                params['categories'] = category
            return f"{url}?{urlencode(params)}"
            
        elif self.provider == 'jackett':
            # Jackett API format
            api_key = self.provider_config.get('api_key', '')
            indexers = self.provider_config.get('indexers', 'all')
            url = urljoin(base_url, '/api/v2.0/indexers/all/results')
            params = {
                'apikey': api_key,
                'Query': query,
                'Category[]': category or '5000'  # TV category
            }
            return f"{url}?{urlencode(params)}"
            
        elif self.provider == 'torznab':
            # Generic Torznab format
            api_key = self.provider_config.get('api_key', '')
            url = urljoin(base_url, '/api')
            params = {
                't': 'search',
                'apikey': api_key,
                'q': query,
                'cat': category or '5000'
            }
            return f"{url}?{urlencode(params)}"
            
        return None
    
    def search(self, query, category=None, limit=50):
        """Search for content using the configured indexer"""
        if not self.is_enabled():
            return {'error': 'Indexer integration is disabled'}
            
        try:
            search_url = self._build_search_url(query, category)
            if not search_url:
                return {'error': 'Unable to build search URL for provider'}
            
            headers = self._get_headers()
            timeout = self.indexer_config.get('timeout', 30)
            
            response = requests.get(search_url, headers=headers, timeout=timeout)
            response.raise_for_status()
            
            # Parse response based on provider
            if self.provider == 'prowlarr':
                return self._parse_prowlarr_response(response.json(), limit)
            elif self.provider in ['jackett', 'torznab']:
                return self._parse_torznab_response(response.text, limit)
            else:
                return {'error': f'Unknown provider: {self.provider}'}
                
        except requests.exceptions.Timeout:
            return {'error': f'Search request timed out after {timeout} seconds'}
        except requests.exceptions.ConnectionError:
            return {'error': 'Could not connect to indexer service'}
        except requests.exceptions.HTTPError as e:
            return {'error': f'HTTP error: {e.response.status_code}'}
        except Exception as e:
            return {'error': f'Search failed: {str(e)}'}
    
    def _parse_prowlarr_response(self, data, limit):
        """Parse Prowlarr API response"""
        results = []
        
        for item in data[:limit]:
            # Extract download information from multiple possible fields
            magnet_link = (
                item.get('magnetUrl') or 
                item.get('magnet') or 
                ''
            )
            
            # Also get download URL (may be torrent file instead of magnet)
            download_url = (
                item.get('downloadUrl') or 
                item.get('link') or 
                item.get('guid') or 
                ''
            )
            
            # Process magnet link if found - ensure it's valid
            if magnet_link:
                if not magnet_link.startswith('magnet:'):
                    # Some indexers return URLs with embedded magnet links
                    if 'magnet:' in magnet_link:
                        # Extract magnet part if it's embedded in a longer URL
                        import re
                        magnet_match = re.search(r'magnet:[^&\s"\']+', magnet_link)
                        if magnet_match:
                            magnet_link = magnet_match.group(0)
                        else:
                            # Not a valid magnet link, clear it
                            magnet_link = ''
                    else:
                        # Not a magnet link at all, clear it
                        magnet_link = ''
            
            # Also check if download_url contains an embedded magnet (some indexers do this)
            if not magnet_link and download_url and 'magnet:' in download_url:
                import re
                magnet_match = re.search(r'magnet:[^&\s"\']+', download_url)
                if magnet_match:
                    magnet_link = magnet_match.group(0)
            
            result = {
                'title': item.get('title', ''),
                'size': item.get('size', 0),
                'seeders': item.get('seeders', 0),
                'leechers': item.get('leechers', 0), 
                'download_url': download_url,  # Original download URL (might be torrent file)
                'magnet_url': magnet_link,     # Extracted magnet link (if any)
                'magnet': magnet_link,         # Also provide 'magnet' field for compatibility
                'info_url': item.get('infoUrl', ''),
                'indexer': item.get('indexer', ''),
                'category': item.get('categories', []),
                'publish_date': item.get('publishDate', ''),
                'infoHash': item.get('infoHash', ''),
                'has_magnet': bool(magnet_link),
                'has_download_url': bool(download_url)
            }
            results.append(result)
        
        return {
            'results': results,
            'total': len(results),
            'provider': self.provider
        }
    
    def resolve_download_url(self, download_url):
        """
        Resolve a Prowlarr/indexer download URL to get the actual magnet link
        This handles cases where the indexer returns a download API URL instead of direct magnet
        """
        if not download_url:
            return None
            
        # If it's already a magnet link, return as-is
        if download_url.startswith('magnet:'):
            return download_url
        
        # Check if it's a Prowlarr download URL
        if '/download?' in download_url and 'apikey=' in download_url:
            try:
                # Make request to Prowlarr download URL
                response = requests.get(download_url, timeout=10, allow_redirects=True)
                
                # Check if response is a redirect to magnet link
                if response.history:
                    for redirect in response.history:
                        if redirect.headers.get('Location', '').startswith('magnet:'):
                            return redirect.headers['Location']
                
                # Check final URL if it's a magnet
                if response.url.startswith('magnet:'):
                    return response.url
                
                # Check response content for magnet links
                if hasattr(response, 'text'):
                    import re
                    magnet_match = re.search(r'magnet:[^"\s<>&]+', response.text)
                    if magnet_match:
                        return magnet_match.group(0)
                
                print(f"⚠️ Could not extract magnet from Prowlarr URL: {download_url[:100]}...")
                return None
                
            except Exception as e:
                print(f"❌ Error resolving download URL: {e}")
                return None
        
        # Not a supported download URL format
        return None
    
    def _parse_torznab_response(self, xml_data, limit):
        """Parse Torznab/Jackett XML response"""
        import xml.etree.ElementTree as ET
        
        results = []
        try:
            root = ET.fromstring(xml_data)
            items = root.findall('.//item')[:limit]
            
            for item in items:
                title = item.find('title')
                size = item.find('size') 
                link = item.find('link')
                
                # Extract torznab attributes
                seeders_elem = item.find('.//*[@name="seeders"]')
                leechers_elem = item.find('.//*[@name="peers"]')
                magnet_elem = item.find('.//*[@name="magneturl"]')
                
                result = {
                    'title': title.text if title is not None else '',
                    'size': int(size.text) if size is not None and size.text.isdigit() else 0,
                    'seeders': int(seeders_elem.get('value', 0)) if seeders_elem is not None else 0,
                    'leechers': int(leechers_elem.get('value', 0)) if leechers_elem is not None else 0,
                    'download_url': link.text if link is not None else '',
                    'magnet_url': magnet_elem.get('value', '') if magnet_elem is not None else '',
                    'info_url': '',
                    'indexer': self.provider,
                    'category': [],
                    'publish_date': ''
                }
                results.append(result)
                
        except ET.ParseError as e:
            return {'error': f'Failed to parse XML response: {e}'}
        
        return {
            'results': results,
            'total': len(results),
            'provider': self.provider
        }
    
    def get_indexers(self):
        """Get list of available indexers"""
        if not self.is_enabled():
            return {'error': 'Indexer integration is disabled'}
            
        try:
            if self.provider == 'prowlarr':
                url = urljoin(self.provider_config['api_url'], '/api/v1/indexer')
                response = requests.get(url, headers=self._get_headers(), timeout=10)
                response.raise_for_status()
                return {'indexers': response.json()}
            else:
                # For other providers, return configured info
                return {
                    'indexers': [{
                        'name': self.provider,
                        'id': 1,
                        'enabled': True
                    }]
                }
                
        except Exception as e:
            return {'error': f'Failed to get indexers: {e}'}
    
    def test_connection(self):
        """Test connection to indexer service"""
        try:
            if not self.provider_config.get('api_url'):
                return {'success': False, 'error': 'No API URL configured'}
                
            # Try a simple search to test connectivity  
            test_result = self.search('test', limit=1)
            
            if 'error' in test_result:
                return {'success': False, 'error': test_result['error']}
            else:
                return {
                    'success': True, 
                    'message': f'Successfully connected to {self.provider}',
                    'indexer_count': len(test_result.get('results', []))
                }
                
        except Exception as e:
            return {'success': False, 'error': f'Connection test failed: {e}'}

# Convenience functions for backward compatibility
def get_indexer_manager():
    """Get configured indexer manager instance"""
    return IndexerManager()

def search_torrents(query, category=None, limit=50):
    """Search for torrents using configured indexer"""
    indexer = get_indexer_manager()
    return indexer.search(query, category, limit)

def is_indexer_available():
    """Check if indexer service is available"""
    indexer = get_indexer_manager()
    return indexer.is_available()