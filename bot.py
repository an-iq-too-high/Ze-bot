
import os
import datetime
import discord
from discord.ext import commands
from discord import app_commands

# ==================================
# BOT SETUP
# ==================================

intents = discord.Intents.default()
intents.message_content = True


class SpaceDood(commands.Bot):
    async def setup_hook(self):
        await self.tree.sync()


bot = SpaceDood(
    command_prefix="!",
    intents=intents
)


# ==================================
# MODERATION CHECKS
# ==================================

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

    # DEBUG: Print role information
    print("========== ROLE DEBUG ==========")

    print(
        "SPACE DOOD:",
        bot_member.top_role.name,
        "Position:",
        bot_member.top_role.position
    )

    print(
        "TARGET:",
        target.top_role.name,
        "Position:",
        target.top_role.position
    )

    print(
        "ACTOR:",
        actor.top_role.name,
        "Position:",
        actor.top_role.position
    )

    print("================================")

    # Bot role hierarchy
    if bot_member.top_role <= target.top_role:
        return (
            f"My highest role ({bot_member.top_role.name}) "
            f"is not above {target.display_name}'s highest role "
            f"({target.top_role.name})."
        )

    # Moderator role hierarchy
    if actor.id != guild.owner_id and actor.top_role <= target.top_role:
        return "You can't moderate someone with an equal or higher role."

    return None


# ==================================
# MODERATION FUNCTION
# ==================================

async def moderate(
    guild,
    actor,
    target,
    action,
    reason,
    minutes=None
):

    permission = {
        "kick": "kick_members",
        "ban": "ban_members",
        "timeout": "moderate_members"
    }[action]

    error = check_moderation(
        guild,
        actor,
        target,
        permission
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

            return (
                f"Successfully timed out {target} "
                f"for {minutes} minutes."
            )

    except discord.Forbidden:
        return "Discord denied that action. Check permissions and role hierarchy."

    except discord.HTTPException as error:
        print("Discord API error:", error)
        return "Something went wrong while contacting Discord."


# ==================================
# USERINFO FUNCTION
# ==================================

def create_userinfo_embed(member):

    embed = discord.Embed(
        title=f"User Information: {member}",
        color=discord.Color.blurple()
    )

    embed.set_thumbnail(
        url=member.display_avatar.url
    )

    embed.add_field(
        name="Username",
        value=member.name,
        inline=True
    )

    embed.add_field(
        name="Display Name",
        value=member.display_name,
        inline=True
    )

    embed.add_field(
        name="User ID",
        value=member.id,
        inline=False
    )

    embed.add_field(
        name="Account Created",
        value=discord.utils.format_dt(
            member.created_at,
            style="F"
        ),
        inline=False
    )

    if member.joined_at:
        join_date = discord.utils.format_dt(
            member.joined_at,
            style="F"
        )
    else:
        join_date = "Unknown"

    embed.add_field(
        name="Joined Server",
        value=join_date,
        inline=False
    )

    embed.add_field(
        name="Highest Role",
        value=member.top_role.mention,
        inline=False
    )

    permissions = [
        name.replace("_", " ").title()
        for name, allowed in member.guild_permissions
        if allowed
    ]

    permission_text = ", ".join(permissions)

    if len(permission_text) > 1000:
        permission_text = permission_text[:997] + "..."

    embed.add_field(
        name="Server Permissions",
        value=permission_text or "None",
        inline=False
    )

    embed.set_footer(
        text=f"Requested by {member.guild.me.display_name}"
    )

    return embed


# ==================================
# PREFIX COMMANDS (!)
# ==================================

@bot.command(name="kick")
async def kick_prefix(
    ctx,
    member: discord.Member,
    *,
    reason="No reason provided"
):

    result = await moderate(
        ctx.guild,
        ctx.author,
        member,
        "kick",
        reason
    )

    await ctx.send(result)


@bot.command(name="ban")
async def ban_prefix(
    ctx,
    member: discord.Member,
    *,
    reason="No reason provided"
):

    result = await moderate(
        ctx.guild,
        ctx.author,
        member,
        "ban",
        reason
    )

    await ctx.send(result)


@bot.command(name="timeout")
async def timeout_prefix(
    ctx,
    member: discord.Member,
    minutes: int,
    *,
    reason="No reason provided"
):

    if not 1 <= minutes <= 40320:
        await ctx.send(
            "Timeout must be between 1 and 40320 minutes."
        )
        return

    result = await moderate(
        ctx.guild,
        ctx.author,
        member,
        "timeout",
        reason,
        minutes
    )

    await ctx.send(result)


@bot.command(name="userinfo")
async def userinfo_prefix(
    ctx,
    member: discord.Member = None
):

    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    member = member or ctx.author

    embed = create_userinfo_embed(member)

    await ctx.send(embed=embed)


# ==================================
# SLASH COMMANDS (/)
# ==================================

@bot.tree.command(
    name="kick",
    description="Kick a member"
)
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
        interaction.guild,
        interaction.user,
        member,
        "kick",
        reason
    )

    await interaction.response.send_message(
        result,
        ephemeral=True
    )


@bot.tree.command(
    name="ban",
    description="Ban a member"
)
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
        interaction.guild,
        interaction.user,
        member,
        "ban",
        reason
    )

    await interaction.response.send_message(
        result,
        ephemeral=True
    )


@bot.tree.command(
    name="timeout",
    description="Timeout a member"
)
@app_commands.describe(
    member="The member to timeout",
    minutes="Timeout duration in minutes",
    reason="Why they are being timed out"
)
async def timeout_slash(
    interaction: discord.Interaction,
    member: discord.Member,
    minutes: app_commands.Range[int, 1, 40320],
    reason: str = "No reason provided"
):

    result = await moderate(
        interaction.guild,
        interaction.user,
        member,
        "timeout",
        reason,
        minutes
    )

    await interaction.response.send_message(
        result,
        ephemeral=True
    )


@bot.tree.command(
    name="userinfo",
    description="View information about a server member"
)
@app_commands.describe(
    member="The member to inspect (optional)"
)
async def userinfo_slash(
    interaction: discord.Interaction,
    member: discord.Member = None
):

    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True
        )
        return

    member = member or interaction.user

    embed = create_userinfo_embed(member)

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# ==================================
# BOT EVENTS
# ==================================

@bot.event
async def on_ready():
    print(
        f"Space Dood is online! Logged in as {bot.user}"
    )


# ==================================
# START BOT
# ==================================

token = os.getenv("DISCORD_SECRET")

if not token:
    raise RuntimeError("DISCORD_SECRET is missing!")

bot.run(token)
