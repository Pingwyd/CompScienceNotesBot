"""
Google Drive Service - Connects to Google Drive and fetches files
"""

import os
import time
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class DriveService:
    """Service to interact with Google Drive API"""
    
    def __init__(self):
        """Initialize the Drive service"""
        self.api_key = os.getenv('GOOGLE_API_KEY')
        self.drive_link = os.getenv('GOOGLE_DRIVE_LINK')
        
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment variables!")
        
        if not self.drive_link:
            raise ValueError("GOOGLE_DRIVE_LINK not found in environment variables!")
        
        # Extract folder ID from the drive link
        self.folder_id = self._extract_folder_id(self.drive_link)
        
        # Build the Drive service
        self.service = build('drive', 'v3', developerKey=self.api_key)
        
        # Simple in-memory cache: {folder_id: {'files': [], 'timestamp': 0}}
        self._cache = {}
        self._cache_duration = 3600  # 1 hour in seconds
        
        # Global file cache for search (refreshed periodically)
        self._all_files_cache = None
        self._all_files_cache_time = 0
        self._all_files_cache_duration = 1800  # 30 minutes

    def _extract_folder_id(self, drive_link):
        """Extract folder ID from Google Drive link"""
        # Example link: https://drive.google.com/drive/folders/ABC123XYZ
        if '/folders/' in drive_link:
            folder_id = drive_link.split('/folders/')[-1]
            # Remove any query parameters
            folder_id = folder_id.split('?')[0]
            return folder_id
        else:
            # Maybe it's already an ID?
            if len(drive_link) > 20 and '/' not in drive_link:
                return drive_link
            raise ValueError(f"Invalid Google Drive link: {drive_link}")

    def list_files(self, folder_id=None, page_size=20, use_cache=True, max_retries=3):
        """
        List files in a folder with caching and retry logic
        
        Args:
            folder_id: ID of the folder to list (defaults to root folder)
            page_size: Number of files to return
            use_cache: Whether to use cached results
            max_retries: Maximum number of retry attempts for API errors
            
        Returns:
            List of file dictionaries
        """
        if folder_id is None:
            folder_id = self.folder_id
            
        # Check cache
        if use_cache and folder_id in self._cache:
            cached_data = self._cache[folder_id]
            if time.time() - cached_data['timestamp'] < self._cache_duration:
                print(f"Using cached data for folder {folder_id}")
                return cached_data['files']
        
        # Retry logic for API errors
        for attempt in range(max_retries):
            try:
                # Query to get files in the folder
                query = f"'{folder_id}' in parents and trashed=false"
                
                results = self.service.files().list(
                    q=query,
                    pageSize=page_size,
                    fields="files(id, name, mimeType, size, modifiedTime, webViewLink)",
                    orderBy="folder,name"  # Folders first, then alphabetically
                ).execute()
                
                files = results.get('files', [])
                
                # Update cache
                self._cache[folder_id] = {
                    'files': files,
                    'timestamp': time.time()
                }
                
                return files
                
            except HttpError as error:
                error_code = error.resp.status
                error_reason = error.error_details[0].get('reason', 'unknown') if error.error_details else 'unknown'
                
                # Retry on 500 (Internal Error) or 503 (Service Unavailable)
                if error_code in [500, 503] and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # Exponential backoff: 2s, 4s, 6s
                    print(f"API Error {error_code} ({error_reason}). Retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"An error occurred: {error}")
                    # Return cached data if available, even if expired
                    if folder_id in self._cache:
                        print(f"Returning stale cached data for folder {folder_id}")
                        return self._cache[folder_id]['files']
                    return []
            except Exception as e:
                print(f"Unexpected error: {e}")
                # Return cached data if available
                if folder_id in self._cache:
                    print(f"Returning stale cached data for folder {folder_id}")
                    return self._cache[folder_id]['files']
                return []
        
        # If all retries failed
        print(f"All retry attempts failed for folder {folder_id}")
        if folder_id in self._cache:
            print(f"Returning stale cached data")
            return self._cache[folder_id]['files']
        return []
    
    def get_file_info(self, file_id, max_retries=3):
        """Get detailed information about a file with retry logic"""
        for attempt in range(max_retries):
            try:
                file = self.service.files().get(
                    fileId=file_id,
                    fields="id, name, mimeType, size, modifiedTime, webViewLink, webContentLink"
                ).execute()
                return file
            except HttpError as error:
                error_code = error.resp.status
                if error_code in [500, 503] and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    print(f"API Error {error_code}. Retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"An error occurred: {error}")
                    return None
            except Exception as e:
                print(f"Unexpected error: {e}")
                return None
        return None

    def download_file(self, file_id, max_retries=3):
        """
        Download a file's content with retry logic
        
        Args:
            file_id: ID of the file to download
            max_retries: Maximum retry attempts
            
        Returns:
            BytesIO object containing the file content
        """
        from io import BytesIO
        from googleapiclient.http import MediaIoBaseDownload
        
        for attempt in range(max_retries):
            try:
                request = self.service.files().get_media(fileId=file_id)
                file_content = BytesIO()
                downloader = MediaIoBaseDownload(file_content, request)
                
                done = False
                while done is False:
                    status, done = downloader.next_chunk()
                    
                file_content.seek(0)
                return file_content
                
            except HttpError as error:
                error_code = error.resp.status
                if error_code in [500, 503] and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    print(f"Download Error {error_code}. Retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"An error occurred downloading file: {error}")
                    return None
            except Exception as e:
                print(f"Unexpected download error: {e}")
                return None
        return None

    def search_files(self, query_text, page_size=20):
        """
        Search for files by name (client-side filtering with caching)
        
        Note: API keys don't support search operations, so we fetch all files
        and filter locally. Uses a cache to avoid repeated scans.
        
        Args:
            query_text: Text to search for in file names
            page_size: Number of results to return
            
        Returns:
            List of file dictionaries
        """
        import time
        
        try:
            # Check if we have a recent cache
            current_time = time.time()
            if (self._all_files_cache is not None and 
                current_time - self._all_files_cache_time < self._all_files_cache_duration):
                print(f"Using cached file list for search (age: {int(current_time - self._all_files_cache_time)}s)")
                all_files = self._all_files_cache
            else:
                # Refresh cache
                print("Refreshing file cache for search...")
                all_files = self._get_all_files_recursive(self.folder_id)
                self._all_files_cache = all_files
                self._all_files_cache_time = current_time
                print(f"Cache refreshed with {len(all_files)} files")
            
            # Filter by query (case-insensitive)
            query_lower = query_text.lower()
            matching_files = [
                file for file in all_files
                if query_lower in file.get('name', '').lower()
            ]
            
            # Sort by modified time (newest first)
            matching_files.sort(
                key=lambda x: x.get('modifiedTime', ''),
                reverse=True
            )
            
            # Limit results
            return matching_files[:page_size]
            
        except Exception as error:
            print(f"An error occurred searching: {error}")
            return []
    
    def invalidate_cache(self):
        """Invalidate all caches - call when you know files have changed"""
        self._cache.clear()
        self._all_files_cache = None
        self._all_files_cache_time = 0
        print("All caches invalidated")
    
    def _get_all_files_recursive(self, folder_id, path="", depth=0, max_depth=10):
        """
        Recursively get all files from a folder
        
        Args:
            folder_id: Starting folder ID
            path: Current path (for breadcrumb)
            depth: Current recursion depth
            max_depth: Maximum recursion depth to prevent infinite loops
            
        Returns:
            List of all files with path info
        """
        all_files = []
        
        if depth > max_depth:
            print(f"Warning: Max depth {max_depth} reached at path: {path}")
            return all_files
        
        try:
            files = self.list_files(folder_id, page_size=1000, use_cache=True)
            
            for file in files:
                # Add path info
                file['path'] = path
                all_files.append(file)
                
                # Recurse into folders
                if self.is_folder(file):
                    new_path = f"{path}/{file['name']}" if path else file['name']
                    subfolder_files = self._get_all_files_recursive(
                        file['id'], new_path, depth + 1, max_depth
                    )
                    all_files.extend(subfolder_files)
            
            return all_files
        except Exception as e:
            print(f"Error getting files recursively: {e}")
            return all_files
    
    def is_folder(self, file):
        """Check if a file is a folder"""
        return file.get('mimeType') == 'application/vnd.google-apps.folder'
    
    def format_file_size(self, size_bytes):
        """Format file size in human-readable format"""
        if not size_bytes:
            return "N/A"
        
        size_bytes = int(size_bytes)
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        
        return f"{size_bytes:.1f} TB"
