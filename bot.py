import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import asyncio

# ── Config ───────────────────────────────────────────────────────────────────

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def get_guild_config(guild_id: int):
    config = load_config()
    gid = str(guild_id)
    if gid not in config:
        config[gid] = {
            "base_roles": {},
            "paths": {},
            "messages": {
                "enforcing": "🔄 Enforcing paths...",
                "done": "✅ Enforcement complete."
            },
            "log_channel": None,
            "path_colors": {}
        }
        save_config(config)
    return config[gid]

def save_guild_config(guild_id: int, guild_config: dict):
    config = load_config()
    config[str(guild_id)] = guild_config
    save_config(config)

def get_role_name(entry):
    """Supports both old string entries and new dict entries with rank."""
    if isinstance(entry, dict):
        return entry["role"]
    return entry

def get_role_rank(entry):
    """Returns rank for sorting. Old string entries default to 0."""
    if isinstance(entry, dict):
        return entry.get("rank", 0)
    return 0

# ── Bot setup ────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

INVITE_LINK = "https://discord.com/oauth2/authorize?client_id=1512983777964724306&scope=bot&permissions=268435456"

# ── Helper ───────────────────────────────────────────────────────────────────

async def send_log(guild: discord.Guild, message: str):
    guild_config = get_guild_config(guild.id)
    log_channel_id = guild_config.get("log_channel")
    if log_channel_id:
        channel = guild.get_channel(int(log_channel_id))
        if channel:
            try:
                await channel.send(message)
            except Exception:
                pass

async def enforce_single_path(member: discord.Member) -> None:
    guild_config = get_guild_config(member.guild.id)
    base_roles = guild_config.get("base_roles", {})
    paths = guild_config.get("paths", {})

    member_role_names_lower = {r.name.lower() for r in member.roles}

    active_path = None
    for base_role, path in base_roles.items():
        if base_role.lower() in member_role_names_lower:
            active_path = path
            break

    if active_path is None:
        return

    all_cultivation_lower = {get_role_name(e).lower() for p in paths.values() for e in p}
    allowed_lower = {get_role_name(e).lower() for e in paths.get(active_path, [])}

    roles_to_remove = [
        r for r in member.roles
        if r.name.lower() in all_cultivation_lower and r.name.lower() not in allowed_lower
    ]

    if roles_to_remove:
        try:
            await member.remove_roles(*roles_to_remove, reason="Path enforcement")
            removed_names = ", ".join(r.name for r in roles_to_remove)
            print(f"[INFO] Removed {removed_names} from {member.display_name}")
            await send_log(member.guild, f"🔧 Removed **{removed_names}** from **{member.display_name}**")
        except discord.Forbidden:
            print(f"[WARN] Missing permissions to remove roles from {member.display_name}")
            await send_log(member.guild, f"⚠️ Missing permission — make sure the S3NN role is above all managed roles in Server Settings → Roles.")
            try:
                channel = discord.utils.get(member.guild.text_channels, name="general") or member.guild.text_channels[0]
                await channel.send("⚠️ Missing permission — make sure the S3NN role is above all managed roles in Server Settings → Roles.")
            except Exception:
                pass
        except discord.HTTPException as e:
            print(f"[ERROR] Failed to remove roles from {member.display_name}: {e}")

# ── Events ───────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

    for guild in bot.guilds:
        print(f"[INFO] Checking all members in {guild.name}...")
        for member in guild.members:
            await enforce_single_path(member)
            await asyncio.sleep(0.5)
        print(f"[INFO] Done checking {guild.name}.")

    print("Bot is online.")


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if before.roles == after.roles:
        return
    await enforce_single_path(after)

# ── Slash Commands ────────────────────────────────────────────────────────────

@bot.tree.command(name="help", description="Learn what S3NN does and how to invite it")
async def help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="S3NN — Role Path Enforcer",
        description="S3NN automatically ensures members only hold roles from their chosen path. When a role is assigned, S3NN removes any conflicting roles from other paths instantly and silently.",
        color=discord.Color.dark_grey()
    )
    embed.add_field(name="🔧 Admin Commands", value="`/setup` `/setpath` `/addrole` `/removepath` `/removerole` `/viewpaths` `/enforce` `/setmessages` `/setlog` `/reset`", inline=False)
    embed.add_field(name="👤 Member Commands", value="`/profile` `/pathstats` `/leaderboard`", inline=False)
    embed.add_field(name="📨 Invite S3NN", value=f"[Click here to invite S3NN]({INVITE_LINK})", inline=False)
    embed.set_footer(text="All admin commands are only visible to administrators.")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="invite", description="Get the invite link for S3NN")
async def invite(interaction: discord.Interaction):
    await interaction.response.send_message(f"📨 Invite S3NN to your server:\n{INVITE_LINK}", ephemeral=True)


@bot.tree.command(name="ping", description="Check if S3NN is online")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! `{round(bot.latency * 1000)}ms`")


@bot.tree.command(name="setup", description="Show setup guide and command list")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    msg = """**📋 S3NN Setup Guide**

**1. Register your base roles** (the roles members choose from):
`/setpath base_role:Role Name path_name:internal_name`
*Example: `/setpath base_role:Demonic Path path_name:demonic`*

**2. Add level roles to each path (with rank):**
`/addrole path_name:internal_name role:Role Name rank:1`
The `rank` number determines leaderboard order — use 1 for the lowest level and 5 for the highest.
*Example: `/addrole path_name:demonic role:Demon Initiate rank:1`*
*Example: `/addrole path_name:demonic role:Demon Lord rank:5`*

**3. Set a log channel (optional):**
`/setlog channel:#your-channel`

**4. Customize enforce messages (optional):**
`/setmessages enforcing:Your message here done:Your done message`

**5. Set a color per path (optional):**
`/setpathcolor path_name:demonic hex_color:#FF0000`

**6. View your current setup:**
`/viewpaths`

**7. Run enforcement manually:**
`/enforce`

**8. Fix a specific member:**
`/verify member:@someone`

**9. Reset everything and start over:**
`/reset`

**Member commands:** `/profile` `/pathstats` `/leaderboard`

Make sure the **S3NN role is above all managed roles** in Server Settings → Roles!"""
    await interaction.response.send_message(msg, ephemeral=True)


@bot.tree.command(name="setlog", description="Set a channel for S3NN to log role removals")
@app_commands.describe(channel="The channel to send logs to")
@app_commands.checks.has_permissions(administrator=True)
async def setlog(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_config = get_guild_config(interaction.guild.id)
    guild_config["log_channel"] = str(channel.id)
    save_guild_config(interaction.guild.id, guild_config)
    await interaction.response.send_message(f"✅ Log channel set to {channel.mention}.", ephemeral=True)


@bot.tree.command(name="setpath", description="Register a base path role")
@app_commands.describe(base_role="The base role name", path_name="Internal path name (e.g. demonic)")
@app_commands.checks.has_permissions(administrator=True)
async def setpath(interaction: discord.Interaction, base_role: str, path_name: str):
    guild_config = get_guild_config(interaction.guild.id)
    guild_config["base_roles"][base_role] = path_name
    if path_name not in guild_config["paths"]:
        guild_config["paths"][path_name] = []
    save_guild_config(interaction.guild.id, guild_config)
    await interaction.response.send_message(f"✅ Base role **{base_role}** linked to path **{path_name}**.", ephemeral=True)


@bot.tree.command(name="addrole", description="Add a level role to a path")
@app_commands.describe(path_name="Internal path name", role="The role name to add", rank="Rank of this role (1 = lowest, 5 = highest)")
@app_commands.checks.has_permissions(administrator=True)
async def addrole(interaction: discord.Interaction, path_name: str, role: str, rank: int):
    guild_config = get_guild_config(interaction.guild.id)
    if path_name not in guild_config["paths"]:
        guild_config["paths"][path_name] = []

    # Remove any existing entry for this role name (case-insensitive) to avoid duplicates
    guild_config["paths"][path_name] = [
        e for e in guild_config["paths"][path_name]
        if get_role_name(e).lower() != role.lower()
    ]
    guild_config["paths"][path_name].append({"role": role, "rank": rank})
    save_guild_config(interaction.guild.id, guild_config)
    await interaction.response.send_message(f"✅ Role **{role}** added to path **{path_name}** at rank **{rank}**.", ephemeral=True)


@bot.tree.command(name="removepath", description="Remove a base path role")
@app_commands.describe(base_role="The base role name to remove")
@app_commands.checks.has_permissions(administrator=True)
async def removepath(interaction: discord.Interaction, base_role: str):
    guild_config = get_guild_config(interaction.guild.id)
    if base_role in guild_config["base_roles"]:
        del guild_config["base_roles"][base_role]
        save_guild_config(interaction.guild.id, guild_config)
        await interaction.response.send_message(f"✅ Base role **{base_role}** removed.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Base role **{base_role}** not found.", ephemeral=True)


@bot.tree.command(name="removerole", description="Remove a level role from a path")
@app_commands.describe(path_name="Internal path name", role="The role name to remove")
@app_commands.checks.has_permissions(administrator=True)
async def removerole(interaction: discord.Interaction, path_name: str, role: str):
    guild_config = get_guild_config(interaction.guild.id)
    if path_name in guild_config["paths"]:
        original = guild_config["paths"][path_name]
        updated = [e for e in original if get_role_name(e).lower() != role.lower()]
        if len(updated) < len(original):
            guild_config["paths"][path_name] = updated
            save_guild_config(interaction.guild.id, guild_config)
            await interaction.response.send_message(f"✅ Role **{role}** removed from path **{path_name}**.", ephemeral=True)
            return
    await interaction.response.send_message(f"❌ Role **{role}** not found in path **{path_name}**.", ephemeral=True)


@bot.tree.command(name="viewpaths", description="View all configured paths and roles")
@app_commands.checks.has_permissions(administrator=True)
async def viewpaths(interaction: discord.Interaction):
    guild_config = get_guild_config(interaction.guild.id)
    base_roles = guild_config.get("base_roles", {})
    paths = guild_config.get("paths", {})

    if not base_roles and not paths:
        await interaction.response.send_message("❌ No paths configured yet. Use `/setup` to get started.", ephemeral=True)
        return

    msg = "**Current Path Configuration:**\n\n"
    for base_role, path_name in base_roles.items():
        entries = paths.get(path_name, [])
        sorted_entries = sorted(entries, key=get_role_rank)
        if sorted_entries:
            roles_str = ", ".join(f"{get_role_name(e)} (rank {get_role_rank(e)})" for e in sorted_entries)
        else:
            roles_str = "No roles added yet"
        msg += f"**{base_role}** (`{path_name}`)\n{roles_str}\n\n"

    await interaction.response.send_message(msg, ephemeral=True)


@bot.tree.command(name="setmessages", description="Customize the messages the bot sends during enforcement")
@app_commands.describe(enforcing="Message shown when enforcement starts", done="Message shown when enforcement is complete")
@app_commands.checks.has_permissions(administrator=True)
async def setmessages(interaction: discord.Interaction, enforcing: str, done: str):
    guild_config = get_guild_config(interaction.guild.id)
    guild_config["messages"]["enforcing"] = enforcing
    guild_config["messages"]["done"] = done
    save_guild_config(interaction.guild.id, guild_config)
    await interaction.response.send_message(f"✅ Messages updated!\n**Start:** {enforcing}\n**Done:** {done}", ephemeral=True)


@bot.tree.command(name="enforce", description="Manually enforce paths for all members")
@app_commands.checks.has_permissions(administrator=True)
async def enforce(interaction: discord.Interaction):
    guild_config = get_guild_config(interaction.guild.id)
    messages = guild_config.get("messages", {})
    enforcing_msg = messages.get("enforcing", "🔄 Enforcing paths...")
    done_msg = messages.get("done", "✅ Enforcement complete.")

    await interaction.response.send_message(enforcing_msg)
    for member in interaction.guild.members:
        await enforce_single_path(member)
        await asyncio.sleep(0.5)
    await interaction.followup.send(done_msg)


@bot.tree.command(name="reset", description="Reset all path configuration for this server")
@app_commands.checks.has_permissions(administrator=True)
async def reset(interaction: discord.Interaction):
    config = load_config()
    gid = str(interaction.guild.id)
    if gid in config:
        del config[gid]
        save_config(config)
    await interaction.response.send_message("✅ All path configuration for this server has been reset.", ephemeral=True)


@bot.tree.command(name="verify", description="Check and fix a specific member's roles")
@app_commands.describe(member="The member to verify")
@app_commands.checks.has_permissions(administrator=True)
async def verify(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)
    await enforce_single_path(member)
    await interaction.followup.send(f"✅ Verified and fixed roles for **{member.display_name}**.", ephemeral=True)


@bot.tree.command(name="pathstats", description="Show how many members are in each path")
async def pathstats(interaction: discord.Interaction):
    guild_config = get_guild_config(interaction.guild.id)
    base_roles = guild_config.get("base_roles", {})

    if not base_roles:
        await interaction.response.send_message("❌ No paths configured yet.", ephemeral=True)
        return

    counts = {base_role: 0 for base_role in base_roles}
    for member in interaction.guild.members:
        member_role_names_lower = {r.name.lower() for r in member.roles}
        for base_role in base_roles:
            if base_role.lower() in member_role_names_lower:
                counts[base_role] += 1
                break

    embed = discord.Embed(title="⚔️ Path Statistics", color=discord.Color.dark_grey())
    total = sum(counts.values())
    for base_role, count in counts.items():
        percent = round((count / total) * 100) if total > 0 else 0
        embed.add_field(name=base_role, value=f"{count} members ({percent}%)", inline=False)
    embed.set_footer(text=f"Total members with a path: {total}")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="profile", description="Show a member's full path profile")
@app_commands.describe(member="The member to view (leave empty for yourself)")
async def profile(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    guild_config = get_guild_config(interaction.guild.id)
    base_roles = guild_config.get("base_roles", {})
    paths = guild_config.get("paths", {})

    member_role_names_lower = {r.name.lower() for r in member.roles}

    active_path = None
    active_base_role = None
    for base_role, path in base_roles.items():
        if base_role.lower() in member_role_names_lower:
            active_path = path
            active_base_role = base_role
            break

    embed = discord.Embed(title=f"{member.display_name}'s Profile", color=discord.Color.dark_grey())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="📅 Joined", value=member.joined_at.strftime("%b %d, %Y") if member.joined_at else "Unknown", inline=True)

    if not active_path:
        embed.add_field(name="⚔️ Path", value="No path assigned", inline=True)
    else:
        path_entries = paths.get(active_path, [])
        highest_entry = None
        for entry in path_entries:
            role_name = get_role_name(entry)
            if role_name.lower() in member_role_names_lower:
                if highest_entry is None or get_role_rank(entry) > get_role_rank(highest_entry):
                    highest_entry = entry

        path_colors = guild_config.get("path_colors", {})
        hex_color = path_colors.get(active_path)
        if hex_color:
            try:
                color = discord.Color(int(hex_color.strip("#"), 16))
            except Exception:
                color = discord.Color.dark_grey()
        else:
            color = discord.Color.dark_grey()
        embed.color = color

        embed.add_field(name="⚔️ Path", value=active_base_role, inline=True)
        embed.add_field(name="🏆 Highest Role", value=get_role_name(highest_entry) if highest_entry else "None", inline=True)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="setpathcolor", description="Set the embed color for a path's profile")
@app_commands.describe(path_name="Internal path name (e.g. demonic)", hex_color="Hex color code (e.g. #FF0000)")
@app_commands.checks.has_permissions(administrator=True)
async def setpathcolor(interaction: discord.Interaction, path_name: str, hex_color: str):
    try:
        int(hex_color.strip("#"), 16)
    except ValueError:
        await interaction.response.send_message("❌ Invalid hex color. Example: `#FF0000`", ephemeral=True)
        return

    guild_config = get_guild_config(interaction.guild.id)
    if "path_colors" not in guild_config:
        guild_config["path_colors"] = {}
    guild_config["path_colors"][path_name] = hex_color.strip("#")
    save_guild_config(interaction.guild.id, guild_config)
    await interaction.response.send_message(f"✅ Color for path **{path_name}** set to `#{hex_color.strip('#')}`.", ephemeral=True)


@bot.tree.command(name="leaderboard", description="Show top cultivators ranked by level in each path")
@app_commands.describe(path_name="Filter by a specific path (leave empty for all paths)")
async def leaderboard(interaction: discord.Interaction, path_name: str = None):
    guild_config = get_guild_config(interaction.guild.id)
    base_roles = guild_config.get("base_roles", {})
    paths = guild_config.get("paths", {})

    if not base_roles:
        await interaction.response.send_message("❌ No paths configured yet.", ephemeral=True)
        return

    # Build reverse lookup: path_name -> base_role display name
    path_to_base_role = {v: k for k, v in base_roles.items()}

    # Filter to specific path if provided
    if path_name:
        if path_name not in paths:
            await interaction.response.send_message(f"❌ Path **{path_name}** not found.", ephemeral=True)
            return
        paths_to_show = {path_name: paths[path_name]}
    else:
        paths_to_show = paths

    embed = discord.Embed(title="🏆 Leaderboard", color=discord.Color.dark_grey())

    for pname, entries in paths_to_show.items():
        if not entries:
            continue

        # Build a dict of role_name_lower -> rank for quick lookup
        role_rank_map = {get_role_name(e).lower(): get_role_rank(e) for e in entries}

        # Score each member: find their highest ranked role in this path
        scored = []
        for member in interaction.guild.members:
            if member.bot:
                continue
            member_role_names_lower = {r.name.lower() for r in member.roles}
            best_rank = 0
            best_role_name = None
            for role_lower, rank in role_rank_map.items():
                if role_lower in member_role_names_lower and rank > best_rank:
                    best_rank = rank
                    best_role_name = role_lower
            if best_role_name:
                # Get the display name of the role (original casing)
                display_role = next(
                    (get_role_name(e) for e in entries if get_role_name(e).lower() == best_role_name),
                    best_role_name
                )
                scored.append((member.display_name, display_role, best_rank))

        scored.sort(key=lambda x: x[2], reverse=True)
        top = scored[:5]

        if not top:
            continue

        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        lines = []
        for i, (name, role, rank) in enumerate(top):
            lines.append(f"{medals[i]} **{name}** — {role}")

        base_role_display = path_to_base_role.get(pname, pname)
        embed.add_field(name=f"⚔️ {base_role_display}", value="\n".join(lines), inline=False)

    if not embed.fields:
        await interaction.response.send_message("❌ No members with ranked roles found.", ephemeral=True)
        return

    embed.set_footer(text="Rankings based on highest assigned level role per path.")
    await interaction.response.send_message(embed=embed)


# ── Run ──────────────────────────────────────────────────────────────────────

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise ValueError("No DISCORD_TOKEN environment variable set!")

bot.run(TOKEN)
