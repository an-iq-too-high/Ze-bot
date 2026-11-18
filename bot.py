import os
import json
import random
import datetime
import asyncio
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
intents.voice_states = True


class SpaceDood(commands.Bot):
    async def setup_hook(self):
        self.add_view(TicketPanelView())
        self.add_view(TicketCloseView())
        await self.tree.sync()
        await resume_giveaways()


bot = SpaceDood(command_prefix="!", intents=intents)

# ==================================
# JSON DATABASE HELPER
# ==================================

def load_json(filename):
    if not os.path.exists(filename):
        return {}

    try:
        with open(filename, "r") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}


def save_json(filename, data):
    temporary_file = filename + ".tmp"

    with open(temporary_file, "w") as file:
        json.dump(data, file, indent=4)

    os.replace(temporary_file, filename)


# ==================================
# GIVEAWAY DATABASE
# ==================================

GIVEAWAY_FILE = "giveaways.json"
giveaway_data = load_json(GIVEAWAY_FILE)
giveaway_tasks = {}


def save_giveaways():
    save_json(GIVEAWAY_FILE, giveaway_data)


def schedule_giveaway(message_id):
    message_id = str(message_id)

    if message_id in giveaway_tasks:
        return

    giveaway_tasks[message_id] = asyncio.create_task(
        finish_giveaway(message_id)
    )


async def finish_giveaway(message_id):
    message_id = str(message_id)

    try:
        giveaway = giveaway_data.get(message_id)

        if giveaway is None:
            return

        remaining = giveaway["end_time"] - datetime.datetime.now(
            datetime.timezone.utc
        ).timestamp()

        if remaining > 0:
            await asyncio.sleep(remaining)

        giveaway = giveaway_data.get(message_id)

        if giveaway is None:
            return

        channel_id = int(giveaway["channel_id"])
        channel = bot.get_channel(channel_id)

        if channel is None:
            channel = await bot.fetch_channel(channel_id)

        message = await channel.fetch_message(int(message_id))
        entrants = []

        for reaction in message.reactions:
            if str(reaction.emoji) == "🎉":
                async for user in reaction.users():
                    if not user.bot:
                        entrants.append(user)
                break

        winner = random.choice(entrants) if entrants else None

        embed = discord.Embed(
            title="🎉 GIVEAWAY ENDED",
            description=(
                f"**Prize:** {giveaway['prize']}\n\n"
                + (
                    f"**Winner:** {winner.mention}"
                    if winner
                    else "**No one entered this giveaway!**"
                )
            ),
            color=discord.Color.red()
        )
        embed.set_footer(text="Space Dood Giveaways")

        await message.edit(embed=embed)

        if winner:
            await channel.send(
                f"🎉 Congratulations {winner.mention}! "
                f"You won **{giveaway['prize']}**!"
            )
        else:
            await channel.send(
                f"🎉 The giveaway for **{giveaway['prize']}** "
                "has ended, but nobody entered."
            )

        giveaway_data.pop(message_id, None)
        save_giveaways()

    except discord.NotFound:
        giveaway_data.pop(message_id, None)
        save_giveaways()

    except discord.Forbidden as error:
        print("Giveaway permission error:", error)

    except discord.HTTPException as error:
        print("Giveaway Discord API error:", error)

    except Exception as error:
        print("Giveaway error:", error)

    finally:
        giveaway_tasks.pop(message_id, None)


async def resume_giveaways():
    for message_id in list(giveaway_data.keys()):
        schedule_giveaway(message_id)


async def start_giveaway(channel, duration, prize):
    end_time = (
        datetime.datetime.now(datetime.timezone.utc).timestamp()
        + duration
    )

    embed = discord.Embed(
        title="🎉 GIVEAWAY!",
        description=(
            f"**Prize:** {prize}\n\n"
            "React with 🎉 to enter!\n\n"
            f"**Ends:** <t:{int(end_time)}:R>"
        ),
        color=discord.Color.red()
    )
    embed.set_footer(text="Space Dood Giveaways")

    message = await channel.send(embed=embed)
    await message.add_reaction("🎉")

    giveaway_data[str(message.id)] = {
        "channel_id": channel.id,
        "guild_id": channel.guild.id,
        "prize": prize,
        "end_time": end_time
    }

    save_giveaways()
    schedule_giveaway(message.id)

    return message


# ==================================
# CURRENCY DATABASE
# ==================================

CURRENCY_FILE = "currency.json"
currency_data = load_json(CURRENCY_FILE)


def save_currency():
    save_json(CURRENCY_FILE, currency_data)


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
ticket_data = load_json(TICKET_FILE)


def save_ticket_config():
    save_json(TICKET_FILE, ticket_data)


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

    return any(
        role in member.roles
        for role in get_ticket_staff_roles(member.guild)
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
greet_data = load_json(GREET_FILE)


def save_greet_config():
    save_json(GREET_FILE, greet_data)


def get_greet_config(guild_id):
    server_id = str(guild_id)

    if server_id not in greet_data:
        greet_data[server_id] = {
            "channel_id": None,
            "message": (
                "Welcome {member} to {server}! "
                "You are member #{membercount}!"
            )
        }
        save_greet_config()

    config = greet_data[server_id]
    config.setdefault("channel_id", None)
    config.setdefault(
        "message",
        "Welcome {member} to {server}! "
        "You are member #{membercount}!"
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
# MODMAIL DATABASE
# ==================================

MODMAIL_CONFIG_FILE = "modmail_config.json"
MODMAIL_THREADS_FILE = "modmail_threads.json"

modmail_config = load_json(MODMAIL_CONFIG_FILE)
modmail_threads = load_json(MODMAIL_THREADS_FILE)


def save_modmail_config():
    save_json(MODMAIL_CONFIG_FILE, modmail_config)


def save_modmail_threads():
    save_json(MODMAIL_THREADS_FILE, modmail_threads)


def get_modmail_config(guild_id):
    server_id = str(guild_id)

    if server_id not in modmail_config:
        modmail_config[server_id] = {
            "category_id": None,
            "enabled": False
        }
        save_modmail_config()

    config = modmail_config[server_id]
    config.setdefault("category_id", None)
    config.setdefault("enabled", False)

    return config


def get_modmail_thread(user_id):
    return modmail_threads.get(str(user_id))


def save_modmail_thread(user_id, guild_id, channel_id):
    modmail_threads[str(user_id)] = {
        "guild_id": guild_id,
        "channel_id": channel_id
    }
    save_modmail_threads()


def remove_modmail_thread(user_id):
    modmail_threads.pop(str(user_id), None)
    save_modmail_threads()


def get_modmail_owner_id(channel):
    if not channel.topic:
        return None

    if not channel.topic.startswith("SpaceDoodModmail|"):
        return None

    for part in channel.topic.split("|"):
        if part.startswith("owner="):
            try:
                return int(part.replace("owner=", ""))
            except ValueError:
                return None

    return None


def is_modmail_closed(channel):
    return (
        channel.topic is not None
        and "status=closed" in channel.topic
    )


def is_modmail_staff(member):
    return (
        member.guild is not None
        and is_ticket_staff(member)
    )


async def get_modmail_category(guild):
    config = get_modmail_config(guild.id)

    category = None

    if config.get("category_id"):
        category = guild.get_channel(
            int(config["category_id"])
        )

    if category is None:
        category = discord.utils.get(
            guild.categories,
            name="Space Dood Modmail"
        )

    if category is None:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            )
        }

        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )

        for role in get_ticket_staff_roles(guild):
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )

        category = await guild.create_category(
            "Space Dood Modmail",
            overwrites=overwrites
        )

    config["category_id"] = category.id
    save_modmail_config()

    return category


async def setup_modmail(guild):
    if guild is None:
        return False, "This command must be used in a server."

    if not get_ticket_staff_roles(guild):
        return (
            False,
            "You haven't configured any ticket staff roles yet!\n"
            "Use `!ticketrole add @Role` first. "
            "Modmail uses those same staff roles."
        )

    try:
        category = await get_modmail_category(guild)

        await category.set_permissions(
            guild.default_role,
            view_channel=False
        )

        if guild.me:
            await category.set_permissions(
                guild.me,
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )

        for role in get_ticket_staff_roles(guild):
            await category.set_permissions(
                role,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )

        modmail_config[str(guild.id)] = {
            "category_id": category.id,
            "enabled": True
        }
        save_modmail_config()

        return (
            True,
            f"✅ Modmail is now enabled!\n"
            f"Category: {category.mention}\n\n"
            "Members can now DM Space Dood to contact your staff team."
        )

    except discord.Forbidden:
        return (
            False,
            "I need the Manage Channels permission to create "
            "and configure the Modmail category."
        )

    except discord.HTTPException as error:
        print("Modmail setup error:", error)
        return False, "Something went wrong while setting up Modmail."


async def find_modmail_guild():
    for guild_id, config in modmail_config.items():
        if not config.get("enabled", False):
            continue

        guild = bot.get_guild(int(guild_id))

        if guild is not None:
            return guild

    return None


async def create_modmail_channel(guild, user):
    category = await get_modmail_category(guild)

    if category is None:
        return None

    username = user.name.lower().replace(" ", "-")
    username = "".join(
        character
        for character in username
        if character.isalnum() or character == "-"
    )

    channel = await guild.create_text_channel(
        name=f"modmail-{username[:30]}",
        category=category,
        topic=(
            f"SpaceDoodModmail|owner={user.id}|status=open"
        )
    )

    save_modmail_thread(
        user.id,
        guild.id,
        channel.id
    )

    embed = discord.Embed(
        title="📨 New Modmail Conversation",
        description=(
            f"**User:** {user.mention}\n"
            f"**Username:** {user}\n"
            f"**User ID:** `{user.id}`\n\n"
            "The member has opened a Modmail conversation.\n"
            "Use `!reply <message>` to respond.\n"
            "Use `!closemail` to close this conversation."
        ),
        color=discord.Color.red()
    )
    embed.set_thumbnail(url=user.display_avatar.url)

    await channel.send(embed=embed)

    return channel


async def get_active_modmail_channel(user_id):
    thread = get_modmail_thread(user_id)

    if thread is None:
        return None

    guild = bot.get_guild(int(thread["guild_id"]))

    if guild is None:
        return None

    channel = guild.get_channel(int(thread["channel_id"]))

    if channel is None:
        try:
            channel = await guild.fetch_channel(
                int(thread["channel_id"])
            )
        except (discord.NotFound, discord.Forbidden):
            remove_modmail_thread(user_id)
            return None

    if not isinstance(channel, discord.TextChannel):
        remove_modmail_thread(user_id)
        return None

    if is_modmail_closed(channel):
        remove_modmail_thread(user_id)
        return None

    return channel


async def relay_member_message(message):
    user = message.author

    guild = await find_modmail_guild()

    if guild is None:
        await user.send(
            "Modmail isn't currently configured on a server. "
            "Please contact the server staff another way."
        )
        return

    channel = await get_active_modmail_channel(user.id)

    if channel is None:
        try:
            channel = await create_modmail_channel(guild, user)
        except discord.Forbidden:
            await user.send(
                "I couldn't open your Modmail conversation. "
                "Please contact the server staff another way."
            )
            return
        except discord.HTTPException as error:
            print("Modmail channel creation error:", error)
            await user.send(
                "Something went wrong while opening your Modmail conversation."
            )
            return

        if channel is None:
            await user.send(
                "I couldn't open your Modmail conversation."
            )
            return

        await user.send(
            "📨 Your Modmail conversation has been opened! "
            "A staff member will reply here."
        )

    files = []

    for attachment in message.attachments:
        try:
            files.append(await attachment.to_file())
        except discord.HTTPException:
            print("Couldn't copy a Modmail attachment.")

    content = message.content.strip() or "(No text message.)"

    embed = discord.Embed(
        title="📩 Member Message",
        description=content[:4000],
        color=discord.Color.blurple()
    )
    embed.set_author(
        name=f"{user} ({user.id})",
        icon_url=user.display_avatar.url
    )

    try:
        await channel.send(
            embed=embed,
            files=files
        )
    except discord.Forbidden:
        await user.send(
            "I couldn't deliver your message to the staff team. "
            "Please try again later."
        )
    except discord.HTTPException as error:
        print("Modmail relay error:", error)
        await user.send(
            "Something went wrong while delivering your message."
        )


async def send_modmail_reply(channel, staff_member, content, attachments):
    owner_id = get_modmail_owner_id(channel)

    if owner_id is None:
        return False, "This isn't a Space Dood Modmail channel."

    if is_modmail_closed(channel):
        return False, "This Modmail conversation is already closed."

    if not is_modmail_staff(staff_member):
        return False, "You don't have the configured Modmail staff role."

    if not content.strip() and not attachments:
        return False, "Please include a message or an attachment."

    try:
        user = await bot.fetch_user(owner_id)

        files = []

        for attachment in attachments:
            files.append(await attachment.to_file())

        embed = discord.Embed(
            title="💬 Staff Reply",
            description=content[:4000] if content.strip() else "(Attachment)",
            color=discord.Color.green()
        )
        embed.set_footer(text="Space Dood Modmail")

        await user.send(
            embed=embed,
            files=files
        )

        staff_embed = discord.Embed(
            title="📤 Reply Sent",
            description=content[:4000] if content.strip() else "(Attachment)",
            color=discord.Color.green()
        )
        staff_embed.set_author(
            name=str(staff_member),
            icon_url=staff_member.display_avatar.url
        )

        await channel.send(embed=staff_embed)

        return True, f"✅ Your reply was sent to <@{owner_id}>!"

    except discord.NotFound:
        return False, "I couldn't find that user."

    except discord.Forbidden:
        return False, "I couldn't DM that user. They may have DMs disabled."

    except discord.HTTPException as error:
        print("Modmail reply error:", error)
        return False, "Something went wrong while sending the reply."


async def close_modmail(channel, actor):
    owner_id = get_modmail_owner_id(channel)

    if owner_id is None:
        return False, "This isn't a Space Dood Modmail channel."

    if is_modmail_closed(channel):
        return False, "This Modmail conversation is already closed."

    if not is_modmail_staff(actor):
        return False, "You don't have the configured Modmail staff role."

    try:
        user = await bot.fetch_user(owner_id)

        try:
            await user.send(
                "🔒 Your Modmail conversation has been closed by the staff team."
            )
        except discord.Forbidden:
            pass

        await channel.edit(
            name=f"closed-{channel.name}"[:100],
            topic=(
                f"SpaceDoodModmail|owner={owner_id}|status=closed"
            )
        )

        remove_modmail_thread(owner_id)

        return True, "🔒 Modmail conversation closed successfully!"

    except discord.Forbidden:
        return False, "I don't have permission to edit this channel."

    except discord.HTTPException as error:
        print("Modmail close error:", error)
        return False, "Something went wrong while closing Modmail."


# ==================================
# TEMPVOICE DATABASE
# ==================================

TEMPVOICE_FILE = "tempvoice_config.json"
tempvoice_data = load_json(TEMPVOICE_FILE)


def save_tempvoice():
    save_json(TEMPVOICE_FILE, tempvoice_data)


def get_tempvoice_config(guild_id):
    server_id = str(guild_id)

    if server_id not in tempvoice_data:
        tempvoice_data[server_id] = {
            "generator_id": None,
            "channels": {}
        }
        save_tempvoice()

    config = tempvoice_data[server_id]
    config.setdefault("generator_id", None)
    config.setdefault("channels", {})

    return config


async def delete_tempvoice_channel(guild, channel_id):
    config = get_tempvoice_config(guild.id)
    channel_id = str(channel_id)

    channel = guild.get_channel(int(channel_id))

    if channel is None:
        config["channels"].pop(channel_id, None)
        save_tempvoice()
        return

    try:
        await channel.delete(reason="Temporary voice channel is empty.")

    except discord.NotFound:
        pass

    except discord.Forbidden:
        print(
            f"I don't have permission to delete temp voice channel "
            f"{channel_id}."
        )
        return

    except discord.HTTPException as error:
        print("Tempvoice deletion error:", error)
        return

    config["channels"].pop(channel_id, None)
    save_tempvoice()


# ==================================
# TICKET CATEGORY
# ==================================

async def get_ticket_category(guild):
    config = get_ticket_config(guild.id)
    category = None

    if config["category_id"]:
        category = guild.get_channel(int(config["category_id"]))

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

        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(
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

    if guild.me:
        overwrites[guild.me] = discord.PermissionOverwrite(
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
        await category.set_permissions(role, overwrite=overwrite)

    else:
        await category.set_permissions(role, overwrite=None)

    for channel in category.text_channels:
        if adding:
            overwrite = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )
            await channel.set_permissions(role, overwrite=overwrite)
        else:
            await channel.set_permissions(role, overwrite=None)


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
    return (
        channel.topic is not None
        and "status=closed" in channel.topic
    )


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

    await channel.edit(
        name=f"closed-{channel.name}"[:100],
        topic=f"SpaceDoodTicket|owner={owner_id}|status=closed"
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
    async def open_ticket(self, interaction, button):
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
    async def close_ticket(self, interaction, button):
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
    return discord.Embed(
        title="Tickets!",
        description="Press the black button to register a ticket!",
        color=discord.Color.red()
    )


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
                "⏳ You've already claimed your daily reward!\n"
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
    embed.set_footer(text="Space Dood Economy")

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

    if (
        actor.id != guild.owner_id
        and actor.top_role <= target.top_role
    ):
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

        if action == "ban":
            await target.ban(reason=reason)
            return f"Successfully banned {target}."

        if action == "timeout":
            await target.timeout(
                datetime.timedelta(minutes=minutes),
                reason=reason
            )
            return (
                f"Successfully timed out {target} "
                f"for {minutes} minutes."
            )

    except discord.Forbidden:
        return (
            "Discord denied that action. "
            "Check permissions and role hierarchy."
        )

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
        return (
            "You need the Manage Messages permission "
            "to warn members."
        )

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

        return (
            f"⚠️ Successfully warned {target.mention}. "
            "Their DM was sent!"
        )

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
# 8BALL FUNCTION
# ==================================

EIGHT_BALL_ANSWERS = [
    "It is certain.",
    "Without a doubt.",
    "Yes, definitely!",
    "You can count on it.",
    "Most likely.",
    "Signs point to yes.",
    "Ask again later.",
    "Cannot predict that right now.",
    "Don't count on it.",
    "My reply is no.",
    "Very doubtful.",
    "Absolutely not!"
]


def get_eight_ball_answer():
    return random.choice(EIGHT_BALL_ANSWERS)


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

    embed.set_footer(text="Space Dood Poll")

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

    join_date = (
        discord.utils.format_dt(member.joined_at, style="F")
        if member.joined_at
        else "Unknown"
    )

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

    embed.set_footer(text=f"User ID: {member.id}")

    return embed


# ==================================
# SERVERINFO FUNCTION
# ==================================

def create_serverinfo_embed(guild):
    embed = discord.Embed(
        title=f"Server Information: {guild.name}",
        color=discord.Color.blurple()
    )

    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    owner = guild.owner

    embed.add_field(
        name="Server Name",
        value=guild.name,
        inline=True
    )

    embed.add_field(
        name="Server ID",
        value=str(guild.id),
        inline=True
    )

    embed.add_field(
        name="Owner",
        value=owner.mention if owner else "Unknown",
        inline=False
    )

    embed.add_field(
        name="Created",
        value=discord.utils.format_dt(guild.created_at, style="F"),
        inline=False
    )

    embed.add_field(
        name="Members",
        value=str(guild.member_count or len(guild.members)),
        inline=True
    )

    embed.add_field(
        name="Roles",
        value=str(len(guild.roles)),
        inline=True
    )

    embed.add_field(
        name="Text Channels",
        value=str(len(guild.text_channels)),
        inline=True
    )

    embed.add_field(
        name="Voice Channels",
        value=str(len(guild.voice_channels)),
        inline=True
    )

    embed.add_field(
        name="Categories",
        value=str(len(guild.categories)),
        inline=True
    )

    embed.add_field(
        name="Boosts",
        value=str(guild.premium_subscription_count or 0),
        inline=True
    )

    embed.add_field(
        name="Boost Level",
        value=f"Level {guild.premium_tier}",
        inline=True
    )

    embed.set_footer(text=f"Server ID: {guild.id}")

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
            "You need the Manage Server permission "
            "to configure ticket roles."
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
            "Usage: `!ticketrole add @Role` or "
            "`!ticketrole remove @Role`"
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
            "You need the Manage Server permission "
            "to create a ticket panel."
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
# PREFIX MODMAIL COMMANDS (!)
# ==================================

@bot.command(name="modmailsetup")
@commands.has_guild_permissions(manage_guild=True)
async def modmailsetup_prefix(ctx):
    if ctx.guild is None:
        return

    success, message = await setup_modmail(ctx.guild)
    await ctx.send(message)


@modmailsetup_prefix.error
async def modmailsetup_prefix_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(
            "You need the Manage Server permission to set up Modmail."
        )


@bot.command(name="reply")
async def reply_prefix(ctx, *, message=""):
    if ctx.guild is None:
        await ctx.send("This command must be used inside a Modmail channel.")
        return

    success, result = await send_modmail_reply(
        ctx.channel,
        ctx.author,
        message,
        ctx.message.attachments
    )

    await ctx.send(result)


@bot.command(name="closemail")
async def closemail_prefix(ctx):
    if ctx.guild is None:
        await ctx.send("This command must be used inside a Modmail channel.")
        return

    success, message = await close_modmail(
        ctx.channel,
        ctx.author
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
        await ctx.send("Usage: `!greet #channel`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Please mention a valid text channel.")


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

    await ctx.send("✅ Greeting message updated!")


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
# PREFIX TEMPVOICE COMMAND
# ==================================

@bot.command(name="tempvoice")
@commands.has_guild_permissions(manage_guild=True)
async def tempvoice_prefix(ctx, channel: discord.VoiceChannel):
    if ctx.guild is None:
        return

    config = get_tempvoice_config(ctx.guild.id)
    config["generator_id"] = channel.id
    save_tempvoice()

    await ctx.send(
        f"✅ Tempvoice generator set to {channel.mention}!\n"
        "When someone joins that channel, Space Dood will create "
        "a temporary voice channel for them."
    )


@tempvoice_prefix.error
async def tempvoice_prefix_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(
            "You need the Manage Server permission to configure Tempvoice."
        )
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: `!tempvoice #VoiceChannel`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Please mention a valid voice channel.")


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
        ctx.guild, ctx.author, member, "kick", reason
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
        ctx.guild, ctx.author, member, "ban", reason
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
        await ctx.send("Timeout must be between 1 and 40320 minutes.")
        return

    result = await moderate(
        ctx.guild, ctx.author, member, "timeout", reason, minutes
    )
    await ctx.send(result)


@bot.command(name="warn")
async def warn_prefix(
    ctx,
    member: discord.Member,
    *,
    reason="No reason provided"
):
    result = await warn_member(
        ctx.guild, ctx.author, member, reason
    )
    await ctx.send(result)


@bot.command(name="joke")
async def joke_prefix(ctx):
    await ctx.send(get_joke())


@bot.command(name="8ball")
async def eightball_prefix(ctx, *, question: str):
    await ctx.send(
        f"🎱 **Question:** {question}\n"
        f"**Answer:** {get_eight_ball_answer()}"
    )


@bot.command(name="giveaway")
async def giveaway_prefix(ctx, duration: int, *, prize: str):
    if ctx.guild is None:
        await ctx.send("Giveaways can only be started in a server.")
        return

    if not ctx.author.guild_permissions.manage_guild:
        await ctx.send(
            "You need the Manage Server permission to start giveaways."
        )
        return

    if not 10 <= duration <= 604800:
        await ctx.send(
            "Giveaway duration must be between 10 and 604800 seconds."
        )
        return

    if not prize.strip():
        await ctx.send("Please provide a prize.")
        return

    try:
        message = await start_giveaway(
            ctx.channel, duration, prize
        )
        await ctx.send(
            f"🎉 Giveaway started! {message.jump_url}"
        )

    except discord.Forbidden:
        await ctx.send(
            "I need permission to send messages, embed links, "
            "and add reactions to start a giveaway."
        )

    except discord.HTTPException as error:
        print("Giveaway start error:", error)
        await ctx.send(
            "Something went wrong while starting the giveaway."
        )


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
        await ctx.send(
            "Something went wrong while creating the poll."
        )


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


@bot.command(name="serverinfo")
async def serverinfo_prefix(ctx):
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    await ctx.send(embed=create_serverinfo_embed(ctx.guild))


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
        ctx.guild, ctx.author, member, amount
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
            "You need the Manage Server permission "
            "to configure ticket roles.",
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
                interaction.guild, role, True
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
                interaction.guild, role, False
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
            "You need the Manage Server permission "
            "to create a ticket panel.",
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
# SLASH MODMAIL COMMANDS (/)
# ==================================

@bot.tree.command(
    name="modmailsetup",
    description="Set up the Modmail system"
)
@app_commands.default_permissions(manage_guild=True)
async def modmailsetup_slash(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True
        )
        return

    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "You need the Manage Server permission to set up Modmail.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    success, message = await setup_modmail(interaction.guild)

    await interaction.followup.send(
        message,
        ephemeral=True
    )


@bot.tree.command(
    name="reply",
    description="Reply to the member in this Modmail conversation"
)
@app_commands.describe(message="The message to send to the member")
async def reply_slash(
    interaction: discord.Interaction,
    message: str
):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command must be used inside a Modmail channel.",
            ephemeral=True
        )
        return

    success, result = await send_modmail_reply(
        interaction.channel,
        interaction.user,
        message,
        []
    )

    await interaction.response.send_message(
        result,
        ephemeral=True
    )


@bot.tree.command(
    name="closemail",
    description="Close this Modmail conversation"
)
async def closemail_slash(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command must be used inside a Modmail channel.",
            ephemeral=True
        )
        return

    success, message = await close_modmail(
        interaction.channel,
        interaction.user
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
            "You need the Manage Server permission "
            "to configure greetings.",
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
    message=(
        "Your greeting message. Supports {server}, "
        "{member}, and {membercount}"
    )
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
            "You need the Manage Server permission "
            "to configure greetings.",
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
# SLASH TEMPVOICE COMMAND
# ==================================

@bot.tree.command(
    name="tempvoice",
    description="Set the temporary voice channel generator"
)
@app_commands.describe(
    channel="The voice channel members join to create temp channels"
)
@app_commands.default_permissions(manage_guild=True)
async def tempvoice_slash(
    interaction: discord.Interaction,
    channel: discord.VoiceChannel
):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True
        )
        return

    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "You need the Manage Server permission to configure Tempvoice.",
            ephemeral=True
        )
        return

    config = get_tempvoice_config(interaction.guild.id)
    config["generator_id"] = channel.id
    save_tempvoice()

    await interaction.response.send_message(
        f"✅ Tempvoice generator set to {channel.mention}!\n"
        "When someone joins that channel, Space Dood will create "
        "a temporary voice channel for them.",
        ephemeral=True
    )


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


@bot.tree.command(name="timeout", description="Timeout a member")
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
    name="warn",
    description="DM a warning to a server member"
)
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
    await interaction.response.send_message(get_joke())


@bot.tree.command(
    name="8ball",
    description="Ask the magic 8ball a question"
)
@app_commands.describe(
    question="What would you like to ask?"
)
async def eightball_slash(
    interaction: discord.Interaction,
    question: str
):
    await interaction.response.send_message(
        f"🎱 **Question:** {question}\n"
        f"**Answer:** {get_eight_ball_answer()}"
    )


@bot.tree.command(
    name="giveaway",
    description="Start a giveaway"
)
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    duration="Duration in seconds (10–604800)",
    prize="What are you giving away?"
)
async def giveaway_slash(
    interaction: discord.Interaction,
    duration: app_commands.Range[int, 10, 604800],
    prize: str
):
    if interaction.guild is None:
        await interaction.response.send_message(
            "Giveaways can only be started in a server.",
            ephemeral=True
        )
        return

    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "You need the Manage Server permission to start giveaways.",
            ephemeral=True
        )
        return

    if not prize.strip():
        await interaction.response.send_message(
            "Please provide a prize.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    try:
        message = await start_giveaway(
            interaction.channel,
            duration,
            prize
        )

        await interaction.followup.send(
            f"🎉 Giveaway started! {message.jump_url}",
            ephemeral=True
        )

    except discord.Forbidden:
        await interaction.followup.send(
            "I need permission to send messages, embed links, "
            "and add reactions to start a giveaway.",
            ephemeral=True
        )

    except discord.HTTPException as error:
        print("Giveaway start error:", error)
        await interaction.followup.send(
            "Something went wrong while starting the giveaway.",
            ephemeral=True
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

    await interaction.response.send_message(
        embed=create_userinfo_embed(member),
        ephemeral=True
    )


@bot.tree.command(
    name="serverinfo",
    description="View information about this server"
)
async def serverinfo_slash(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        embed=create_serverinfo_embed(interaction.guild),
        ephemeral=True
    )


@bot.tree.command(
    name="balance",
    description="Check your Space Coins"
)
async def balance_slash(interaction: discord.Interaction):
    result = await check_balance(
        interaction.guild,
        interaction.user
    )
    await interaction.response.send_message(
        result,
        ephemeral=True
    )


@bot.tree.command(
    name="daily",
    description="Claim your daily Space Coins"
)
async def daily_slash(interaction: discord.Interaction):
    result = await claim_daily(
        interaction.guild,
        interaction.user
    )
    await interaction.response.send_message(
        result,
        ephemeral=True
    )


@bot.tree.command(
    name="work",
    description="Earn Space Coins by working"
)
async def work_slash(interaction: discord.Interaction):
    result = await work(
        interaction.guild,
        interaction.user
    )
    await interaction.response.send_message(
        result,
        ephemeral=True
    )


@bot.tree.command(
    name="pay",
    description="Send Space Coins to another member"
)
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
    await interaction.response.send_message(
        result,
        ephemeral=True
    )


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
async def on_message(message):
    if message.author.bot:
        return

    if isinstance(message.channel, discord.DMChannel):
        await relay_member_message(message)
        return

    await bot.process_commands(message)


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


# ==================================
# TEMPVOICE EVENT
# ==================================

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return

    guild = member.guild
    config = get_tempvoice_config(guild.id)

    # First, clean up the temporary channel the member left.
    if before.channel is not None:
        old_channel_id = str(before.channel.id)

        if old_channel_id in config["channels"]:
            remaining_members = [
                current_member
                for current_member in before.channel.members
                if current_member.id != member.id
            ]

            if not remaining_members:
                await delete_tempvoice_channel(
                    guild,
                    old_channel_id
                )

    # Next, check whether the member joined the generator channel.
    generator_id = config.get("generator_id")

    if (
        after.channel is None
        or generator_id is None
        or after.channel.id != int(generator_id)
    ):
        return

    generator = after.channel

    bot_member = guild.me

    if bot_member is None:
        return

    if not bot_member.guild_permissions.manage_channels:
        print("Tempvoice needs the Manage Channels permission.")
        return

    if not bot_member.guild_permissions.move_members:
        print("Tempvoice needs the Move Members permission.")
        return

    username = member.display_name.lower().replace(" ", "-")
    username = "".join(
        character
        for character in username
        if character.isalnum() or character == "-"
    )

    channel_name = f"{username[:80]}'s channel"

    overwrites = dict(generator.overwrites)

    overwrites[member] = discord.PermissionOverwrite(
        view_channel=True,
        connect=True,
        speak=True,
        manage_channels=True,
        move_members=True
    )

    try:
        temp_channel = await guild.create_voice_channel(
            name=channel_name[:100],
            category=generator.category,
            overwrites=overwrites,
            reason=f"Temporary voice channel for {member}"
        )

        config["channels"][str(temp_channel.id)] = {
            "owner_id": member.id
        }
        save_tempvoice()

        try:
            await member.move_to(
                temp_channel,
                reason="Created a temporary voice channel."
            )

        except (discord.Forbidden, discord.HTTPException) as error:
            print("Tempvoice move error:", error)

            await delete_tempvoice_channel(
                guild,
                temp_channel.id
            )

    except discord.Forbidden:
        print(
            "I don't have permission to create or configure "
            "temporary voice channels."
        )

    except discord.HTTPException as error:
        print("Tempvoice creation error:", error)


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
