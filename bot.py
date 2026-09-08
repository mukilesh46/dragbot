import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv


# =========================================================
# LOAD .ENV
# =========================================================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")

if not TOKEN:
    print("❌ DISCORD_TOKEN is missing in .env file!")
    raise SystemExit(1)


# =========================================================
# INTENTS
# =========================================================

intents = discord.Intents.default()

intents.message_content = True
intents.members = True
intents.voice_states = True
intents.guilds = True


# =========================================================
# BOT
# =========================================================

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None
)


# =========================================================
# SETTINGS
# =========================================================

DRAG_DELAY = 0.20

drag_tasks = {}
drag_info = {}


# =========================================================
# GET BOT VOICE CHANNEL
# =========================================================

def get_bot_voice_channel(guild):

    bot_member = guild.me

    if bot_member is None:
        return None

    if bot_member.voice is None:
        return None

    return bot_member.voice.channel


# =========================================================
# FIND TEMPORARY VOICE CHANNEL
# =========================================================

def get_temporary_channel(guild, bot_channel):

    bot_member = guild.me

    if bot_member is None:
        return None

    for channel in guild.voice_channels:

        # Don't use the bot's current VC
        if channel.id == bot_channel.id:
            continue

        permissions = channel.permissions_for(bot_member)

        if not permissions.connect:
            continue

        if not permissions.move_members:
            continue

        # Check VC user limit
        if channel.user_limit != 0:

            if len(channel.members) >= channel.user_limit:
                continue

        return channel

    return None


# =========================================================
# BOT READY
# =========================================================

@bot.event
async def on_ready():

    print("========================================")
    print("🐉 DRAGO BOT ONLINE")
    print(f"🤖 Bot User : {bot.user}")
    print(f"🌐 Servers  : {len(bot.guilds)}")
    print(f"⚡ Delay    : {DRAG_DELAY}s")
    print("========================================")

    for guild in bot.guilds:

        bot_vc = get_bot_voice_channel(guild)

        if bot_vc:

            print(
                f"🎙️ {guild.name} → {bot_vc.name}"
            )

        else:

            print(
                f"⚪ {guild.name} → Bot is not in VC"
            )


# =========================================================
# JOIN
#
# !join
#
# Bot joins the VC where the command user is currently.
# =========================================================

@bot.command(name="join")
@commands.has_permissions(move_members=True)
async def join(ctx):

    if ctx.author.voice is None:

        await ctx.send(
            "❌ **You must be inside a Voice Channel!**\n\n"
            "Join your desired VC and type:\n"
            "`!join`"
        )

        return

    channel = ctx.author.voice.channel
    bot_member = ctx.guild.me

    if bot_member is None:

        await ctx.send(
            "❌ Could not find DRAGO BOT."
        )

        return

    permissions = channel.permissions_for(bot_member)

    if not permissions.connect:

        await ctx.send(
            f"❌ DRAGO BOT cannot connect to "
            f"**{channel.name}**.\n\n"
            "Give the bot **Connect** permission."
        )

        return

    try:

        # Bot already inside a VC
        if bot_member.voice is not None:

            current_channel = bot_member.voice.channel

            # Already in requested VC
            if current_channel.id == channel.id:

                await ctx.send(
                    f"🎙️ DRAGO BOT is already in "
                    f"**{channel.name}**!"
                )

                return

            # Move bot to requested VC
            await bot_member.move_to(channel)

        else:

            # Bot joins VC
            await channel.connect()

        await ctx.send(
            f"🐉 **DRAGO BOT JOINED!**\n\n"
            f"🎙️ VC: **{channel.name}**\n\n"
            f"⚡ Use:\n"
            f"`!drag @member count`"
        )

    except discord.Forbidden:

        await ctx.send(
            "❌ DRAGO BOT doesn't have permission "
            "to join or move to this VC."
        )

    except discord.HTTPException as e:

        await ctx.send(
            f"❌ Discord API Error: `{e}`"
        )

    except Exception as e:

        print(f"[JOIN ERROR] {e}")

        await ctx.send(
            f"❌ Join Error: `{e}`"
        )


# =========================================================
# LEAVE
#
# !leave
#
# Stops drag and leaves VC.
# =========================================================

@bot.command(name="leave")
@commands.has_permissions(move_members=True)
async def leave(ctx):

    guild_id = ctx.guild.id

    task = drag_tasks.get(guild_id)

    if task:

        task.cancel()

        try:
            await task

        except asyncio.CancelledError:
            pass

        except Exception:
            pass

    voice_client = ctx.guild.voice_client

    if voice_client is None:

        await ctx.send(
            "⚪ DRAGO BOT is not in a VC."
        )

        return

    try:

        await voice_client.disconnect()

    except Exception as e:

        print(f"[LEAVE ERROR] {e}")

    drag_tasks.pop(guild_id, None)

    await ctx.send(
        "👋 **DRAGO BOT LEFT THE VC!**"
    )


# =========================================================
# DRAG
#
# COMMAND:
#
# !drag @member count
#
# Example:
#
# !drag @User 100
#
#
# BEHAVIOR:
#
# Member in another VC:
#
# OTHER VC
#    ↓
# BOT VC
#    ↓
# OTHER VC
#
#
# Member already in bot VC:
#
# BOT VC
#    ↓
# TEMP VC
#    ↓
# BOT VC
#
#
# If member disconnects:
#
# DRAG RUNNING
#       ↓
# MEMBER DISCONNECT
#       ↓
# PAUSE
#       ↓
# WAIT FOR SAME MEMBER
#       ↓
# MEMBER REJOINS ANY VC
#       ↓
# RESUME
#       ↓
# CONTINUE REMAINING ROUNDS
# =========================================================

@bot.command(name="drag")
@commands.has_permissions(move_members=True)
async def drag(ctx, member: discord.Member, count: int):

    guild = ctx.guild
    guild_id = guild.id

    # =====================================================
    # COUNT CHECK
    # =====================================================

    if count <= 0:

        await ctx.send(
            "❌ Count must be `1` or greater."
        )

        return

    # =====================================================
    # CHECK EXISTING DRAG
    # =====================================================

    existing_task = drag_tasks.get(guild_id)

    if existing_task is not None and not existing_task.done():

        await ctx.send(
            "❌ **A drag is already running!**\n\n"
            "Use:\n"
            "`!stop`"
        )

        return

    # =====================================================
    # BOT VC CHECK
    # =====================================================

    bot_vc = get_bot_voice_channel(guild)

    if bot_vc is None:

        await ctx.send(
            "❌ **DRAGO BOT IS NOT IN A VC!**\n\n"
            "1️⃣ Join your desired VC\n"
            "2️⃣ Type `!join`\n"
            "3️⃣ Then use:\n"
            "`!drag @member count`"
        )

        return

    # =====================================================
    # TARGET MEMBER
    # =====================================================

    target_member = guild.get_member(member.id)

    if target_member is None:

        await ctx.send(
            "❌ Member not found."
        )

        return

    # =====================================================
    # TARGET MUST INITIALLY BE IN VC
    # =====================================================

    if (
        target_member.voice is None
        or target_member.voice.channel is None
    ):

        await ctx.send(
            f"❌ {target_member.mention} "
            f"is not in a Voice Channel."
        )

        return

    starting_channel = target_member.voice.channel

    # =====================================================
    # BOT MEMBER
    # =====================================================

    bot_member = guild.me

    if bot_member is None:

        await ctx.send(
            "❌ Could not retrieve DRAGO BOT."
        )

        return

    # =====================================================
    # BOT MOVE PERMISSION
    # =====================================================

    if not bot_member.guild_permissions.move_members:

        await ctx.send(
            "❌ DRAGO BOT needs "
            "**Move Members** permission."
        )

        return

    # =====================================================
    # ROLE HIERARCHY
    # =====================================================

    if target_member.top_role >= bot_member.top_role:

        await ctx.send(
            f"❌ DRAGO BOT cannot move "
            f"{target_member.mention}.\n\n"
            "The bot's highest role must be higher "
            "than the member's highest role."
        )

        return

    # =====================================================
    # TEMP VC
    # =====================================================

    temporary_channel = None

    if starting_channel.id == bot_vc.id:

        temporary_channel = get_temporary_channel(
            guild,
            bot_vc
        )

        if temporary_channel is None:

            await ctx.send(
                "❌ **No temporary Voice Channel found!**\n\n"
                "Create another VC where the bot has "
                "**Connect + Move Members** permission."
            )

            return

    # =====================================================
    # SAVE DRAG INFORMATION
    # =====================================================

    drag_info[guild_id] = {

        "member_id": target_member.id,

        "starting_channel_id": starting_channel.id,

        "starting_channel_name": starting_channel.name,

        "bot_channel_id": bot_vc.id,

        "bot_channel_name": bot_vc.name,

        "temporary_channel_id": (
            temporary_channel.id
            if temporary_channel
            else None
        ),

        "temporary_channel_name": (
            temporary_channel.name
            if temporary_channel
            else None
        ),

        "total": count,

        "completed": 0,

        "remaining": count,

        "status": "running"
    }

    # =====================================================
    # START MESSAGE
    # =====================================================

    await ctx.send(
        f"🐉 **DRAGO STARTED!**\n\n"
        f"👤 Member: {target_member.mention}\n"
        f"🎯 Bot VC: **{bot_vc.name}**\n"
        f"↪️ Start VC: **{starting_channel.name}**\n\n"
        f"⚡ Speed: **{DRAG_DELAY:.2f}s FAST**\n"
        f"🔁 Rounds: **{count}**"
    )

    # =====================================================
    # DRAG TASK
    # =====================================================

    async def perform_drag():

        nonlocal temporary_channel

        completed = 0

        try:

            while completed < count:

                # =============================================
                # CHECK BOT VC
                # =============================================

                current_bot = guild.me

                if (
                    current_bot is None
                    or current_bot.voice is None
                    or current_bot.voice.channel is None
                ):

                    drag_info[guild_id]["status"] = "stopped"

                    await ctx.send(
                        "🛑 **DRAG STOPPED!**\n\n"
                        "DRAGO BOT left the VC."
                    )

                    return

                current_bot_vc = current_bot.voice.channel

                # =============================================
                # GET TARGET MEMBER
                # =============================================

                current_member = guild.get_member(
                    target_member.id
                )

                if current_member is None:

                    drag_info[guild_id]["status"] = "error"

                    await ctx.send(
                        "❌ Member is no longer in the server."
                    )

                    return

                # =============================================
                # MEMBER DISCONNECTED
                #
                # PAUSE BUT DON'T STOP
                # =============================================

                if (
                    current_member.voice is None
                    or current_member.voice.channel is None
                ):

                    drag_info[guild_id]["status"] = "paused"

                    remaining = count - completed

                    await ctx.send(
                        f"⏸️ **DRAGO PAUSED!**\n\n"
                        f"👤 {target_member.mention} "
                        f"disconnected from VC.\n\n"
                        f"✅ Completed: **{completed}/{count}**\n"
                        f"📊 Balance: **{remaining}**\n\n"
                        f"🔎 Waiting for the SAME MEMBER "
                        f"to rejoin ANY VC..."
                    )

                    # =========================================
                    # WAIT UNTIL SAME MEMBER REJOINS
                    # =========================================

                    while True:

                        before, after = await bot.wait_for(
                            "voice_state_update",
                            timeout=None,
                            check=lambda before, after: (
                                after.guild.id == guild_id
                                and after.member.id == target_member.id
                                and after.channel is not None
                            )
                        )

                        current_member = guild.get_member(
                            target_member.id
                        )

                        if (
                            current_member is not None
                            and current_member.voice is not None
                            and current_member.voice.channel is not None
                        ):

                            break

                    # =========================================
                    # RESUME
                    # =========================================

                    drag_info[guild_id]["status"] = "running"

                    await ctx.send(
                        f"▶️ **DRAGO RESUMED!**\n\n"
                        f"👤 {target_member.mention}\n"
                        f"🎙️ Rejoined: "
                        f"**{current_member.voice.channel.name}**\n\n"
                        f"📊 Continuing from "
                        f"**{completed + 1}/{count}**\n"
                        f"🔥 Balance: "
                        f"**{count - completed}**"
                    )

                # =============================================
                # REFRESH TARGET
                # =============================================

                current_member = guild.get_member(
                    target_member.id
                )

                if current_member is None:
                    continue

                if (
                    current_member.voice is None
                    or current_member.voice.channel is None
                ):
                    continue

                current_member_vc = (
                    current_member.voice.channel
                )

                # =============================================
                # CASE 1
                #
                # TARGET ALREADY IN BOT VC
                #
                # BOT VC
                #   ↓
                # TEMP VC
                #   ↓
                # BOT VC
                # =============================================

                if current_member_vc.id == current_bot_vc.id:

                    # =========================================
                    # FIND TEMP VC
                    # =========================================

                    if (
                        temporary_channel is None
                        or temporary_channel.id
                        == current_bot_vc.id
                    ):

                        temporary_channel = (
                            get_temporary_channel(
                                guild,
                                current_bot_vc
                            )
                        )

                    # =========================================
                    # NO TEMP VC
                    # =========================================

                    if temporary_channel is None:

                        drag_info[guild_id]["status"] = "error"

                        await ctx.send(
                            "❌ No temporary VC available."
                        )

                        return

                    # =========================================
                    # MOVE TO TEMP VC
                    # =========================================

                    await current_member.move_to(
                        temporary_channel,
                        reason=(
                            f"DRAGO round "
                            f"{completed + 1}"
                        )
                    )

                    await asyncio.sleep(
                        DRAG_DELAY
                    )

                    # =========================================
                    # REFRESH
                    # =========================================

                    current_member = guild.get_member(
                        target_member.id
                    )

                    # =========================================
                    # DISCONNECTED DURING MOVE
                    # =========================================

                    if (
                        current_member is None
                        or current_member.voice is None
                        or current_member.voice.channel is None
                    ):

                        continue

                    # =========================================
                    # MOVE BACK TO BOT VC
                    # =========================================

                    if (
                        current_member.voice.channel.id
                        == temporary_channel.id
                    ):

                        await current_member.move_to(
                            current_bot_vc,
                            reason=(
                                f"DRAGO round "
                                f"{completed + 1}"
                            )
                        )

                # =============================================
                # CASE 2
                #
                # TARGET IN ANOTHER VC
                #
                # OTHER VC
                #    ↓
                # BOT VC
                #    ↓
                # OTHER VC
                # =============================================

                else:

                    return_channel = current_member_vc

                    # =========================================
                    # MOVE TO BOT VC
                    # =========================================

                    await current_member.move_to(
                        current_bot_vc,
                        reason=(
                            f"DRAGO round "
                            f"{completed + 1}"
                        )
                    )

                    await asyncio.sleep(
                        DRAG_DELAY
                    )

                    # =========================================
                    # REFRESH TARGET
                    # =========================================

                    current_member = guild.get_member(
                        target_member.id
                    )

                    # =========================================
                    # DISCONNECTED
                    # =========================================

                    if (
                        current_member is None
                        or current_member.voice is None
                        or current_member.voice.channel is None
                    ):

                        continue

                    # =========================================
                    # RETURN TO ORIGINAL VC
                    # =========================================

                    if (
                        current_member.voice.channel.id
                        == current_bot_vc.id
                    ):

                        await current_member.move_to(
                            return_channel,
                            reason=(
                                f"DRAGO return round "
                                f"{completed + 1}"
                            )
                        )

                # =============================================
                # SMALL DELAY
                # =============================================

                await asyncio.sleep(
                    DRAG_DELAY
                )

                # =============================================
                # ROUND COMPLETED
                # =============================================

                completed += 1

                drag_info[guild_id]["completed"] = completed

                drag_info[guild_id]["remaining"] = (
                    count - completed
                )

                # NO ROUND MESSAGE
                # CHAT STAYS CLEAN

            # =================================================
            # ALL ROUNDS COMPLETED
            # =================================================

            drag_info[guild_id]["status"] = "completed"

            drag_info[guild_id]["remaining"] = 0

            await ctx.send(
                f"✅ **DRAG COMPLETED!**\n\n"
                f"👤 Member: {target_member.mention}\n\n"
                f"⚡ Speed: **{DRAG_DELAY:.2f}s FAST**\n"
                f"🔁 Total Rounds: **{count}**\n"
                f"✅ Completed: **{completed}**"
            )

        # =====================================================
        # MANUAL STOP
        # =====================================================

        except asyncio.CancelledError:

            remaining = count - completed

            drag_info[guild_id]["status"] = "stopped"

            drag_info[guild_id]["completed"] = completed

            drag_info[guild_id]["remaining"] = remaining

            await ctx.send(
                f"🛑 **DRAG STOPPED!**\n\n"
                f"👤 Member: {target_member.mention}\n\n"
                f"✅ Completed: **{completed}**\n"
                f"📊 Remaining: **{remaining}**"
            )

            raise

        # =====================================================
        # PERMISSION ERROR
        # =====================================================

        except discord.Forbidden:

            drag_info[guild_id]["status"] = "error"

            await ctx.send(
                "❌ **PERMISSION ERROR**\n\n"
                "Check:\n"
                "• Move Members\n"
                "• Bot role hierarchy\n"
                "• VC permissions"
            )

        # =====================================================
        # HTTP ERROR
        # =====================================================

        except discord.HTTPException as e:

            drag_info[guild_id]["status"] = "error"

            print(
                f"[DRAGO HTTP ERROR] {e}"
            )

            await ctx.send(
                f"❌ Discord API Error:\n`{e}`"
            )

        # =====================================================
        # OTHER ERROR
        # =====================================================

        except Exception as e:

            drag_info[guild_id]["status"] = "error"

            print(
                f"[DRAGO ERROR] {e}"
            )

            await ctx.send(
                f"❌ Unexpected Error:\n`{e}`"
            )

        # =====================================================
        # CLEANUP
        # =====================================================

        finally:

            drag_tasks.pop(
                guild_id,
                None
            )


    # =========================================================
    # CREATE DRAG TASK
    # =========================================================

    task = asyncio.create_task(
        perform_drag()
    )

    drag_tasks[guild_id] = task


# =========================================================
# STOP
#
# !stop
# =========================================================

@bot.command(name="stop")
@commands.has_permissions(move_members=True)
async def stop(ctx):

    guild_id = ctx.guild.id

    task = drag_tasks.get(guild_id)

    if task is None or task.done():

        await ctx.send(
            "⚪ No drag is currently running."
        )

        return

    task.cancel()


# =========================================================
# STATUS
#
# !status
# =========================================================

@bot.command(name="status")
async def status(ctx):

    guild_id = ctx.guild.id

    info = drag_info.get(guild_id)

    if info is None:

        await ctx.send(
            "⚪ No drag information available."
        )

        return

    bot_vc = get_bot_voice_channel(
        ctx.guild
    )

    bot_vc_name = (
        bot_vc.name
        if bot_vc
        else "NOT IN VC"
    )

    await ctx.send(
        f"📊 **DRAGO STATUS**\n\n"
        f"🎙️ Bot VC: **{bot_vc_name}**\n"
        f"👤 Member: <@{info['member_id']}>\n\n"
        f"📍 Starting VC: "
        f"**{info['starting_channel_name']}**\n"
        f"🎯 Bot VC: "
        f"**{info['bot_channel_name']}**\n\n"
        f"🔁 Total: **{info['total']}**\n"
        f"✅ Completed: **{info['completed']}**\n"
        f"📊 Remaining: **{info['remaining']}**\n"
        f"📌 Status: "
        f"**{info['status'].upper()}**"
    )


# =========================================================
# HELP
#
# !helpme
# =========================================================

@bot.command(name="helpme")
async def helpme(ctx):

    await ctx.send(
        "🐉 **DRAGO BOT COMMANDS**\n\n"

        "🎙️ **JOIN**\n"
        "`!join`\n"
        "→ Bot joins your VC.\n\n"

        "⚡ **DRAG**\n"
        "`!drag @member count`\n"
        "→ Starts fast VC dragging.\n"
        "→ Member disconnects = PAUSE.\n"
        "→ Same member rejoins ANY VC = RESUME.\n"
        "→ Remaining rounds continue automatically.\n\n"

        "🛑 **STOP**\n"
        "`!stop`\n"
        "→ Stops current drag.\n\n"

        "📊 **STATUS**\n"
        "`!status`\n"
        "→ Shows drag status.\n\n"

        "👋 **LEAVE**\n"
        "`!leave`\n"
        "→ Bot leaves VC.\n\n"

        "**Example:**\n"
        "`!drag @User 100`"
    )


# =========================================================
# COMMAND ERROR HANDLER
# =========================================================

@bot.event
async def on_command_error(ctx, error):

    if isinstance(
        error,
        commands.CommandNotFound
    ):
        return

    if isinstance(
        error,
        commands.MissingPermissions
    ):

        await ctx.send(
            "❌ You need the "
            "**Move Members** permission."
        )

        return

    if isinstance(
        error,
        commands.MissingRequiredArgument
    ):

        await ctx.send(
            "❌ **Missing argument!**\n\n"
            "Use:\n"
            "`!drag @member count`\n\n"
            "Example:\n"
            "`!drag @User 100`"
        )

        return

    if isinstance(
        error,
        commands.MemberNotFound
    ):

        await ctx.send(
            "❌ Member not found.\n\n"
            "Please mention a valid "
            "server member."
        )

        return

    if isinstance(
        error,
        commands.BadArgument
    ):

        await ctx.send(
            "❌ **Invalid command!**\n\n"
            "Use:\n"
            "`!drag @member count`\n\n"
            "Example:\n"
            "`!drag @User 100`"
        )

        return

    print(
        f"[COMMAND ERROR] {error}"
    )


# =========================================================
# START BOT
# =========================================================

if __name__ == "__main__":

    print(
        "🐉 Starting DRAGO BOT..."
    )

    try:

        bot.run(TOKEN)

    except discord.LoginFailure:

        print(
            "❌ Login Failed!\n\n"
            "Check your DISCORD_TOKEN "
            "inside .env"
        )

    except Exception as e:

        print(
            f"❌ Error starting bot: {e}"
        )