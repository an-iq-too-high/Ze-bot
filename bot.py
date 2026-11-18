import os
import json
import random
import datetime
import aiohttp
import discord
from discord.ext import commands
from discord import app_commands

# ==================================
# BOT SETUP
# ==================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class SpaceDood(commands.Bot):
    async def setup_hook(self):
        self.add_view(TicketPanelView())
        self.add_view(TicketCloseView())
        await self.tree.sync()


bot = SpaceDood(
    command_prefix="!",
    intents=intents
)


# ==================================
# CURRENCY DATABASE
# ==================================

CURRENCY_FILE = "currency.json"


def load_currency():
    if not os.path.exists(CURRENCY_FILE):
        return {}

    try:
        with open(CURRENCY_FILE, "r") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}


currency_data = load_currency()


def save_currency():
    temporary_file = CURRENCY_FILE + ".tmp"

    with open(temporary_file, "w") as file:
        json.dump(currency_data, file, indent=4)

    os.replace(temporary_file, CURRENCY_FILE)


def get_account(guild_id, user_id):
    server = str(guild_id)
    user = str(user_id)

    if server not in currency_data:
        currency_data[server] = {}

    if user not in currency_data[server]:
        currency_data[server][user] = {
            "balance": 100,
            "last_daily": None
        }

        save_currency()

    return currency_data[server][user]


def add_money(guild_id, user_id, amount):
    account = get_account(guild_id, user_id)
    account["balance"] += amount
    save_currency()


# ==================================
# TICKET CONFIGURATION DATABASE
# ==================================

TICKET_FILE = "ticket_config.json"


def load_ticket_config():
    if not os.path.exists(TICKET_FILE):
        return {}

    try:
        with open(TICKET_FILE, "r") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}


ticket_data = load_ticket_config()


def save_ticket_config():
    temporary_file = TICKET_FILE + ".tmp"

    with open(temporary_file, "w") as file:
        json.dump(ticket_data, file, indent=4)

    os.replace(temporary_file, TICKET_FILE)


def get_ticket_config(guild_id):
    server_id = str(guild_id)

    if server_id not in ticket_data:
        ticket_data[server_id] = {
            "staff_roles": [],
            "category_id": None
        }
        save_ticket_config()

    config = ticket_data[server_id]

    config.setdefault("staff_roles", [])
    config.setdefault("category_id", None)

    return config


def get_ticket_staff_roles(guild):
    config = get_ticket_config(guild.id)

    roles = []

    for role_id in config["staff_roles"]:
        role = guild.get_role(int(role_id))

        if role is not None:
            roles.append(role)

    return roles


def is_ticket_staff(member):
    if member.guild is None:
        return False

    staff_roles = get_ticket_staff_roles(member.guild)

    return any(
        role in member.roles
        for role in staff_roles
    )


def can_manage_ticket_settings(member):
    return (
        member.guild is not None
        and member.guild_permissions.manage_guild
    )


# ==================================
# GREETING CONFIGURATION DATABASE
# ==================================

GREET_FILE = "greet_config.json"


def load_greet_config():
    if not os.path.exists(GREET_FILE):
        return {}

    try:
        with open(GREET_FILE, "r") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}


greet_data = load_greet_config()


def save_greet_config():
    temporary_file = GREET_FILE + ".tmp"

    with open(temporary_file, "w") as file:
        json.dump(greet_data, file, indent=4)

    os.replace(temporary_file, GREET_FILE)


def get_greet_config(guild_id):
    server_id = str(guild_id)

    if server_id not in greet_data:
        greet_data[server_id] = {
            "channel_id": None,
            "message": "Welcome {member} to {server}! You are member #{membercount}!"
        }

        save_greet_config()

    config = greet_data[server_id]

    config.setdefault("channel_id", None)
    config.setdefault(
        "message",
        "Welcome {member} to {server}! You are member #{membercount}!"
    )

    return config


def format_greeting(member, message):
    return (
        message
        .replace("{server}", member.guild.name)
        .replace("{member}", member.mention)
        .replace(
            "{membercount}",
            str(member.guild.member_count or len(member.guild.members))
        )
    )


# ==================================
# TICKET CATEGORY
# ==================================

async def get_ticket_category(guild):
    config = get_ticket_config(guild.id)

    category = None

    if config["category_id"]:
        category = guild.get_channel(
            int(config["category_id"])
        )

    if category is None:
        category = discord.utils.get(
            guild.categories,
            name="Space Dood Tickets"
        )

    if category is None:

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            )
        }

        bot_member = guild.me

        if bot_member:
            overwrites[bot_member] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                read_message_history=True
            )

        for role in get_ticket_staff_roles(guild):
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

        category = await guild.create_category(
            "Space Dood Tickets",
            overwrites=overwrites
        )

    config["category_id"] = category.id
    save_ticket_config()

    return category


# ==================================
# TICKET CHANNEL CREATION
# ==================================

async def create_ticket_channel(guild, member):

    category = await get_ticket_category(guild)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False
        ),

        member: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True
        )
    }

    bot_member = guild.me

    if bot_member:
        overwrites[bot_member] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_channels=True,
            read_message_history=True
        )

    for role in get_ticket_staff_roles(guild):
        overwrites[role] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True
        )

    username = member.name.lower().replace(" ", "-")
    username = "".join(
        character
        for character in username
        if character.isalnum() or character == "-"
    )

    channel = await guild.create_text_channel(
        name=f"ticket-{username[:30]}",
        category=category,
        overwrites=overwrites,
        topic=f"SpaceDoodTicket|owner={member.id}|status=open"
    )

    embed = discord.Embed(
        title="🎫 Ticket Created!",
        description=(
            f"Hello {member.mention}!\n\n"
            "Please describe what you need help with.\n"
            "A staff member will be with you shortly."
        ),
        color=discord.Color.red()
    )

    await channel.send(
        content=member.mention,
        embed=embed,
        view=TicketCloseView()
    )

    return channel


# ==================================
# TICKET PERMISSION UPDATES
# ==================================

async def update_ticket_role_permissions(guild, role, adding):

    category = await get_ticket_category(guild)

    if adding:
        overwrite = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True
        )

        await category.set_permissions(
            role,
            overwrite=overwrite
        )

    else:
        await category.set_permissions(
            role,
            overwrite=None
        )

    for channel in category.text_channels:

        if adding:
            overwrite = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )

            await channel.set_permissions(
                role,
                overwrite=overwrite
            )

        else:
            await channel.set_permissions(
                role,
                overwrite=None
            )


# ==================================
# TICKET CLOSING
# ==================================

def get_ticket_owner_id(channel):

    if not channel.topic:
        return None

    for part in channel.topic.split("|"):
        if part.startswith("owner="):
            try:
                return int(part.replace("owner=", ""))
            except ValueError:
                return None

    return None


def is_ticket_closed(channel):

    if not channel.topic:
        return False

    return "status=closed" in channel.topic


async def close_ticket_channel(guild, actor, channel):

    if not isinstance(channel, discord.TextChannel):
        return False, "This is not a text channel."

    owner_id = get_ticket_owner_id(channel)

    if owner_id is None:
        return False, "This channel is not a Space Dood ticket."

    if is_ticket_closed(channel):
        return False, "This ticket is already closed."

    is_owner = actor.id == owner_id
    is_staff = is_ticket_staff(actor)

    if not is_owner and not is_staff:
        return False, "You don't have permission to close this ticket."

    owner = guild.get_member(owner_id)

    if owner is not None:
        await channel.set_permissions(
            owner,
            view_channel=True,
            send_messages=False,
            read_message_history=True
        )

    new_topic = f"SpaceDoodTicket|owner={owner_id}|status=closed"

    await channel.edit(
        name=f"closed-{channel.name}"[:100],
        topic=new_topic
    )

    return True, "🔒 Ticket closed successfully!"


# ==================================
# TICKET PANEL VIEW
# ==================================

class TicketPanelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Press me!",
        style=discord.ButtonStyle.secondary,
        custom_id="space_dood:open_ticket"
    )
    async def open_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if interaction.guild is None:
            await interaction.response.send_message(
                "Tickets can only be opened in a server.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            channel = await create_ticket_channel(
                interaction.guild,
                interaction.user
            )

            await interaction.followup.send(
                f"🎫 Your ticket has been created: {channel.mention}",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have permission to create ticket channels. "
                "Check my Manage Channels permission.",
                ephemeral=True
            )

        except discord.HTTPException as error:
            print("Ticket creation error:", error)

            await interaction.followup.send(
                "Something went wrong while creating your ticket.",
                ephemeral=True
            )


# ==================================
# TICKET CLOSE VIEW
# ==================================

class TicketCloseView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="space_dood:close_ticket"
    )
    async def close_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if interaction.guild is None:
            await interaction.response.send_message(
                "This button can only be used in a server.",
                ephemeral=True
            )
            return

        success, message = await close_ticket_channel(
            interaction.guild,
            interaction.user,
            interaction.channel
        )

        if success:
            await interaction.response.edit_message(
                content="🔒 This ticket has been closed.",
                embed=None,
                view=None
            )
        else:
            await interaction.response.send_message(
                message,
                ephemeral=True
            )


# ==================================
# TICKET PANEL EMBED
# ==================================

def create_ticket_panel():

    embed = discord.Embed(
        title="Tickets!",
        description="Press the black button to register a ticket!",
        color=discord.Color.red()
    )

    return embed


# ==================================
# CURRENCY FUNCTIONS
# ==================================

async def check_balance(guild, member):

    if guild is None:
        return "This command can only be used in a server."

    account = get_account(guild.id, member.id)

    return (
        f"💰 **{member.display_name}'s balance:** "
        f"{account['balance']:,} SC"
    )


async def claim_daily(guild, member):

    if guild is None:
        return "This command can only be used in a server."

    account = get_account(guild.id, member.id)

    now = datetime.datetime.now(datetime.timezone.utc)

    if account["last_daily"]:

        last_daily = datetime.datetime.fromisoformat(
            account["last_daily"]
        )

        if now - last_daily < datetime.timedelta(days=1):
            remaining = datetime.timedelta(days=1) - (
                now - last_daily
            )

            hours = int(remaining.total_seconds() // 3600)
            minutes = int(
                (remaining.total_seconds() % 3600) // 60
            )

            return (
                f"⏳ You've already claimed your daily reward!\n"
                f"Come back in **{hours}h {minutes}m**."
            )

    reward = 100

    account["balance"] += reward
    account["last_daily"] = now.isoformat()

    save_currency()

    return f"🎁 You claimed **{reward} SC**!"


async def work(guild, member):

    if guild is None:
        return "This command can only be used in a server."

    reward = random.randint(20, 75)

    add_money(guild.id, member.id, reward)

    return f"💼 You worked and earned **{reward} SC**!"


async def pay_member(guild, sender, receiver, amount):

    if guild is None:
        return "This command can only be used in a server."

    if receiver.bot:
        return "You can't send money to bots!"

    if sender.id == receiver.id:
        return "You can't send money to yourself!"

    if amount <= 0:
        return "The amount must be greater than zero."

    sender_account = get_account(guild.id, sender.id)
    receiver_account = get_account(guild.id, receiver.id)

    if sender_account["balance"] < amount:
        return "You don't have enough SC!"

    sender_account["balance"] -= amount
    receiver_account["balance"] += amount

    save_currency()

    return (
        f"💸 {sender.mention} sent **{amount:,} SC** "
        f"to {receiver.mention}!"
    )


# ==================================
# LEADERBOARD
# ==================================

def create_leaderboard(guild):

    server = currency_data.get(str(guild.id), {})

    if not server:
        return None

    sorted_users = sorted(
        server.items(),
        key=lambda item: item[1]["balance"],
        reverse=True
    )

    embed = discord.Embed(
        title=f"🏆 {guild.name} Leaderboard",
        color=discord.Color.gold()
    )

    medals = ["🥇", "🥈", "🥉"]
    lines = []

    for position, (user_id, account) in enumerate(
        sorted_users[:10],
        start=1
    ):

        medal = (
            medals[position - 1]
            if position <= 3
            else f"**{position}.**"
        )

        lines.append(
            f"{medal} <@{user_id}> — "
            f"**{account['balance']:,} SC**"
        )

    embed.description = "\n".join(lines)

    embed.set_footer(
        text="Space Dood Economy"
    )

    return embed


# ==================================
# CAT AND DOG IMAGE FUNCTIONS
# ==================================

async def get_animal_image(animal):

    urls = {
        "cat": "https://api.thecatapi.com/v1/images/search",
        "dog": "https://dog.ceo/api/breeds/image/random"
    }

    try:

        timeout = aiohttp.ClientTimeout(total=15)

        async with aiohttp.ClientSession() as session:

            async with session.get(
                urls[animal],
                timeout=timeout
            ) as response:

                if response.status != 200:
                    return None

                data = await response.json()

                if animal == "cat":
                    return data[0]["url"]

                return data["message"]

    except (
        aiohttp.ClientError,
        KeyError,
        IndexError,
        ValueError,
        TimeoutError
    ):
        return None


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

    if bot_member.top_role <= target.top_role:
        return (
            f"My highest role ({bot_member.top_role.name}) "
            f"is not above {target.display_name}'s highest role "
            f"({target.top_role.name})."
        )

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
# WARN FUNCTION
# ==================================

async def warn_member(guild, actor, target, reason):

    if guild is None:
        return "This command can only be used in a server."

    if not actor.guild_permissions.manage_messages:
        return "You need the Manage Messages permission to warn members."

    if target.id == actor.id:
        return "You can't warn yourself!"

    if target.bot:
        return "You can't warn a bot!"

    try:

        await target.send(
            f"⚠️ **You've received a warning in {guild.name}!**\n\n"
            f"**Reason:** {reason}\n"
            f"**Moderator:** {actor}"
        )

        return f"⚠️ Successfully warned {target.mention}. Their DM was sent!"

    except discord.Forbidden:
        return (
            f"⚠️ {target.mention} was not warned because "
            "I couldn't DM them. They may have DMs disabled."
        )

    except discord.HTTPException as error:
        print("Warning DM error:", error)
        return "Something went wrong while trying to send the warning DM."


# ==================================
# JOKE FUNCTION
# ==================================

JOKES = [
    "Why did the computer go to the doctor? Because it had a virus! 💻",
    "Why was the math book sad? It had too many problems! 📚",
    "What do you call a sleeping dinosaur? A dino-snore! 🦖",
    "Why did the developer go broke? Because they used up all their cache! 💸",
    "What do computers eat for a snack? Microchips! 🍟",
    "Why did the programmer quit their job? They didn't get arrays! 😂",
    "What is a computer's favorite music? Anything with a good byte! 🎵"
]


def get_joke():
    return random.choice(JOKES)


# ==================================
# POLL FUNCTION
# ==================================

async def create_poll(
    channel,
    question,
    answer1,
    answer2,
    answer3=None
):

    answers = [
        ("1️⃣", answer1),
        ("2️⃣", answer2)
    ]

    if answer3:
        answers.append(("3️⃣", answer3))

    embed = discord.Embed(
        title="📊 " + question,
        description="React below to vote!",
        color=discord.Color.blurple()
    )

    for emoji, answer in answers:
        embed.add_field(
            name=emoji,
            value=answer,
            inline=False
        )

    embed.set_footer(
        text="Space Dood Poll"
    )

    message = await channel.send(embed=embed)

    for emoji, answer in answers:
        await message.add_reaction(emoji)

    return message


# ==================================
# USERINFO FUNCTION
# ==================================

def create_userinfo_embed(member):

    embed = discord.Embed(
        title=f"User Information: {member}",
        color=discord.Color.blurple()
    )

    embed.set_thumbnail(url=member.display_avatar.url)

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
        value=discord.utils.format_dt(member.created_at, style="F"),
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
        text=f"User ID: {member.id}"
    )

    return embed


# ==================================
# PREFIX TICKET COMMANDS (!)
# ==================================

@bot.command(name="ticketrole")
async def ticketrole_prefix(ctx, action: str, role: discord.Role):

    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    if not can_manage_ticket_settings(ctx.author):
        await ctx.send(
            "You need the Manage Server permission to configure ticket roles."
        )
        return

    config = get_ticket_config(ctx.guild.id)

    if action.lower() == "add":

        if str(role.id) in config["staff_roles"]:
            await ctx.send("That role is already a ticket staff role.")
            return

        try:
            await update_ticket_role_permissions(
                ctx.guild,
                role,
                True
            )

        except discord.Forbidden:
            await ctx.send(
                "I couldn't update that role's ticket permissions. "
                "Check my Manage Channels permission."
            )
            return

        config["staff_roles"].append(str(role.id))
        save_ticket_config()

        await ctx.send(
            f"✅ {role.mention} is now a ticket staff role! "
            "It has access to existing and future tickets."
        )

    elif action.lower() == "remove":

        if str(role.id) not in config["staff_roles"]:
            await ctx.send("That role isn't a ticket staff role.")
            return

        try:
            await update_ticket_role_permissions(
                ctx.guild,
                role,
                False
            )

        except discord.Forbidden:
            await ctx.send(
                "I couldn't remove that role's ticket permissions. "
                "Check my Manage Channels permission."
            )
            return

        config["staff_roles"].remove(str(role.id))
        save_ticket_config()

        await ctx.send(
            f"✅ {role.mention} is no longer a ticket staff role."
        )

    else:
        await ctx.send(
            "Usage: `!ticketrole add @Role` or `!ticketrole remove @Role`"
        )


@bot.command(name="ticketpanel")
@commands.has_guild_permissions(manage_guild=True)
async def ticketpanel_prefix(ctx):

    if ctx.guild is None:
        return

    try:
        await ctx.send(
            embed=create_ticket_panel(),
            view=TicketPanelView()
        )

    except discord.Forbidden:
        await ctx.send(
            "I need permission to send messages and embed links here."
        )


@ticketpanel_prefix.error
async def ticketpanel_prefix_error(ctx, error):

    if isinstance(error, commands.MissingPermissions):
        await ctx.send(
            "You need the Manage Server permission to create a ticket panel."
        )


@bot.command(name="ticketclose")
async def ticketclose_prefix(ctx):

    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    success, message = await close_ticket_channel(
        ctx.guild,
        ctx.author,
        ctx.channel
    )

    await ctx.send(message)


# ==================================
# PREFIX GREETING COMMANDS (!)
# ==================================

@bot.command(name="greet")
@commands.has_guild_permissions(manage_guild=True)
async def greet_prefix(ctx, channel: discord.TextChannel):

    if ctx.guild is None:
        return

    config = get_greet_config(ctx.guild.id)
    config["channel_id"] = channel.id
    save_greet_config()

    await ctx.send(
        f"✅ Greeting channel set to {channel.mention}!"
    )


@greet_prefix.error
async def greet_prefix_error(ctx, error):

    if isinstance(error, commands.MissingPermissions):
        await ctx.send(
            "You need the Manage Server permission to configure greetings."
        )

    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            "Usage: `!greet #channel`"
        )

    elif isinstance(error, commands.BadArgument):
        await ctx.send(
            "Please mention a valid text channel."
        )


@bot.command(name="greetmsg")
@commands.has_guild_permissions(manage_guild=True)
async def greetmsg_prefix(ctx, *, message: str):

    if ctx.guild is None:
        return

    if len(message) > 2000:
        await ctx.send(
            "Your greeting message must be 2000 characters or fewer."
        )
        return

    config = get_greet_config(ctx.guild.id)
    config["message"] = message
    save_greet_config()

    await ctx.send(
        "✅ Greeting message updated!"
    )


@greetmsg_prefix.error
async def greetmsg_prefix_error(ctx, error):

    if isinstance(error, commands.MissingPermissions):
        await ctx.send(
            "You need the Manage Server permission to configure greetings."
        )

    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            "Usage: `!greetmsg Hello {member}, welcome to {server}!`"
        )


# ==================================
# PREFIX COMMANDS (!)
# ==================================

@bot.command(name="kick")
async def kick_prefix(ctx, member: discord.Member, *, reason="No reason provided"):

    result = await moderate(
        ctx.guild, ctx.author, member, "kick", reason
    )

    await ctx.send(result)


@bot.command(name="ban")
async def ban_prefix(ctx, member: discord.Member, *, reason="No reason provided"):

    result = await moderate(
        ctx.guild, ctx.author, member, "ban", reason
    )

    await ctx.send(result)


@bot.command(name="timeout")
async def timeout_prefix(ctx, member: discord.Member, minutes: int, *, reason="No reason provided"):

    if not 1 <= minutes <= 40320:
        await ctx.send("Timeout must be between 1 and 40320 minutes.")
        return

    result = await moderate(
        ctx.guild, ctx.author, member, "timeout", reason, minutes
    )

    await ctx.send(result)


@bot.command(name="warn")
async def warn_prefix(ctx, member: discord.Member, *, reason="No reason provided"):

    result = await warn_member(
        ctx.guild,
        ctx.author,
        member,
        reason
    )

    await ctx.send(result)


@bot.command(name="joke")
async def joke_prefix(ctx):
    await ctx.send(get_joke())


@bot.command(name="poll")
async def poll_prefix(
    ctx,
    question: str,
    answer1: str,
    answer2: str,
    *,
    answer3: str = None
):

    if ctx.guild is None:
        await ctx.send("Polls can only be created in a server.")
        return

    try:
        await create_poll(
            ctx.channel,
            question,
            answer1,
            answer2,
            answer3
        )

    except discord.Forbidden:
        await ctx.send(
            "I need permission to send messages and add reactions here."
        )

    except discord.HTTPException as error:
        print("Poll error:", error)
        await ctx.send("Something went wrong while creating the poll.")


@bot.command(name="say")
async def say_prefix(ctx, *, word: str):

    await ctx.send(
        word,
        allowed_mentions=discord.AllowedMentions.none()
    )


@bot.command(name="userinfo")
async def userinfo_prefix(ctx, member: discord.Member = None):

    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    member = member or ctx.author

    await ctx.send(embed=create_userinfo_embed(member))


@bot.command(name="balance")
async def balance_prefix(ctx):
    await ctx.send(
        await check_balance(ctx.guild, ctx.author)
    )


@bot.command(name="daily")
async def daily_prefix(ctx):
    await ctx.send(
        await claim_daily(ctx.guild, ctx.author)
    )


@bot.command(name="work")
async def work_prefix(ctx):
    await ctx.send(
        await work(ctx.guild, ctx.author)
    )


@bot.command(name="pay")
async def pay_prefix(ctx, member: discord.Member, amount: int):

    result = await pay_member(
        ctx.guild,
        ctx.author,
        member,
        amount
    )

    await ctx.send(result)


@bot.command(name="leaderboard")
async def leaderboard_prefix(ctx):

    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    embed = create_leaderboard(ctx.guild)

    if embed is None:
        await ctx.send("Nobody has earned any Space Coins yet!")
        return

    await ctx.send(embed=embed)


@bot.command(name="cat")
async def cat_prefix(ctx):

    image_url = await get_animal_image("cat")

    if image_url is None:
        await ctx.send("Couldn't find a cat picture. Try again!")
        return

    embed = discord.Embed(
        title="🐱 Here's a cute cat!",
        color=discord.Color.blurple()
    )

    embed.set_image(url=image_url)

    await ctx.send(embed=embed)


@bot.command(name="dog")
async def dog_prefix(ctx):

    image_url = await get_animal_image("dog")

    if image_url is None:
        await ctx.send("Couldn't find a dog picture. Try again!")
        return

    embed = discord.Embed(
        title="🐶 Here's a cute dog!",
        color=discord.Color.blurple()
    )

    embed.set_image(url=image_url)

    await ctx.send(embed=embed)


# ==================================
# SLASH TICKET COMMANDS (/)
# ==================================

@bot.tree.command(
    name="ticketrole",
    description="Add or remove a ticket staff role"
)
@app_commands.describe(
    action="Add or remove the role",
    role="The role to configure"
)
@app_commands.choices(
    action=[
        app_commands.Choice(name="add", value="add"),
        app_commands.Choice(name="remove", value="remove")
    ]
)
async def ticketrole_slash(
    interaction: discord.Interaction,
    action: app_commands.Choice[str],
    role: discord.Role
):

    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True
        )
        return

    if not can_manage_ticket_settings(interaction.user):
        await interaction.response.send_message(
            "You need the Manage Server permission to configure ticket roles.",
            ephemeral=True
        )
        return

    config = get_ticket_config(interaction.guild.id)

    if action.value == "add":

        if str(role.id) in config["staff_roles"]:
            await interaction.response.send_message(
                "That role is already a ticket staff role.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            await update_ticket_role_permissions(
                interaction.guild,
                role,
                True
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "I couldn't update that role's ticket permissions. "
                "Check my Manage Channels permission.",
                ephemeral=True
            )
            return

        config["staff_roles"].append(str(role.id))
        save_ticket_config()

        await interaction.followup.send(
            f"✅ {role.mention} is now a ticket staff role! "
            "It has access to existing and future tickets.",
            ephemeral=True
        )

    elif action.value == "remove":

        if str(role.id) not in config["staff_roles"]:
            await interaction.response.send_message(
                "That role isn't a ticket staff role.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            await update_ticket_role_permissions(
                interaction.guild,
                role,
                False
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "I couldn't remove that role's ticket permissions. "
                "Check my Manage Channels permission.",
                ephemeral=True
            )
            return

        config["staff_roles"].remove(str(role.id))
        save_ticket_config()

        await interaction.followup.send(
            f"✅ {role.mention} is no longer a ticket staff role.",
            ephemeral=True
        )


@bot.tree.command(
    name="ticketpanel",
    description="Create the ticket panel"
)
@app_commands.default_permissions(manage_guild=True)
async def ticketpanel_slash(interaction: discord.Interaction):

    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True
        )
        return

    if not can_manage_ticket_settings(interaction.user):
        await interaction.response.send_message(
            "You need the Manage Server permission to create a ticket panel.",
            ephemeral=True
        )
        return

    try:
        await interaction.channel.send(
            embed=create_ticket_panel(),
            view=TicketPanelView()
        )

        await interaction.response.send_message(
            "🎫 Ticket panel created!",
            ephemeral=True
        )

    except discord.Forbidden:
        await interaction.response.send_message(
            "I need permission to send messages and embed links here.",
            ephemeral=True
        )


@bot.tree.command(
    name="ticketclose",
    description="Close the ticket in this channel"
)
async def ticketclose_slash(interaction: discord.Interaction):

    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True
        )
        return

    success, message = await close_ticket_channel(
        interaction.guild,
        interaction.user,
        interaction.channel
    )

    await interaction.response.send_message(
        message,
        ephemeral=True
    )


# ==================================
# SLASH GREETING COMMANDS (/)
# ==================================

@bot.tree.command(
    name="greet",
    description="Set the channel for member greetings"
)
@app_commands.describe(
    channel="The channel where greetings should be sent"
)
@app_commands.default_permissions(manage_guild=True)
async def greet_slash(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):

    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True
        )
        return

    if not can_manage_ticket_settings(interaction.user):
        await interaction.response.send_message(
            "You need the Manage Server permission to configure greetings.",
            ephemeral=True
        )
        return

    config = get_greet_config(interaction.guild.id)
    config["channel_id"] = channel.id
    save_greet_config()

    await interaction.response.send_message(
        f"✅ Greeting channel set to {channel.mention}!",
        ephemeral=True
    )


@bot.tree.command(
    name="greetmsg",
    description="Set the message sent when someone joins"
)
@app_commands.describe(
    message="Your greeting message. Supports {server}, {member}, and {membercount}"
)
@app_commands.default_permissions(manage_guild=True)
async def greetmsg_slash(
    interaction: discord.Interaction,
    message: str
):

    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True
        )
        return

    if not can_manage_ticket_settings(interaction.user):
        await interaction.response.send_message(
            "You need the Manage Server permission to configure greetings.",
            ephemeral=True
        )
        return

    if len(message) > 2000:
        await interaction.response.send_message(
            "Your greeting message must be 2000 characters or fewer.",
            ephemeral=True
        )
        return

    config = get_greet_config(interaction.guild.id)
    config["message"] = message
    save_greet_config()

    await interaction.response.send_message(
        "✅ Greeting message updated!",
        ephemeral=True
    )


# ==================================
# SLASH COMMANDS (/)
# ==================================

@bot.tree.command(name="kick", description="Kick a member")
@app_commands.describe(member="The member to kick", reason="Why they are being kicked")
async def kick_slash(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):

    result = await moderate(
        interaction.guild, interaction.user, member, "kick", reason
    )

    await interaction.response.send_message(result, ephemeral=True)


@bot.tree.command(name="ban", description="Ban a member")
@app_commands.describe(member="The member to ban", reason="Why they are being banned")
async def ban_slash(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):

    result = await moderate(
        interaction.guild, interaction.user, member, "ban", reason
    )

    await interaction.response.send_message(result, ephemeral=True)


@bot.tree.command(name="timeout", description="Timeout a member")
@app_commands.describe(member="The member to timeout", minutes="Timeout duration in minutes", reason="Why they are being timed out")
async def timeout_slash(interaction: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 40320], reason: str = "No reason provided"):

    result = await moderate(
        interaction.guild, interaction.user, member, "timeout", reason, minutes
    )

    await interaction.response.send_message(result, ephemeral=True)


@bot.tree.command(name="warn", description="DM a warning to a server member")
@app_commands.describe(
    member="The member to warn",
    reason="Why they are receiving a warning"
)
async def warn_slash(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "No reason provided"
):

    result = await warn_member(
        interaction.guild,
        interaction.user,
        member,
        reason
    )

    await interaction.response.send_message(
        result,
        ephemeral=True
    )


@bot.tree.command(name="joke", description="Tell a random joke")
async def joke_slash(interaction: discord.Interaction):

    await interaction.response.send_message(
        get_joke()
    )


@bot.tree.command(name="poll", description="Create a poll")
@app_commands.describe(
    question="The poll question",
    answer1="The first answer",
    answer2="The second answer",
    answer3="The third answer (optional)"
)
async def poll_slash(
    interaction: discord.Interaction,
    question: str,
    answer1: str,
    answer2: str,
    answer3: str = None
):

    if interaction.guild is None:
        await interaction.response.send_message(
            "Polls can only be created in a server.",
            ephemeral=True
        )
        return

    try:

        await create_poll(
            interaction.channel,
            question,
            answer1,
            answer2,
            answer3
        )

        await interaction.response.send_message(
            "📊 Poll created!",
            ephemeral=True
        )

    except discord.Forbidden:
        await interaction.response.send_message(
            "I need permission to send messages and add reactions here.",
            ephemeral=True
        )

    except discord.HTTPException as error:
        print("Poll error:", error)

        await interaction.response.send_message(
            "Something went wrong while creating the poll.",
            ephemeral=True
        )


@bot.tree.command(name="userinfo", description="View information about a server member")
@app_commands.describe(member="The member to inspect (optional)")
async def userinfo_slash(interaction: discord.Interaction, member: discord.Member = None):

    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True
        )
        return

    member = member or interaction.user

    await interaction.response.send_message(
        embed=create_userinfo_embed(member),
        ephemeral=True
    )


@bot.tree.command(name="balance", description="Check your Space Coins")
async def balance_slash(interaction: discord.Interaction):

    result = await check_balance(
        interaction.guild,
        interaction.user
    )

    await interaction.response.send_message(result, ephemeral=True)


@bot.tree.command(name="daily", description="Claim your daily Space Coins")
async def daily_slash(interaction: discord.Interaction):

    result = await claim_daily(
        interaction.guild,
        interaction.user
    )

    await interaction.response.send_message(result, ephemeral=True)


@bot.tree.command(name="work", description="Earn Space Coins by working")
async def work_slash(interaction: discord.Interaction):

    result = await work(
        interaction.guild,
        interaction.user
    )

    await interaction.response.send_message(result, ephemeral=True)


@bot.tree.command(name="pay", description="Send Space Coins to another member")
@app_commands.describe(
    member="Who should receive the coins",
    amount="How many coins to send"
)
async def pay_slash(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: app_commands.Range[int, 1, 1000000000]
):

    result = await pay_member(
        interaction.guild,
        interaction.user,
        member,
        amount
    )

    await interaction.response.send_message(result, ephemeral=True)


@bot.tree.command(
    name="leaderboard",
    description="View the richest members in this server"
)
async def leaderboard_slash(interaction: discord.Interaction):

    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True
        )
        return

    embed = create_leaderboard(interaction.guild)

    if embed is None:
        await interaction.response.send_message(
            "Nobody has earned any Space Coins yet!",
            ephemeral=True
        )
        return

    await interaction.response.send_message(embed=embed)


@bot.tree.command(
    name="cat",
    description="Find a cute cat picture"
)
async def cat_slash(interaction: discord.Interaction):

    await interaction.response.defer()

    image_url = await get_animal_image("cat")

    if image_url is None:
        await interaction.followup.send(
            "Couldn't find a cat picture. Try again!"
        )
        return

    embed = discord.Embed(
        title="🐱 Here's a cute cat!",
        color=discord.Color.blurple()
    )

    embed.set_image(url=image_url)

    await interaction.followup.send(embed=embed)


@bot.tree.command(
    name="dog",
    description="Find a cute dog picture"
)
async def dog_slash(interaction: discord.Interaction):

    await interaction.response.defer()

    image_url = await get_animal_image("dog")

    if image_url is None:
        await interaction.followup.send(
            "Couldn't find a dog picture. Try again!"
        )
        return

    embed = discord.Embed(
        title="🐶 Here's a cute dog!",
        color=discord.Color.blurple()
    )

    embed.set_image(url=image_url)

    await interaction.followup.send(embed=embed)


# ==================================
# BOT EVENTS
# ==================================

@bot.event
async def on_member_join(member):

    config = get_greet_config(member.guild.id)

    channel_id = config.get("channel_id")

    if not channel_id:
        return

    channel = member.guild.get_channel(int(channel_id))

    if channel is None:
        print(
            f"Greeting channel {channel_id} was not found "
            f"in {member.guild.name}."
        )
        return

    message = format_greeting(
        member,
        config["message"]
    )

    try:
        await channel.send(
            message,
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=False,
                everyone=False
            )
        )

    except discord.Forbidden:
        print(
            f"I don't have permission to send greetings in "
            f"#{channel.name}."
        )

    except discord.HTTPException as error:
        print("Greeting error:", error)


@bot.event
async def on_ready():
    print(f"Space Dood is online! Logged in as {bot.user}")


# ==================================
# START BOT
# ==================================

token = os.getenv("DISCORD_SECRET")

if not token:
    raise RuntimeError("DISCORD_SECRET is missing!")

bot.run(token)
