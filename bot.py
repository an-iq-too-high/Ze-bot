
import os
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# Prefix command: !hello
@bot.command()
async def hello(ctx):
    await ctx.send("Hello!")

# Slash command: /hello
@bot.tree.command(name="hello", description="Say hello to the bot!")
async def hello_slash(interaction: discord.Interaction):
    await interaction.response.send_message("Hello!")

# Register slash commands
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

bot.run(os.getenv("DISCORD_SECRET"))
