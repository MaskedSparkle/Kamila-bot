import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import traceback
import re
from flask import Flask
import threading
import datetime

app_web = Flask(__name__)
@app_web.route('/')
def home():
    return "Kamila CUSTOM FULL - Kick/Ban/Unban + Custom Filters"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host='0.0.0.0', port=port)

threading.Thread(target=run_web, daemon=True).start()

DATA_FILE = "kamila_data.json"

DEFAULT_NSFW = [r'\b(pornhub|onlyfans|xvideos|xnxx)\.com\b', r'discord\.gg/.*nsfw', r'onlyfans\.com/']
DEFAULT_BAD_HARD = [r'\bkurva\b', r'baszd meg', r'\bkurva anyád\b', r'\bbuzi\b', r'\bgeci\b']
DEFAULT_BAD_SOFT = [r'\bhülye\b', r'\bidi[oó]ta?\b', r'\bfasz\b']

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                for gid in raw:
                    raw[gid]["kicked"] = set(raw[gid].get("kicked", []))
                    raw[gid]["banned"] = set(raw[gid].get("banned", []))
                    raw[gid]["warnings"] = raw[gid].get("warnings", {})
                    # defaults
                    if "threshold" not in raw[gid]: raw[gid]["threshold"] = 3
                    if "nsfw_enabled" not in raw[gid]: raw[gid]["nsfw_enabled"] = True
                    if "badwords_enabled" not in raw[gid]: raw[gid]["badwords_enabled"] = True
                    if "spam_enabled" not in raw[gid]: raw[gid]["spam_enabled"] = True
                    if "nsfw_patterns" not in raw[gid]: raw[gid]["nsfw_patterns"] = DEFAULT_NSFW.copy()
                    if "badwords_hard" not in raw[gid]: raw[gid]["badwords_hard"] = DEFAULT_BAD_HARD.copy()
                    if "badwords_soft" not in raw[gid]: raw[gid]["badwords_soft"] = DEFAULT_BAD_SOFT.copy()
                    if "admin_channel" not in raw[gid]: raw[gid]["admin_channel"] = None
                return raw
        except Exception as e:
            print(f"Load error: {e}")
    return {}

def save_data(guild_data):
    try:
        to_save = {}
        for gid, data in guild_data.items():
            to_save[gid] = {
                "warnings": data.get("warnings", {}),
                "kicked": list(data.get("kicked", set())),
                "banned": list(data.get("banned", set())),
                "admin_channel": data.get("admin_channel"),
                "threshold": data.get("threshold", 3),
                "nsfw_enabled": data.get("nsfw_enabled", True),
                "badwords_enabled": data.get("badwords_enabled", True),
                "spam_enabled": data.get("spam_enabled", True),
                "nsfw_patterns": data.get("nsfw_patterns", DEFAULT_NSFW.copy()),
                "badwords_hard": data.get("badwords_hard", DEFAULT_BAD_HARD.copy()),
                "badwords_soft": data.get("badwords_soft", DEFAULT_BAD_SOFT.copy()),
            }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Save error: {e}")

class Kamila(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.messages = True
        intents.guilds = True
        intents.bans = True 
        super().__init__(command_prefix='!', intents=intents)
        self.guild_data = load_data()

    def get_guild_data(self, guild_id):
        gid = str(guild_id)
        if gid not in self.guild_data:
            self.guild_data[gid] = {
                "warnings": {}, "kicked": set(), "banned": set(),
                "admin_channel": None,
                "threshold": 3,
                "nsfw_enabled": True,
                "badwords_enabled": True,
                "spam_enabled": True,
                "nsfw_patterns": DEFAULT_NSFW.copy(),
                "badwords_hard": DEFAULT_BAD_HARD.copy(),
                "badwords_soft": DEFAULT_BAD_SOFT.copy(),
            }
        # ensure defaults
        g = self.guild_data[gid]
        for k, v in [("threshold", 3), ("nsfw_enabled", True), ("badwords_enabled", True), ("spam_enabled", True)]:
            if k not in g: g[k] = v
        for k, v in [("nsfw_patterns", DEFAULT_NSFW.copy()), ("badwords_hard", DEFAULT_BAD_HARD.copy()), ("badwords_soft", DEFAULT_BAD_SOFT.copy()), ("banned", set())]:
            if k not in g: g[k] = v if not isinstance(v, set) else set()
        return g

    def get_admin_channel_id(self, guild):
        gdata = self.get_guild_data(guild.id)
        if gdata.get("admin_channel"):
            return gdata["admin_channel"]
        for ch in guild.text_channels:
            if "log" in ch.name.lower():
                return ch.id
        return None

    async def log_to_admin(self, guild, message=None, embed=None):
        try:
            cid = self.get_admin_channel_id(guild)
            if not cid:
                for ch in guild.text_channels:
                    if ch.permissions_for(guild.me).send_messages:
                        cid = ch.id; break
            ch = self.get_channel(cid) if cid else None
            if not ch: return
            if message: await ch.send(message)
            elif embed: await ch.send(embed=embed)
        except: pass

    async def check_rule_violations(self, message, guild_id):
        gdata = self.get_guild_data(guild_id)
        content = message.content
        violations = []

        if gdata.get("nsfw_enabled"):
            for p in gdata.get("nsfw_patterns", []):
                try:
                    if re.search(p, content, re.I):
                        violations.append(f"NSFW link: {p}")
                        break
                except: pass

        if gdata.get("badwords_enabled"):
            for p in gdata.get("badwords_hard", []):
                try:
                    if re.search(p, content, re.I):
                        violations.append(f"Durva szó: {p}")
                        break
                except: pass
            if not violations:
                for p in gdata.get("badwords_soft", []):
                    try:
                        if re.search(p, content, re.I):
                            violations.append(f"Enyhe szó: {p}")
                            break
                    except: pass

        if gdata.get("spam_enabled"):
            if len(content) > 800 or content.count('http') > 4 or len(content.split()) > 100:
                violations.append("SPAM")

        return violations

    async def handle_violation(self, message, violations):
        gdata = self.get_guild_data(message.guild.id)
        uid = str(message.author.id)
        gdata["warnings"][uid] = gdata["warnings"].get(uid, 0) + 1
        threshold = gdata.get("threshold", 3)
        save_data(self.guild_data)
        
        try: await message.delete()
        except: pass

        if gdata["warnings"][uid] < threshold:
            try:
                await message.channel.send(f"⚠ {message.author.mention} **{gdata['warnings'][uid]}/{threshold} figyelmeztetés!** Ok: {violations[0]}", delete_after=15)
            except: pass
            await self.log_to_admin(message.guild, f"⚠ {message.author.name} warn {gdata['warnings'][uid]}/{threshold} | {violations}")
        else:
            # threshold elérve -> kick vagy ban? beállítás szerint ban ha threshold >=5? most kick + opcionális ban
            gdata["kicked"].add(uid)
            save_data(self.guild_data)
            try:
                await message.author.kick(reason=f"Kamila: {threshold} figyelmeztetés elérve - {violations}")
                await message.channel.send(f"👢 {message.author.mention} kickelve! {threshold} warn elérve.", delete_after=10)
                await self.log_to_admin(message.guild, f"👢 KICK {message.author.name} | {threshold}/{threshold} | {violations}")
            except Exception as e:
                await self.log_to_admin(message.guild, f"❌ Kick hiba {message.author.name}: {e}")

    async def setup_hook(self):
        print("🔧 Kamila CUSTOM setup_hook...")

        @self.tree.command(name="warnings", description="Figyelmeztetések megnézése")
        @app_commands.describe(member="Kinek nézzük")
        async def warnings(interaction: discord.Interaction, member: discord.Member = None):
            try:
                await interaction.response.defer(ephemeral=True)
                gdata = self.get_guild_data(interaction.guild.id)
                target = member or interaction.user
                cnt = gdata["warnings"].get(str(target.id), 0)
                threshold = gdata.get("threshold", 3)
                await interaction.followup.send(f"**{target.name}: {cnt}/{threshold} figyelmeztetés**", ephemeral=True)
            except Exception as e:
                print(traceback.format_exc())
                try: await interaction.followup.send(f"❌ {e}", ephemeral=True)
                except: pass

        @self.tree.command(name="clearwarnings", description="Figyelmeztetések törlése")
        @app_commands.describe(member="Kinek töröljük")
        async def clearwarnings(interaction: discord.Interaction, member: discord.Member):
            try:
                await interaction.response.defer()
                if not interaction.user.guild_permissions.administrator and not interaction.user.guild_permissions.kick_members:
                    await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
                gdata = self.get_guild_data(interaction.guild.id)
                gdata["warnings"][str(member.id)] = 0
                gdata["kicked"].discard(str(member.id))
                save_data(self.guild_data)
                await interaction.followup.send(f"✅ {member.name} warnjai törölve ezen a szerveren: {interaction.guild.name}")
            except Exception as e:
                print(traceback.format_exc())

        @self.tree.command(name="setlog", description="Log csatorna beállítása")
        @app_commands.describe(channel="Melyik csatornába logoljon")
        async def setlog(interaction: discord.Interaction, channel: discord.TextChannel):
            try:
                await interaction.response.defer(ephemeral=True)
                if not interaction.user.guild_permissions.administrator:
                    await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
                gdata = self.get_guild_data(interaction.guild.id)
                gdata["admin_channel"] = channel.id
                save_data(self.guild_data)
                await interaction.followup.send(f"✅ Log csatorna: {channel.mention} | Szerver: {interaction.guild.name}", ephemeral=True)
            except Exception as e:
                print(traceback.format_exc())

        @self.tree.command(name="setthreshold", description="Hány figyelmeztetés után kickeljen (custom)")
        @app_commands.describe(count="Hány warn után kick/ban pl: 3, 5, 10")
        async def setthreshold(interaction: discord.Interaction, count: int):
            try:
                await interaction.response.defer(ephemeral=True)
                if not interaction.user.guild_permissions.administrator:
                    await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
                if count < 1 or count > 20:
                    await interaction.followup.send("❌ 1 és 20 között add meg!", ephemeral=True); return
                gdata = self.get_guild_data(interaction.guild.id)
                gdata["threshold"] = count
                save_data(self.guild_data)
                await interaction.followup.send(f"✅ Threshold beállítva: **{count}** warn után kick | Szerver: {interaction.guild.name}", ephemeral=True)
            except Exception as e:
                print(traceback.format_exc())

        @self.tree.command(name="kick", description="Tag kickelése")
        @app_commands.describe(member="Kit kickeljen", reason="Indok")
        async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Nincs indok"):
            try:
                await interaction.response.defer()
                if not interaction.user.guild_permissions.kick_members:
                    await interaction.followup.send("❌ Nincs jogod kickelni!", ephemeral=True); return
                if member.guild_permissions.administrator:
                    await interaction.followup.send("❌ Admin-t nem kickelhetsz!", ephemeral=True); return
                try:
                    await member.kick(reason=f"{interaction.user.name}: {reason}")
                    gdata = self.get_guild_data(interaction.guild.id)
                    gdata["kicked"].add(str(member.id))
                    save_data(self.guild_data)
                    await interaction.followup.send(f"👢 {member.name} kickelve! Indok: {reason}")
                    await self.log_to_admin(interaction.guild, f"👢 KICK {member.name} által: {interaction.user.name} | Indok: {reason}")
                except Exception as e:
                    await interaction.followup.send(f"❌ Kick hiba: {e}", ephemeral=True)
            except Exception as e:
                print(traceback.format_exc())

        @self.tree.command(name="ban", description="Tag bannolása")
        @app_commands.describe(member="Kit bannoljon", reason="Indok", delete_days="Hány nap üzenetét törölje (0-7)")
        async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Nincs indok", delete_days: int = 0):
            try:
                await interaction.response.defer()
                if not interaction.user.guild_permissions.ban_members:
                    await interaction.followup.send("❌ Nincs jogod bannolni!", ephemeral=True); return
                if member.guild_permissions.administrator:
                    await interaction.followup.send("❌ Admin-t nem bannolhatsz!", ephemeral=True); return
                if delete_days < 0 or delete_days > 7:
                    delete_days = 0
                try:
                    await member.ban(reason=f"{interaction.user.name}: {reason}", delete_message_days=delete_days)
                    gdata = self.get_guild_data(interaction.guild.id)
                    gdata["banned"].add(str(member.id))
                    save_data(self.guild_data)
                    await interaction.followup.send(f"🔨 {member.name} bannolva! Indok: {reason}")
                    await self.log_to_admin(interaction.guild, f"🔨 BAN {member.name} által: {interaction.user.name} | Indok: {reason}")
                    
                except Exception as e:
                    await interaction.followup.send(f"❌ Ban hiba: {e}", ephemeral=True)
            except Exception as e:
                print(traceback.format_exc())

        @self.tree.command(name="unban", description="Tag unbannolása ID alapján")
        @app_commands.describe(user_id="Bannolt felhasználó ID-ja", reason="Indok")
        async def unban(interaction: discord.Interaction, user_id: str, reason: str = "Unban"):
            try:
                await interaction.response.defer()
                if not interaction.user.guild_permissions.ban_members:
                    await interaction.followup.send("❌ Nincs jogod unbannolni!", ephemeral=True); return
                try:
                    user = await self.fetch_user(int(user_id))
                    await interaction.guild.unban(user, reason=f"{interaction.user.name}: {reason}")
                    gdata = self.get_guild_data(interaction.guild.id)
                    gdata["banned"].discard(str(user_id))
                    save_data(self.guild_data)
                    await interaction.followup.send(f"✅ {user.name} ({user.id}) unbannolva! Indok: {reason}")
                    await self.log_to_admin(interaction.guild, f"✅ UNBAN {user.name} által: {interaction.user.name} | {reason}")
                except Exception as e:
                    await interaction.followup.send(f"❌ Unban hiba: {e} (Biztos jó az ID?)", ephemeral=True)
            except Exception as e:
                print(traceback.format_exc())

        @self.tree.command(name="togglenfsfw", description="NSFW link szűrés ki/be")
        @app_commands.choices(state=[app_commands.Choice(name="Be", value="on"), app_commands.Choice(name="Ki", value="off")])
        async def togglenfsfw(interaction: discord.Interaction, state: str):
            try:
                await interaction.response.defer(ephemeral=True)
                if not interaction.user.guild_permissions.administrator:
                    await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
                gdata = self.get_guild_data(interaction.guild.id)
                gdata["nsfw_enabled"] = state == "on"
                save_data(self.guild_data)
                await interaction.followup.send(f"✅ NSFW szűrés: {'BE' if gdata['nsfw_enabled'] else 'KI'}", ephemeral=True)
            except: pass

        @self.tree.command(name="togglebadwords", description="Csúnya beszéd szűrés ki/be")
        @app_commands.choices(state=[app_commands.Choice(name="Be", value="on"), app_commands.Choice(name="Ki", value="off")])
        async def togglebadwords(interaction: discord.Interaction, state: str):
            try:
                await interaction.response.defer(ephemeral=True)
                if not interaction.user.guild_permissions.administrator:
                    await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
                gdata = self.get_guild_data(interaction.guild.id)
                gdata["badwords_enabled"] = state == "on"
                save_data(self.guild_data)
                await interaction.followup.send(f"✅ Csúnya beszéd szűrés: {'BE' if gdata['badwords_enabled'] else 'KI'}", ephemeral=True)
            except: pass

        @self.tree.command(name="togglespam", description="Spam szűrés ki/be")
        @app_commands.choices(state=[app_commands.Choice(name="Be", value="on"), app_commands.Choice(name="Ki", value="off")])
        async def togglespam(interaction: discord.Interaction, state: str):
            try:
                await interaction.response.defer(ephemeral=True)
                if not interaction.user.guild_permissions.administrator:
                    await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
                gdata = self.get_guild_data(interaction.guild.id)
                gdata["spam_enabled"] = state == "on"
                save_data(self.guild_data)
                await interaction.followup.send(f"✅ Spam szűrés: {'BE' if gdata['spam_enabled'] else 'KI'}", ephemeral=True)
            except: pass

        @self.tree.command(name="addbadword", description="Csúnya szó hozzáadása a szűrőhöz")
        @app_commands.describe(word="Szó vagy regex pl: kurva vagy \\bkurva\\b", level="Durva vagy enyhe szűrés")
        @app_commands.choices(level=[app_commands.Choice(name="Durva (hard)", value="hard"), app_commands.Choice(name="Enyhe (soft)", value="soft")])
        async def addbadword(interaction: discord.Interaction, word: str, level: str = "hard"):
            try:
                await interaction.response.defer(ephemeral=True)
                if not interaction.user.guild_permissions.administrator:
                    await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
                gdata = self.get_guild_data(interaction.guild.id)
                key = "badwords_hard" if level == "hard" else "badwords_soft"
                if word not in gdata[key]:
                    gdata[key].append(word)
                    save_data(self.guild_data)
                    await interaction.followup.send(f"✅ Hozzáadva {level} listához: `{word}`", ephemeral=True)
                else:
                    await interaction.followup.send(f"⚠ Már benne van: `{word}`", ephemeral=True)
            except Exception as e:
                print(traceback.format_exc())
                await interaction.followup.send(f"❌ {e}", ephemeral=True)

        @self.tree.command(name="removebadword", description="Csúnya szó törlése")
        @app_commands.describe(word="Pontosan ahogy hozzáadtad")
        async def removebadword(interaction: discord.Interaction, word: str):
            try:
                await interaction.response.defer(ephemeral=True)
                if not interaction.user.guild_permissions.administrator:
                    await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
                gdata = self.get_guild_data(interaction.guild.id)
                removed = False
                for key in ["badwords_hard", "badwords_soft"]:
                    if word in gdata[key]:
                        gdata[key].remove(word)
                        removed = True
                if removed:
                    save_data(self.guild_data)
                    await interaction.followup.send(f"✅ Törölve: `{word}`", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Nincs ilyen: `{word}`", ephemeral=True)
            except Exception as e:
                print(traceback.format_exc())

        @self.tree.command(name="listbadwords", description="Csúnya szavak listája")
        async def listbadwords(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
                gdata = self.get_guild_data(interaction.guild.id)
                hard = "\n".join([f"- `{w}`" for w in gdata.get("badwords_hard", [])]) or "Nincs"
                soft = "\n".join([f"- `{w}`" for w in gdata.get("badwords_soft", [])]) or "Nincs"
                embed = discord.Embed(title=f"🤬 Badwords - {interaction.guild.name}", color=discord.Color.orange())
                embed.add_field(name="Durva (hard)", value=hard[:1000], inline=False)
                embed.add_field(name="Enyhe (soft)", value=soft[:1000], inline=False)
                embed.add_field(name="Státusz", value=f"{'BE' if gdata.get('badwords_enabled') else 'KI'} | Threshold: {gdata.get('threshold')}", inline=False)
                await interaction.followup.send(embed=embed, ephemeral=True)
            except Exception as e:
                print(traceback.format_exc())

        @self.tree.command(name="addnsfwlink", description="NSFW link minta hozzáadása")
        @app_commands.describe(pattern="Regex vagy szó pl: pornhub.com vagy \\bonlyfans\\b")
        async def addnsfwlink(interaction: discord.Interaction, pattern: str):
            try:
                await interaction.response.defer(ephemeral=True)
                if not interaction.user.guild_permissions.administrator:
                    await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
                gdata = self.get_guild_data(interaction.guild.id)
                if pattern not in gdata["nsfw_patterns"]:
                    gdata["nsfw_patterns"].append(pattern)
                    save_data(self.guild_data)
                    await interaction.followup.send(f"✅ NSFW minta hozzáadva: `{pattern}`", ephemeral=True)
                else:
                    await interaction.followup.send(f"⚠ Már van: `{pattern}`", ephemeral=True)
            except Exception as e:
                print(traceback.format_exc())

        @self.tree.command(name="removensfwlink", description="NSFW minta törlése")
        @app_commands.describe(pattern="Pontosan ahogy hozzáadtad")
        async def removensfwlink(interaction: discord.Interaction, pattern: str):
            try:
                await interaction.response.defer(ephemeral=True)
                if not interaction.user.guild_permissions.administrator:
                    await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
                gdata = self.get_guild_data(interaction.guild.id)
                if pattern in gdata["nsfw_patterns"]:
                    gdata["nsfw_patterns"].remove(pattern)
                    save_data(self.guild_data)
                    await interaction.followup.send(f"✅ Törölve: `{pattern}`", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Nincs ilyen: `{pattern}`", ephemeral=True)
            except: pass

        @self.tree.command(name="listnsfwlinks", description="NSFW minták listája")
        async def listnsfwlinks(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
                gdata = self.get_guild_data(interaction.guild.id)
                lst = "\n".join([f"- `{p}`" for p in gdata.get("nsfw_patterns", [])]) or "Nincs"
                embed = discord.Embed(title=f"🔞 NSFW minták - {interaction.guild.name}", color=discord.Color.red())
                embed.description = lst[:4000]
                embed.add_field(name="Státusz", value=f"{'BE' if gdata.get('nsfw_enabled') else 'KI'}")
                await interaction.followup.send(embed=embed, ephemeral=True)
            except: pass

        @self.tree.command(name="kamilaconfig", description="Kamila összes beállítása")
        async def kamilaconfig(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
                gdata = self.get_guild_data(interaction.guild.id)
                embed = discord.Embed(title=f"🛡 Kamila Config - {interaction.guild.name}", color=discord.Color.purple())
                def ch_mention(cid):
                    if not cid: return "Nincs"
                    ch = interaction.guild.get_channel(cid)
                    return ch.mention if ch else f"ID:{cid}"
                embed.add_field(name="Log csatorna", value=ch_mention(gdata.get("admin_channel")), inline=False)
                embed.add_field(name="Threshold", value=f"{gdata.get('threshold')} warn után kick", inline=True)
                embed.add_field(name="NSFW", value=f"{'BE' if gdata.get('nsfw_enabled') else 'KI'} | {len(gdata.get('nsfw_patterns', []))} minta", inline=True)
                embed.add_field(name="Badwords", value=f"{'BE' if gdata.get('badwords_enabled') else 'KI'} | {len(gdata.get('badwords_hard', []))} hard + {len(gdata.get('badwords_soft', []))} soft", inline=True)
                embed.add_field(name="Spam", value=f"{'BE' if gdata.get('spam_enabled') else 'KI'}", inline=True)
                embed.add_field(name="Figyelt userek", value=str(len(gdata.get("warnings", {}))), inline=True)
                embed.add_field(name="Kickelt/Bannolt", value=f"{len(gdata.get('kicked', set()))} / {len(gdata.get('banned', set()))}", inline=True)
                await interaction.followup.send(embed=embed, ephemeral=True)
            except Exception as e:
                print(traceback.format_exc())

        @self.tree.command(name="ping", description="Teszt")
        async def ping(interaction: discord.Interaction):
            await interaction.response.send_message("🛡 Kamila Pong! Custom filters működik! ✅", ephemeral=True)

        @self.tree.command(name="sync", description="Sync (tulaj only)")
        async def sync(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
                if interaction.user.id != 1047920915641548921:
                    await interaction.followup.send("❌ Csak a tulaj!", ephemeral=True); return
                synced = await self.tree.sync()
                for guild in self.guilds:
                    try: await self.tree.sync(guild=guild)
                    except: pass
                await interaction.followup.send(f"✅ {len(synced)} parancs syncelve!", ephemeral=True)
            except Exception as e:
                print(traceback.format_exc())

        try:
            synced = await self.tree.sync()
            print(f"✅ Kamila Global sync: {len(synced)} -> {', '.join([c.name for c in synced])}")
        except Exception as e:
            print(f"❌ Sync hiba: {e}\n{traceback.format_exc()}")

    async def on_ready(self):
        print(f"🤖 {self.user.name} | {len(self.guilds)} szerveren - CUSTOM FULL")
        for guild in self.guilds:
            try:
                await self.tree.sync(guild=guild)
                print(f"✅ Guild sync {guild.name}")
            except Exception as e:
                print(f"❌ Guild {guild.name} hiba: {e}")

    async def on_message(self, message):
        if message.author == self.user or message.author.bot: return
        if not message.guild: return
        # adminok és modok kihagyva
        if message.author.guild_permissions.administrator or message.author.guild_permissions.manage_messages:
            return

        violations = await self.check_rule_violations(message, message.guild.id)
        if violations:
            await self.handle_violation(message, violations)

if __name__ == "__main__":
    bot = Kamila()
    token = os.getenv("DISCORD_TOKEN")
    bot.run(token)
