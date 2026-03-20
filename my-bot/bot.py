import discord
from discord import app_commands
import aiohttp
import asyncio
import time
from dotenv import load_dotenv
import os

load_dotenv()

TOKEN = os.getenv("MTQzOTg5NTAzMTA4NjMyMTczOA.GcHUFz.w3U4BgyQ-nWUcgTfeZB5x6KRONIR2A6PDhaU-k")

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# ── State ─────────────────────────────────────────────────────────────────────
spam_tasks: dict[int, asyncio.Task] = {}   # channel_id -> task
spam_stats: dict[int, dict] = {}           # channel_id -> stats


# ── Helper: build dashboard embed ────────────────────────────────────────────
def build_embed(stats: dict, running: bool) -> discord.Embed:
    elapsed = int(time.time() - stats["start_time"])
    mins, secs = divmod(elapsed, 60)

    status = "🟢 Running" if running else "🔴 Stopped"
    color  = discord.Color.green() if running else discord.Color.red()

    embed = discord.Embed(title="📨 Message Spammer Dashboard", color=color)
    embed.add_field(name="Status",  value=status,                          inline=True)
    embed.add_field(name="Webhook", value=f"`{stats['webhook'][:40]}...`", inline=True)
    embed.add_field(name="Message", value=f"```{stats['message']}```",     inline=False)
    embed.add_field(name="Sent",    value=str(stats["count"]),             inline=True)
    embed.add_field(name="Elapsed", value=f"{mins}m {secs}s",             inline=True)
    embed.add_field(name="Errors",  value=str(stats["errors"]),            inline=True)
    embed.set_footer(text="Use /stopspm to stop")
    return embed


# ── Background spam loop ──────────────────────────────────────────────────────
async def spam_loop(channel_id: int, dashboard_msg: discord.Message):
    stats = spam_stats[channel_id]

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.post(stats["webhook"], json={"content": stats["message"]}) as r:
                    if r.status == 204:
                        stats["count"] += 1
                    elif r.status == 429:
                        data = await r.json()
                        await asyncio.sleep(data.get("retry_after", 1))
                        continue
                    else:
                        stats["errors"] += 1
            except Exception:
                stats["errors"] += 1

            # Update dashboard every 5 messages
            if stats["count"] % 5 == 0:
                try:
                    await dashboard_msg.edit(embed=build_embed(stats, running=True))
                except Exception:
                    pass

            await asyncio.sleep(1)


# ── /msgspm ───────────────────────────────────────────────────────────────────
@tree.command(name="msgspm", description="Start sending a message repeatedly via webhook")
@app_commands.describe(
    webhook="The Discord webhook URL to send messages to",
    msg="The message to send repeatedly"
)
async def msgspm(interaction: discord.Interaction, webhook: str, msg: str):
    channel_id = interaction.channel_id

    if channel_id in spam_tasks and not spam_tasks[channel_id].done():
        await interaction.response.send_message(
            "⚠️ A spammer is already running in this channel. Use `/stopspm` first.",
            ephemeral=True
        )
        return

    if not webhook.startswith("https://discord.com/api/webhooks/"):
        await interaction.response.send_message(
            "❌ Invalid webhook URL. Must start with `https://discord.com/api/webhooks/`",
            ephemeral=True
        )
        return

    spam_stats[channel_id] = {
        "webhook":    webhook,
        "message":    msg,
        "count":      0,
        "errors":     0,
        "start_time": time.time(),
    }

    await interaction.response.defer()
    dashboard_msg = await interaction.followup.send(
        embed=build_embed(spam_stats[channel_id], running=True)
    )

    task = asyncio.create_task(spam_loop(channel_id, dashboard_msg))
    spam_tasks[channel_id] = task

    def on_done(t):
        asyncio.create_task(
            dashboard_msg.edit(embed=build_embed(spam_stats[channel_id], running=False))
        )

    task.add_done_callback(on_done)


# ── /stopspm ──────────────────────────────────────────────────────────────────
@tree.command(name="stopspm", description="Stop the running message spammer")
async def stopspm(interaction: discord.Interaction):
    channel_id = interaction.channel_id

    if channel_id not in spam_tasks or spam_tasks[channel_id].done():
        await interaction.response.send_message("ℹ️ No spammer is running in this channel.", ephemeral=True)
        return

    spam_tasks[channel_id].cancel()
    await interaction.response.send_message("✅ Spammer stopped.", ephemeral=True)


# ── Ready ─────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {bot.user}")


bot.run(TOKEN)
