import subprocess
import Cocoa  # type: ignore[import-untyped]
import logging

logger = logging.getLogger(__name__)

# Cache to avoid repetitive mdfind calls
_APP_CACHE: dict[str, str] = {}

def get_bundle_id_from_path(app_path: str) -> str | None:
    """Extracts the CFBundleIdentifier from an .app bundle path using NSBundle."""
    bundle = Cocoa.NSBundle.bundleWithPath_(app_path)
    if bundle:
        return bundle.bundleIdentifier()
    return None

def resolve_app_bundle_id(app_name: str) -> str | None:
    """
    Dynamically resolves a localized app name (e.g., '备忘录', '迅雷') to its Bundle ID.
    Uses mdfind for lightning-fast localized name searching.
    """
    app_name = app_name.strip()
    if not app_name:
        return None
        
    cache_key = app_name.lower()
    if cache_key in _APP_CACHE:
        return _APP_CACHE[cache_key]

    # Use mdfind to search by Display Name or File System Name, ignoring case/diacritics
    query = f"kMDItemContentType == 'com.apple.application-bundle' && (kMDItemDisplayName == '*{app_name}*'cd || kMDItemFSName == '*{app_name}*'cd)"
    
    try:
        res = subprocess.run(
            ["mdfind", query], 
            capture_output=True, 
            text=True, 
            check=True
        )
        paths = [p.strip() for p in res.stdout.split('\n') if p.strip()]
        
        if not paths:
            return None
            
        # Heuristic: sort by length to prefer exact matches (e.g. 'Notes.app' over 'VoiceMemos.app' for '备忘录')
        paths.sort(key=len)
        
        best_path = paths[0]
        bundle_id = get_bundle_id_from_path(best_path)
        
        if bundle_id:
            _APP_CACHE[cache_key] = bundle_id
            return bundle_id
            
    except subprocess.CalledProcessError as e:
        logger.error(f"mdfind failed: {e}")
        
    return None
