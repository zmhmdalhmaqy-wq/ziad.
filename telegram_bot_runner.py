#!/usr/bin/env python3
import subprocess
import time

print("Starting Telegram Bot...")
subprocess.Popen(['python3', 'telegram_bot.py'])
print("Bot started in background")

while True:
    time.sleep(60)