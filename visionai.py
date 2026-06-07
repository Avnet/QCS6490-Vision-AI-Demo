#!/usr/bin/env python3

if __name__ == "__main__":
    import os
    import multiprocessing as mp
    from vai.common import (APP_HEADER, TRIA)
    from vai.demo_manager import DemoManager

    try:
        mp.set_start_method('spawn', force=True)
    except RuntimeError:
        # Method might already be set in some environments
        pass
        
    print(TRIA)
    print(f"\nLaunching {APP_HEADER}")
    # Create the video object
    # Add port= if is necessary to use a different one
    video = DemoManager(os.path.dirname(__file__))
    video.localApp()
