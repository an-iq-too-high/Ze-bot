import os
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

@bot.command()
async def hello(ctx):
    await ctx.send("Hello!")

bot.run(os.getenv("DISCORD_SECRET"))
