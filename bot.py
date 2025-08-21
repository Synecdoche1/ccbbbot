#!/usr/bin/env python3
import os
import sys
import traceback
import asyncio
import discord
from flask import Flask
from threading import Thread

# -------------------------
# LOAD CONFIG FROM ENV
# -------------------------
TOKEN = os.getenv("DISCORD_TOKEN")
PORT = int(os.getenv("PORT", 10000))  # Flask server port

if not TOKEN:
    print("❌ DISCORD_TOKEN environment variable not set!")
    sys.exit(1)

print("✅ Config loaded")

# -------------------------
# IMPORT MODULES
# -------------------------
try:
    from modules import revive
    print("✅ revive module imported")
except Exception as e:
    print(f"❌ Failed to import revive module: {e}")
    traceback.print_exc()
    revive = None

# -------------------------
# CREATE DISCORD CLIENT
# -------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
client = discord.Client(intents=intents)

# -------------------------
# COMMAND REGISTRY
# -------------------------
COMMANDS = {}
if revive:
    COMMANDS.update({
        "revives": revive.revives,
        "/revives": revive.revives
    })

# -------------------------
# ON_READY EVENT
# -------------------------
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")
    print(f"✅ Bot is in {len(client.guilds)} guilds")
    for guild in client.guilds:
        print(f"   - {guild.name} (ID: {guild.id})")

# -------------------------
# ON_MESSAGE EVENT
# -------------------------
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    should_process = client.user in message.mentions or isinstance(message.channel, discord.DMChannel)
    if not should_process:
        return

    content_lower = message.content.lower().strip()
    # Remove bot mentions
    mention_str = f"<@{client.user.id}>"
    mention_str_nick = f"<@!{client.user.id}>"
    content_lower = content_lower.replace(mention_str, "").replace(mention_str_nick, "").strip()

    # Check registered commands
    for cmd_name, cmd_func in COMMANDS.items():
        if content_lower.startswith(cmd_name):
            print(f"📥 Command triggered: {cmd_name} by {message.author}")
            await cmd_func(message.channel)
            return

# -------------------------
# FLASK KEEPALIVE SERVER
# -------------------------
app = Flask("")

@app.route("/")
def home():
    return "Bot is running ✅"

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

# -------------------------
# START BOT + FLASK THREAD
# -------------------------
if __name__ == "__main__":
    Thread(target=run_flask).start()
    try:
        client.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Invalid bot token!")
    except KeyboardInterrupt:
        print("👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")
        traceback.print_exc()
