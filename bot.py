

import os
import datetime
import discord
from discord.ext import commands
from discord import app_commands

# Bot setup
intents = discord.Intents.default()
intents.message_content = True


class SpaceDood(commands.Bot):
    async def setup_hook(self):
        await self.tree.sync()


bot = SpaceDood(
    command_prefix="!",
    intents=intents
)


# Check whether a moderation action is allowed
def check_moderation(guild, actor, target, permission):
    if guild is None:
        return "This command can only be used in a server."

    if not getattr(actor.guild_permissions, permission):
        return "You don't have permission to do that."

    if target.id == actor.id:
        return "You can't moderate yourself!"

    if target.id == guild.owner_id:
        return "You can't moderate the server owner."

    bot_member = guild.me

    if bot_member is None:
        return "I couldn't find my own server member."

    if not getattr(bot_member.guild_permissions, permission):
        return "I don't have the required server permission."

    if bot_member.top_role <= target.top_role:
        return "That member's role is higher than or equal to mine."

    if actor.id != guild.owner_id and actor.top_role <= target.top_role:
        return "You can't moderate someone with an equal or higher role."

    return None


# Perform moderation actions
async def moderate(guild, actor, target, action, reason,
                   minutes=None):

    permission = {
        "kick": "kick_members",
        "ban": "ban_members",
        "timeout": "moderate_members"
    }[action]

    error = check_moderation(
        guild, actor, target, permission
    )

    if error:
        return error

    try:
        if action == "kick":
            await target.kick(reason=reason)
            return f"Successfully kicked {target}."

        elif action == "ban":
            await target.ban(reason=reason)
            return f"Successfully banned {target}."

        elif action == "timeout":
            await target.timeout(
                datetime.timedelta(minutes=minutes),
                reason=reason
            )
            return f"Successfully timed out {target} for {minutes} minutes."

    except discord.Forbidden:
        return "Discord denied that action. Check my permissions and role."

    except discord.HTTPException:
        return "Something went wrong while contacting Discord."


# ==================================
# PREFIX COMMANDS (!)
# ==================================

@bot.command(name="kick")
async def kick_prefix(ctx, member: discord.Member,
                      *, reason="No reason provided"):

    result = await moderate(
        ctx.guild, ctx.author, member,
        "kick", reason
    )

    await ctx.send(result)


@bot.command(name="ban")
async def ban_prefix(ctx, member: discord.Member,
                     *, reason="No reason provided"):

    result = await moderate(
        ctx.guild, ctx.author, member,
        "ban", reason
    )

    await ctx.send(result)


@bot.command(name="timeout")
async def timeout_prefix(ctx, member: discord.Member,
                         minutes: int,
                         *, reason="No reason provided"):

    if not 1 <= minutes <= 40320:
        await ctx.send("Timeout must be between 1 and 40320 minutes.")
        return

    result = await moderate(
        ctx.guild, ctx.author, member,
        "timeout", reason, minutes
    )

    await ctx.send(result)


# ==================================
# SLASH COMMANDS (/)
# ==================================

@bot.tree.command(name="kick", description="Kick a member")
@app_commands.describe(
    member="The member to kick",
    reason="Why they are being kicked"
)
async def kick_slash(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "No reason provided"
):

    result = await moderate(
        interaction.guild, interaction.user, member,
        "kick", reason
    )

    await interaction.response.send_message(
        result, ephemeral=True
    )


@bot.tree.command(name="ban", description="Ban a member")
@app_commands.describe(
    member="The member to ban",
    reason="Why they are being banned"
)
async def ban_slash(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "No reason provided"
):

    result = await moderate(
        interaction.guild, interaction.user, member,
        "ban", reason
    )

    await interaction.response.send_message(
        result, ephemeral=True
    )


@bot.tree.command(name="timeout", description="Timeout a member")
@app_commands.describe(
    member="The member to timeout",
    minutes="Timeout duration in minutes (1–40320)",
    reason="Why they are being timed out"
)
async def timeout_slash(
    interaction: discord.Interaction,
    member: discord.Member,
    minutes: app_commands.Range[int, 1, 40320],
    reason: str = "No reason provided"
):

    result = await moderate(
        interaction.guild, interaction.user, member,
        "timeout", reason, minutes
    )

    await interaction.response.send_message(
        result, ephemeral=True
    )


# ==================================
# BOT EVENTS
# ==================================

@bot.event
async def on_ready():
    print(f"Space Dood is online! Logged in as {bot.user}")


# Start bot
token = os.getenv("DISCORD_SECRET")

if not token:
    raise RuntimeError("DISCORD_SECRET is missing!")

bot.run(token)
