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


class SpaceDood(commands.Bot):
    async def setup_hook(self):
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
async def on_ready():
    print(f"Space Dood is online! Logged in as {bot.user}")


# ==================================
# START BOT
# ==================================

token = os.getenv("DISCORD_SECRET")

if not token:
    raise RuntimeError("DISCORD_SECRET is missing!")

bot.run(token)
