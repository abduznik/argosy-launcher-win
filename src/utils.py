import hashlib
import zipfile
import os
from pathlib import Path

def calculate_file_hash(file_path):
    md5 = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5.update(chunk)
    return md5.hexdigest()

def calculate_folder_hash(folder_path):
    """
    Calculates a content-based hash of a folder.
    Matches RomM/Argosy logic: sorted list of 'name:md5' lines.
    """
    folder = Path(folder_path)
    if not folder.exists(): return None
    
    entries = []
    for file in folder.rglob('*'):
        if file.is_file():
            file_hash = calculate_file_hash(file)
            # Use name relative to parent to include the folder name itself in the hash
            entry_name = file.relative_to(folder.parent).as_posix()
            entries.append(f"{entry_name}:{file_hash}")
    
    entries.sort()
    combined = "\n".join(entries)
    return hashlib.md5(combined.encode('utf-8')).hexdigest()

def calculate_zip_content_hash(zip_path):
    """
    Calculates a content-based hash of the files INSIDE a ZIP.
    Allows comparing a server ZIP to a local folder without binary-matching the ZIP container.
    """
    if not os.path.exists(zip_path): return None
    
    entries = []
    with zipfile.ZipFile(zip_path, 'r') as z:
        for info in z.infolist():
            if not info.is_dir():
                # Read file content from zip and hash it
                with z.open(info) as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()
                # entry name matches the one in calculate_folder_hash
                entries.append(f"{info.filename}:{file_hash}")
    
    entries.sort()
    combined = "\n".join(entries)
    return hashlib.md5(combined.encode('utf-8')).hexdigest()

def zip_path(source_path, output_zip):
    source = Path(source_path)
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        if source.is_file():
            zipf.write(source, source.name)
        else:
            for file in source.rglob('*'):
                if file.is_file():
                    arcname = file.relative_to(source.parent).as_posix()
                    zipf.write(file, arcname)
    return output_zip
