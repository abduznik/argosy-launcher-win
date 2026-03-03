import requests
import os
from pathlib import Path

class RomMClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')
        self.token = None
        self.user_games = []

    def set_token(self, token):
        self.token = token

    def login(self, username, password):
        url = f"{self.base_url}/api/token"
        scope = "me.read me.write platforms.read roms.read assets.read assets.write roms.user.read roms.user.write collections.read collections.write"
        try:
            response = requests.post(url, data={
                "username": username,
                "password": password,
                "scope": scope
            }, timeout=10)
            if response.status_code == 200:
                self.token = response.json().get("access_token")
                return True, self.token
            return False, f"Login Failed: {response.status_code} - {response.text}"
        except Exception as e:
            return False, str(e)

    def fetch_library(self):
        if not self.token: return []
        url = f"{self.base_url}/api/roms"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            response = requests.get(url, headers=headers, params={"size": 1000}, timeout=15)
            if response.status_code == 200:
                self.user_games = response.json().get("items", [])
                return self.user_games
        except Exception as e:
            print(f"Library fetch error: {e}")
        return []

    def get_latest_save(self, rom_id):
        if not self.token: return None
        url = f"{self.base_url}/api/saves"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            # Fetch saves for this ROM
            response = requests.get(url, headers=headers, params={"rom_id": rom_id}, timeout=10)
            if response.status_code == 200:
                data = response.json()
                # Handle different RomM API response formats
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = data.get("items", [])
                else:
                    items = []
                
                # Sort by created_at or just take the first if the server already sorted
                if items:
                    # Try to sort by ID descending or created_at if available
                    try:
                        items.sort(key=lambda x: x.get('id', 0), reverse=True)
                    except: pass
                    return items[0]
        except Exception as e:
            print(f"Error fetching latest save: {e}")
        return None

    def get_cover_url(self, game):
        """Returns a valid URL for the game cover, preferring local RomM assets."""
        path = game.get('path_cover_large') or game.get('path_cover_small')
        if path:
            return path if path.startswith('http') else f"{self.base_url}{path}"
        url = game.get('url_cover')
        if url:
            # Sometimes IGDB URLs are protocol-relative
            if url.startswith('//'): return f"https:{url}"
            return url
        return None

    def download_rom(self, rom_id, file_name, target_path, progress_callback=None, cancel_flag=None):
        if not self.token: return False
        from urllib.parse import quote
        import time
        encoded_name = quote(file_name)
        url = f"{self.base_url}/api/roms/{rom_id}/content/{encoded_name}"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        try:
            response = requests.get(url, headers=headers, stream=True, timeout=60)
            if response.status_code == 200:
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                start_time = time.time()
                # Optimized for consistent local performance (1MB chunks)
                with open(target_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=1024*1024):
                        if cancel_flag and cancel_flag[0]:
                            f.close()
                            os.remove(target_path)
                            return False
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback and total_size > 0:
                                elapsed = time.time() - start_time
                                speed = downloaded / elapsed if elapsed > 0 else 0
                                progress_callback(downloaded, total_size, speed)
                return True
        except Exception as e:
            print(f"[API] ROM download error: {e}")
        return False

    def get_firmware(self):
        """Fetches all available firmware from RomM, enriching with platform metadata."""
        if not self.token: return []
        url = f"{self.base_url}/api/platforms"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                platforms = response.json()
                firmware_list = []
                for p in platforms:
                    fws = p.get('firmware', [])
                    for f in fws:
                        # Enrich with platform info for filtering/display
                        f['platform_name'] = p.get('name')
                        f['platform_slug'] = p.get('slug')
                        f['platform_id'] = p.get('id')
                        firmware_list.append(f)
                return firmware_list
        except Exception as e:
            print(f"[API] Firmware fetch error: {e}")
        return []

    def download_firmware(self, fw_data, target_path, progress_callback=None):
        """fw_data is the full firmware dict from RomM."""
        if not self.token: return False
        
        # Official API is 403, so we try to build the raw asset path
        # Pattern: /api/raw/assets/firmware/[platform]/[filename]
        # But RomM sometimes puts it in different places.
        # Let's try the download_path if it exists, otherwise build it.
        path = fw_data.get('download_path')
        if not path:
            # Build common asset path for firmware
            slug = fw_data.get('platform_slug', 'unknown')
            name = fw_data.get('file_name')
            path = f"/api/raw/assets/firmware/{slug}/{name}"
            
        url = path if path.startswith('http') else f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        print(f"[API] Downloading BIOS from {url}")
        import time
        try:
            response = requests.get(url, headers=headers, stream=True, timeout=60)
            if response.status_code == 200:
                total = int(response.headers.get('content-length', 0))
                downloaded = 0
                start_time = time.time()
                with open(target_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=512*1024):
                        f.write(chunk); downloaded += len(chunk)
                        if progress_callback:
                            elapsed = time.time() - start_time
                            speed = downloaded / elapsed if elapsed > 0 else 0
                            progress_callback(downloaded, total, speed)
                return True
            else:
                print(f"[API] BIOS download failed: {response.status_code} at {url}")
        except Exception as e:
            print(f"[API] BIOS error: {e}")
        return False

    def get_save_hash(self, save_data):
        """Fetches the ETag/MD5 from the server via a HEAD request."""
        if not self.token: return None
        path = save_data.get('download_path')
        if not path: return None
        
        url = path if path.startswith('http') else f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            # Use HEAD to get headers without downloading the whole file
            response = requests.head(url, headers=headers, timeout=10)
            # RomM/Nginx usually returns ETag or Content-MD5
            etag = response.headers.get('ETag')
            if etag:
                # ETags are often quoted: "hash"
                return etag.strip('"')
        except Exception as e:
            print(f"Error fetching save hash: {e}")
        return None

    def download_save(self, save_data, target_path):
        """save_data is the full dict from RomM."""
        if not self.token: return False
        
        path = save_data.get('download_path')
        if not path: return False
        
        # If path is relative, prefix with base_url
        url = path if path.startswith('http') else f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        print(f"[API] Downloading save from {url}")
        try:
            response = requests.get(url, headers=headers, stream=True, timeout=60)
            if response.status_code == 200:
                with open(target_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True
            else:
                print(f"[API] Download failed: {response.status_code}")
        except Exception as e:
            print(f"[API] Download error: {e}")
        return False

    def upload_save(self, rom_id, emulator, save_path):
        if not self.token: return False, "No token"
        url = f"{self.base_url}/api/saves"
        params = {"rom_id": rom_id, "emulator": emulator, "slot": "argosy-windows"}
        headers = {"Authorization": f"Bearer {self.token}"}
        
        try:
            with open(save_path, 'rb') as f:
                files = {'saveFile': (os.path.basename(save_path), f, 'application/octet-stream')}
                response = requests.post(url, params=params, headers=headers, files=files, timeout=60)
                return response.status_code in [200, 201], response.text
        except Exception as e:
            return False, str(e)
