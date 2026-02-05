#!/usr/bin/env python3
"""
watch-memory.py - Auto-sync Chitta graph when MEMORY.md or IDENTITY.md changes.

Uses Python watchdog library to monitor file changes and trigger sync-chitta.py.
Runs the sync function internally to avoid subprocess overhead.
"""

import sys
import time
import os

# Add chitta directory to path for imports
CHITTA_DIR = "/Users/VedicRGI_Worker/chitta"
WORKSPACE_DIR = os.path.expanduser("~/.openclaw/workspace")
sys.path.insert(0, CHITTA_DIR)

# Check if watchdog is installed
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("Installing watchdog...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "--user", "watchdog"], check=True)
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler


class MemoryChangeHandler(FileSystemEventHandler):
    """Handle file change events for MEMORY.md and IDENTITY.md."""
    
    def __init__(self):
        self.last_sync = 0
        self.debounce_seconds = 5  # Don't sync more than once per 5 seconds
    
    def on_modified(self, event):
        if event.is_directory:
            return
        
        filename = os.path.basename(event.src_path)
        if filename in ["MEMORY.md", "IDENTITY.md"]:
            now = time.time()
            if now - self.last_sync < self.debounce_seconds:
                print(f"[Watcher] Debouncing {filename} change...")
                return
            
            self.last_sync = now
            print(f"[Watcher] {filename} changed, syncing Chitta graph...")
            self.sync_chitta()
    
    def sync_chitta(self):
        """Run sync-chitta.py to update the graph."""
        try:
            import subprocess
            result = subprocess.run(
                ["python3", f"{CHITTA_DIR}/sync-chitta.py"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=CHITTA_DIR
            )
            if result.returncode == 0:
                print(f"[Watcher] Sync complete!")
                # Print summary line from output
                for line in result.stdout.split("\n"):
                    if "Complete!" in line or "Contexts:" in line:
                        print(f"[Watcher] {line}")
            else:
                print(f"[Watcher] Sync error: {result.stderr}")
        except Exception as e:
            print(f"[Watcher] Sync exception: {e}")


def main():
    print(f"""
╔═══════════════════════════════════════════════════════════╗
║           Chitta Memory Watcher                           ║
║                                                           ║
║  Watching: {WORKSPACE_DIR}
║  Files: MEMORY.md, IDENTITY.md                            ║
║  Action: Auto-sync Chitta graph on change                 ║
╚═══════════════════════════════════════════════════════════╝
""")
    
    if not os.path.exists(WORKSPACE_DIR):
        print(f"[Watcher] Error: Workspace directory not found: {WORKSPACE_DIR}")
        sys.exit(1)
    
    event_handler = MemoryChangeHandler()
    observer = Observer()
    observer.schedule(event_handler, WORKSPACE_DIR, recursive=False)
    observer.start()
    
    print(f"[Watcher] Started watching {WORKSPACE_DIR}")
    print("[Watcher] Press Ctrl+C to stop")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Watcher] Stopping...")
        observer.stop()
    
    observer.join()
    print("[Watcher] Stopped")


if __name__ == "__main__":
    main()
