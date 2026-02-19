#!/usr/bin/env python3
"""
AppShak Launcher - Simple CLI for running different AppShak environments.

For observers, builders, and QC agents.
"""

import asyncio
import subprocess
import sys
import os

# Ensure we're in the correct directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

processes = {}

async def launch_original():
    """Launch the Original AppShak kernel (core library)."""
    print("Launching Original AppShak (Core Library)...")
    sys.path.insert(0, '.')

    try:
        from appshak import AppShakKernel

        config = {
            "heartbeat_interval": 15,
            "event_poll_timeout": 1.0,
        }

        kernel = AppShakKernel(config)
        await kernel.start()

        print("Original AppShak running. Press Ctrl+C to stop and return to menu.")

        try:
            while kernel.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("Stopping Original AppShak...")
            await kernel.shutdown()
            print("Original AppShak stopped.")

    except ImportError as e:
        print(f"Error importing AppShak: {e}")
        print("Make sure you're running from the AppShak_HQ directory.")

def launch_live():
    """Launch the Live AppShak server."""
    if 'live' in processes and processes['live'].poll() is None:
        print("Live server already running on port 8000")
        return

    print("Starting Live server on port 8000...")
    try:
        p = subprocess.Popen([
            sys.executable, '-m', 'uvicorn',
            'appshak_live.server:app',
            '--host', '0.0.0.0',
            '--port', '8000',
            '--reload'
        ])
        processes['live'] = p
        print("Live server started. Access at http://localhost:8000")
    except Exception as e:
        print(f"Error starting Live server: {e}")

def launch_office():
    """Launch the Office AppShak server."""
    if 'office' in processes and processes['office'].poll() is None:
        print("Office server already running on port 8001")
        return

    print("Starting Office server on port 8001...")
    try:
        p = subprocess.Popen([
            sys.executable, '-m', 'uvicorn',
            'appshak_office.server:app',
            '--host', '0.0.0.0',
            '--port', '8001',
            '--reload'
        ])
        processes['office'] = p
        print("Office server started. Access at http://localhost:8001")
    except Exception as e:
        print(f"Error starting Office server: {e}")

def stop_server(name):
    """Stop a running server."""
    if name in processes and processes[name].poll() is None:
        print(f"Stopping {name.capitalize()} server...")
        processes[name].terminate()
        processes[name].wait()
        print(f"{name.capitalize()} server stopped.")
    else:
        print(f"{name.capitalize()} server not running.")

def print_menu():
    """Print the main menu."""
    print("\n" + "="*50)
    print("         AppShak Launcher")
    print("="*50)
    print("1. Launch Original (Core Library)")
    print("2. Launch Live (WebUI)")
    print("3. Launch Office (Advanced)")
    print()
    print("Server Controls:")
    print("s. Start Live Server")
    print("o. Start Office Server")
    print("x. Stop Live Server")
    print("y. Stop Office Server")
    print()
    print("Other:")
    print("/help - Show detailed help")
    print("q. Quit")
    print("="*50)

def handle_help():
    """Show detailed help."""
    print("\n" + "="*60)
    print("                    AppShak Launcher Help")
    print("="*60)
    print("MAIN COMMANDS:")
    print("1 - Launch Original: Runs the core AppShak kernel directly.")
    print("    This will block until you stop it with Ctrl+C.")
    print()
    print("2 - Launch Live: Starts the Live WebUI server on port 8000.")
    print("    Access dashboard at http://localhost:8000")
    print()
    print("3 - Launch Office: Starts the Office server on port 8001.")
    print("    Access dashboard at http://localhost:8001")
    print()
    print("SERVER CONTROLS:")
    print("s - Start Live server (same as option 2)")
    print("o - Start Office server (same as option 3)")
    print("x - Stop Live server")
    print("y - Stop Office server")
    print()
    print("OTHER:")
    print("/help - Show this help menu")
    print("q - Quit the launcher (stops all running servers)")
    print()
    print("NOTES:")
    print("- Servers run in the background and can be controlled separately")
    print("- Original kernel runs in foreground and blocks the menu")
    print("- Use Ctrl+C to stop the Original kernel and return to menu")
    print("- Make sure dependencies are installed for Live/Office")
    print("="*60)

async def main():
    """Main launcher loop."""
    print("Welcome to AppShak Launcher!")
    print("Type /help for detailed instructions.")

    while True:
        print_menu()
        try:
            cmd = input("> ").strip().lower()
        except KeyboardInterrupt:
            print("\nExiting...")
            break

        if cmd == '1':
            await launch_original()
        elif cmd == '2':
            launch_live()
        elif cmd == '3':
            launch_office()
        elif cmd == 's':
            launch_live()
        elif cmd == 'o':
            launch_office()
        elif cmd == 'x':
            stop_server('live')
        elif cmd == 'y':
            stop_server('office')
        elif cmd == '/help':
            handle_help()
        elif cmd == 'q':
            print("Stopping all servers...")
            for name, p in processes.items():
                if p.poll() is None:
                    p.terminate()
            print("Exiting AppShak Launcher. Goodbye!")
            break
        else:
            print("Invalid command. Type /help for help.")

if __name__ == "__main__":
    asyncio.run(main())