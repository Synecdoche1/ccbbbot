import psutil
import subprocess
import time

BOT_SCRIPT = "bot.py"

def kill_bot():
    """Kill any running bot.py processes."""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['cmdline'] and BOT_SCRIPT in proc.info['cmdline']:
                print(f"Killing bot.py PID: {proc.pid}")
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

def start_bot():
    """Start the bot.py script."""
    print("Starting bot.py...")
    return subprocess.Popen(["python", BOT_SCRIPT])

if __name__ == "__main__":
    while True:
        kill_bot()  # Kill any old instances
        bot_process = start_bot()
        bot_process.wait()  # Wait for bot to exit
        print("Bot stopped. Restarting in 2 seconds...")
        time.sleep(2)
