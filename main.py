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
    return "Kamila AUTO ROLE + TIMEOUT - Full Custom"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host='0.0.0.0', port=port)

threading.Thread(target=run_web, daemon=True).start()

DATA_FILE = "kamila_data.json"

DEFAULT_NSFW = [r'\b(pornhub|onlyfans|xvideos|xnxx)\.com\b', r'discord\.gg/.*nsfw', r'onlyfans\.com/']
DEFAULT_BAD_HARD = [r'\bkurva\b', r'baszd meg', r'\bkurva anyád\b', r'\bbuzi\b', r'\bgeci\b']
DEFAULT_BAD_SOFT = [r'\bhülye\b', r'\bidi[oó]ta?\b', r'\bfasz\b']

def parse_duration(duration_str: str):
    """10m, 1h, 2d, 30s -> timedelta"""
    duration_str = duration_str.lower().strip()
    try:
        if duration_str.endswith('s'):
            return datetime.timedelta(seconds=int(duration_str[:-1]))
        elif duration_str.endswith('m'):
            return datetime.timedelta(minutes=int(duration_str[:-1]))
        elif duration_str.endswith('h'):
            return datetime.timedelta(hours=int(duration_str[:-1]))
        elif duration_str.endswith('d'):
            return datetime.timedelta(days=int(duration_str[:-1]))
        else:
            # csak szám = perc
            return datetime.timedelta(minutes=int(duration_str))
    except:
        return None

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                for gid in raw:
                    raw[gid]["kicked"] = set(raw[gid].get("kicked", []))
                    raw[gid]["banned"] = set(raw[gid].get("banned", []))
                    raw[gid]["warnings"] = raw[gid].get("warnings", {})
                    if "threshold" not in raw[gid]: raw[gid]["threshold"] = 3
                    if "nsfw_enabled" not in raw[gid]: raw[gid]["nsfw_enabled"] = True
                    if "badwords_enabled" not in raw[gid]: raw[gid]["badwords_enabled"] = True
                    if "spam_enabled" not in raw[gid]: raw[gid]["spam_enabled"] = True
                    if "nsfw_patterns" not in raw[gid]: raw[gid]["nsfw_patterns"] = DEFAULT_NSFW.copy()
                    if "badwords_hard" not in raw[gid]: raw[gid]["badwords_hard"] = DEFAULT_BAD_HARD.copy()
                    if "badwords_soft" not in raw[gid]: raw[gid]["badwords_soft"] = DEFAULT_BAD_SOFT.copy()
                    if "admin_channel" not in raw[gid]: raw[gid]["admin_channel"] = None
                    if "auto_role_enabled" not in raw[gid]: raw[gid]["auto_role_enabled"] = False
                    if "auto_role_id" not in raw[gid]: raw[gid]["auto_role_id"] = None
                    if "auto_role_name" not in raw[gid]: raw[gid]["auto_role_name"] = None
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
                "auto_role_enabled": data.get("auto_role_enabled", False),
                "auto_role_id": data.get("auto_role_id"),
                "auto_role_name": data.get("auto_role_name"),
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
                "nsfw_enabled": True, "badwords_enabled": True, "spam_enabled": True,
                "nsfw_patterns": DEFAULT_NSFW.copy(),
                "badwords_hard": DEFAULT_BAD_HARD.copy(),
                "badwords_soft": DEFAULT_BAD_SOFT.copy(),
                "auto_role_enabled": False,
                "auto_role_id": None,
                "auto_role_name": None,
            }
        g = self.guild_data[gid]
        # ensure defaults
        defaults = {
            "threshold": 3, "nsfw_enabled": True, "badwords_enabled": True, "spam_enabled": True,
            "auto_role_enabled": False, "auto_role_id": None, "auto_role_name": None,
            "banned": set(), "kicked": set(), "warnings": {}, "admin_channel": None,
            "nsfw_patterns": DEFAULT_NSFW.copy(), "badwords_hard": DEFAULT_BAD_HARD.copy(), "badwords_soft": DEFAULT_BAD_SOFT.copy()
        }
        for k, v in defaults.items():
            if k not in g:
                g[k] = v if not isinstance(v, set) else set()
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
                        violations.append(f"NSFW: {p}")
                        break
                except: pass
        if gdata.get("badwords_enabled"):
            for p in gdata.get("badwords_hard", []):
                try:
                    if re.search(p, content, re.I):
                        violations.append(f"Durva: {p}")
                        break
                except: pass
            if not violations:
                for p in gdata.get("badwords_soft", []):
                    try:
                        if re.search(p, content, re.I):
                            violations.append(f"Enyhe: {p}")
                            break
                    except: pass
        if gdata.get("spam_enabled"):
            if len(content) > 800 or content.count('http') > 4:
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
                await message.channel.send(f"⚠ {message.author.mention} **{gdata['warnings'][uid]}/{threshold}** Ok: {violations[0]}", delete_after=10)
            except: pass
            await self.log_to_admin(message.guild, f"⚠ {message.author.name} warn {gdata['warnings'][uid]}/{threshold} | {violations}")
        else:
            gdata["kicked"].add(uid)
            save_data(self.guild_data)
            try:
                await message.author.kick(reason=f"Kamila: {threshold} warn - {violations}")
                await message.channel.send(f"👢 {message.author.mention} kickelve! {threshold} warn.", delete_after=10)
                await self.log_to_admin(message.guild, f"👢 KICK {message.author.name} | {threshold}/{threshold}")
            except Exception as e:
                await self.log_to_admin(message.guild, f"❌ Kick hiba {message.author.name}: {e}")

    async def setup_hook(self):
        print("🔧 Kamila AUTO ROLE + TIMEOUT setup...")

        @self.tree.command(name="warnings", description="Figyelmeztetések")
        @app_commands.describe(member="Kinek nézzük")
        async def warnings(interaction: discord.Interaction, member: discord.Member = None):
            await interaction.response.defer(ephemeral=True)
            gdata = self.get_guild_data(interaction.guild.id)
            target = member or interaction.user
            cnt = gdata["warnings"].get(str(target.id), 0)
            threshold = gdata.get("threshold", 3)
            await interaction.followup.send(f"**{target.name}: {cnt}/{threshold}**", ephemeral=True)

        @self.tree.command(name="clearwarnings", description="Warnok törlése")
        @app_commands.describe(member="Kinek")
        async def clearwarnings(interaction: discord.Interaction, member: discord.Member):
            await interaction.response.defer()
            if not interaction.user.guild_permissions.kick_members and not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            gdata = self.get_guild_data(interaction.guild.id)
            gdata["warnings"][str(member.id)] = 0
            gdata["kicked"].discard(str(member.id))
            save_data(self.guild_data)
            await interaction.followup.send(f"✅ {member.name} warnjai törölve")

        @self.tree.command(name="setlog", description="Log csatorna")
        @app_commands.describe(channel="Csatorna")
        async def setlog(interaction: discord.Interaction, channel: discord.TextChannel):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            gdata = self.get_guild_data(interaction.guild.id)
            gdata["admin_channel"] = channel.id
            save_data(self.guild_data)
            await interaction.followup.send(f"✅ Log: {channel.mention} | {interaction.guild.name}", ephemeral=True)

        @self.tree.command(name="setthreshold", description="Hány warn után kick")
        @app_commands.describe(count="1-20")
        async def setthreshold(interaction: discord.Interaction, count: int):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            if count < 1 or count > 20:
                await interaction.followup.send("❌ 1-20 között!", ephemeral=True); return
            gdata = self.get_guild_data(interaction.guild.id)
            gdata["threshold"] = count
            save_data(self.guild_data)
            await interaction.followup.send(f"✅ Threshold: **{count}** warn után kick | {interaction.guild.name}", ephemeral=True)

        # AUTO ROLE - ÚJ
        @self.tree.command(name="setautorole", description="Auto rang beállítása belépésnél (rang név vagy role)")
        @app_commands.describe(role="Melyik rangot adja automatikusan belépésnél")
        async def setautorole(interaction: discord.Interaction, role: discord.Role):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            # Bot magasabb legyen mint a rang
            if role >= interaction.guild.me.top_role:
                await interaction.followup.send(f"❌ A bot rangja alacsonyabb mint {role.name}! Húzd feljebb a bot rangját!", ephemeral=True)
                return
            gdata = self.get_guild_data(interaction.guild.id)
            gdata["auto_role_id"] = role.id
            gdata["auto_role_name"] = role.name
            gdata["auto_role_enabled"] = True
            save_data(self.guild_data)
            await interaction.followup.send(f"✅ Auto rang beállítva: **{role.name}** | BE kapcsolva | {interaction.guild.name}\nMostantól minden új tag megkapja!", ephemeral=True)

        @self.tree.command(name="toggleautorole", description="Auto rang ki/be kapcsolása")
        @app_commands.choices(state=[app_commands.Choice(name="Be", value="on"), app_commands.Choice(name="Ki", value="off")])
        async def toggleautorole(interaction: discord.Interaction, state: str):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            gdata = self.get_guild_data(interaction.guild.id)
            gdata["auto_role_enabled"] = state == "on"
            save_data(self.guild_data)
            role_name = gdata.get("auto_role_name") or "Nincs beállítva"
            await interaction.followup.send(f"✅ Auto rang: {'BE' if gdata['auto_role_enabled'] else 'KI'} | Rang: {role_name}", ephemeral=True)

        @self.tree.command(name="removeautorole", description="Auto rang törlése")
        async def removeautorole(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            gdata = self.get_guild_data(interaction.guild.id)
            gdata["auto_role_id"] = None
            gdata["auto_role_name"] = None
            gdata["auto_role_enabled"] = False
            save_data(self.guild_data)
            await interaction.followup.send(f"✅ Auto rang törölve | {interaction.guild.name}", ephemeral=True)

        # TIMEOUT / UNTIMEOUT - ÚJ
        @self.tree.command(name="timeout", description="Tag timeoutolása (némítás)")
        @app_commands.describe(member="Kit timeoutoljon", duration="Mennyi időre pl: 10m, 1h, 1d, 10s", reason="Indok")
        async def timeout(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "Nincs indok"):
            await interaction.response.defer()
            if not interaction.user.guild_permissions.moderate_members:
                await interaction.followup.send("❌ Nincs jogod timeoutolni! (Moderate Members kell)", ephemeral=True); return
            if member.guild_permissions.administrator:
                await interaction.followup.send("❌ Admin-t nem lehet timeoutolni!", ephemeral=True); return
            if member.top_role >= interaction.guild.me.top_role:
                await interaction.followup.send("❌ A bot rangja alacsonyabb!", ephemeral=True); return
            
            delta = parse_duration(duration)
            if not delta:
                await interaction.followup.send("❌ Rossz idő formátum! Használd: `10m`, `1h`, `1d`, `30s` vagy szám percben", ephemeral=True); return
            if delta.total_seconds() < 60 or delta.total_seconds() > 2419200: # 28 nap max
                await interaction.followup.send("❌ 1 perc és 28 nap között legyen!", ephemeral=True); return
            
            try:
                until = discord.utils.utcnow() + delta
                await member.timeout(until, reason=f"{interaction.user.name}: {reason}")
                await interaction.followup.send(f"⏰ {member.mention} timeoutolva **{duration}**-re! Indok: {reason}")
                await self.log_to_admin(interaction.guild, f"⏰ TIMEOUT {member.name} | {duration} | Indok: {reason} | Által: {interaction.user.name}")
            except Exception as e:
                await interaction.followup.send(f"❌ Timeout hiba: {e}", ephemeral=True)

        @self.tree.command(name="untimeout", description="Timeout feloldása")
        @app_commands.describe(member="Kinek oldja fel", reason="Indok")
        async def untimeout(interaction: discord.Interaction, member: discord.Member, reason: str = "Feloldva"):
            await interaction.response.defer()
            if not interaction.user.guild_permissions.moderate_members:
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            try:
                await member.timeout(None, reason=f"{interaction.user.name}: {reason}")
                await interaction.followup.send(f"✅ {member.mention} timeout feloldva! Indok: {reason}")
                await self.log_to_admin(interaction.guild, f"✅ UNTIMEOUT {member.name} | Által: {interaction.user.name} | {reason}")
            except Exception as e:
                await interaction.followup.send(f"❌ Hiba: {e}", ephemeral=True)

        @self.tree.command(name="kick", description="Tag kickelése")
        @app_commands.describe(member="Kit", reason="Indok")
        async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Nincs indok"):
            await interaction.response.defer()
            if not interaction.user.guild_permissions.kick_members:
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            if member.guild_permissions.administrator:
                await interaction.followup.send("❌ Admin-t nem!", ephemeral=True); return
            try:
                await member.kick(reason=f"{interaction.user.name}: {reason}")
                gdata = self.get_guild_data(interaction.guild.id)
                gdata["kicked"].add(str(member.id))
                save_data(self.guild_data)
                await interaction.followup.send(f"👢 {member.name} kickelve! {reason}")
                await self.log_to_admin(interaction.guild, f"👢 KICK {member.name} | {reason} | {interaction.user.name}")
            except Exception as e:
                await interaction.followup.send(f"❌ {e}", ephemeral=True)

        @self.tree.command(name="ban", description="Tag bannolása")
        @app_commands.describe(member="Kit", reason="Indok", delete_days="Üzenetek törlése 0-7 nap")
        async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Nincs indok", delete_days: int = 0):
            await interaction.response.defer()
            if not interaction.user.guild_permissions.ban_members:
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            if member.guild_permissions.administrator:
                await interaction.followup.send("❌ Admin-t nem!", ephemeral=True); return
            try:
                await member.ban(reason=f"{interaction.user.name}: {reason}", delete_message_days=max(0, min(7, delete_days)))
                gdata = self.get_guild_data(interaction.guild.id)
                gdata["banned"].add(str(member.id))
                save_data(self.guild_data)
                await interaction.followup.send(f"🔨 {member.name} bannolva! {reason}")
                await self.log_to_admin(interaction.guild, f"🔨 BAN {member.name} | {reason} | {interaction.user.name}")
            except Exception as e:
                await interaction.followup.send(f"❌ {e}", ephemeral=True)

        @self.tree.command(name="unban", description="Unban ID alapján")
        @app_commands.describe(user_id="User ID", reason="Indok")
        async def unban(interaction: discord.Interaction, user_id: str, reason: str = "Unban"):
            await interaction.response.defer()
            if not interaction.user.guild_permissions.ban_members:
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            try:
                user = await self.fetch_user(int(user_id))
                await interaction.guild.unban(user, reason=f"{interaction.user.name}: {reason}")
                gdata = self.get_guild_data(interaction.guild.id)
                gdata["banned"].discard(str(user_id))
                save_data(self.guild_data)
                await interaction.followup.send(f"✅ {user.name} unbannolva!")
            except Exception as e:
                await interaction.followup.send(f"❌ {e}", ephemeral=True)

        @self.tree.command(name="togglenfsfw", description="NSFW szűrés ki/be")
        @app_commands.choices(state=[app_commands.Choice(name="Be", value="on"), app_commands.Choice(name="Ki", value="off")])
        async def togglenfsfw(interaction: discord.Interaction, state: str):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator: return
            gdata = self.get_guild_data(interaction.guild.id)
            gdata["nsfw_enabled"] = state == "on"
            save_data(self.guild_data)
            await interaction.followup.send(f"✅ NSFW: {'BE' if gdata['nsfw_enabled'] else 'KI'}", ephemeral=True)

        @self.tree.command(name="togglebadwords", description="Csúnya beszéd ki/be")
        @app_commands.choices(state=[app_commands.Choice(name="Be", value="on"), app_commands.Choice(name="Ki", value="off")])
        async def togglebadwords(interaction: discord.Interaction, state: str):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator: return
            gdata = self.get_guild_data(interaction.guild.id)
            gdata["badwords_enabled"] = state == "on"
            save_data(self.guild_data)
            await interaction.followup.send(f"✅ Badwords: {'BE' if gdata['badwords_enabled'] else 'KI'}", ephemeral=True)

        @self.tree.command(name="togglespam", description="Spam ki/be")
        @app_commands.choices(state=[app_commands.Choice(name="Be", value="on"), app_commands.Choice(name="Ki", value="off")])
        async def togglespam(interaction: discord.Interaction, state: str):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator: return
            gdata = self.get_guild_data(interaction.guild.id)
            gdata["spam_enabled"] = state == "on"
            save_data(self.guild_data)
            await interaction.followup.send(f"✅ Spam: {'BE' if gdata['spam_enabled'] else 'KI'}", ephemeral=True)

        @self.tree.command(name="addbadword", description="Csúnya szó hozzáadása")
        @app_commands.describe(word="Szó vagy regex", level="Durva vagy enyhe")
        @app_commands.choices(level=[app_commands.Choice(name="Durva", value="hard"), app_commands.Choice(name="Enyhe", value="soft")])
        async def addbadword(interaction: discord.Interaction, word: str, level: str = "hard"):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator: return
            gdata = self.get_guild_data(interaction.guild.id)
            key = "badwords_hard" if level == "hard" else "badwords_soft"
            if word not in gdata[key]:
                gdata[key].append(word)
                save_data(self.guild_data)
                await interaction.followup.send(f"✅ Hozzáadva {level}: `{word}`", ephemeral=True)
            else:
                await interaction.followup.send(f"⚠ Már benne van", ephemeral=True)

        @self.tree.command(name="removebadword", description="Csúnya szó törlése")
        @app_commands.describe(word="Pontosan ahogy hozzáadtad")
        async def removebadword(interaction: discord.Interaction, word: str):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator: return
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
                await interaction.followup.send(f"❌ Nincs ilyen", ephemeral=True)

        @self.tree.command(name="listbadwords", description="Badwords lista")
        async def listbadwords(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            gdata = self.get_guild_data(interaction.guild.id)
            hard = "\n".join([f"- `{w}`" for w in gdata.get("badwords_hard", [])]) or "Nincs"
            soft = "\n".join([f"- `{w}`" for w in gdata.get("badwords_soft", [])]) or "Nincs"
            embed = discord.Embed(title="Badwords", color=discord.Color.orange())
            embed.add_field(name="Hard", value=hard[:1000], inline=False)
            embed.add_field(name="Soft", value=soft[:1000], inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

        @self.tree.command(name="addnsfwlink", description="NSFW minta hozzáadása")
        @app_commands.describe(pattern="Regex")
        async def addnsfwlink(interaction: discord.Interaction, pattern: str):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator: return
            gdata = self.get_guild_data(interaction.guild.id)
            if pattern not in gdata["nsfw_patterns"]:
                gdata["nsfw_patterns"].append(pattern)
                save_data(self.guild_data)
                await interaction.followup.send(f"✅ NSFW hozzáadva: `{pattern}`", ephemeral=True)
            else:
                await interaction.followup.send(f"⚠ Már van", ephemeral=True)

        @self.tree.command(name="removensfwlink", description="NSFW minta törlése")
        @app_commands.describe(pattern="Pontosan")
        async def removensfwlink(interaction: discord.Interaction, pattern: str):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator: return
            gdata = self.get_guild_data(interaction.guild.id)
            if pattern in gdata["nsfw_patterns"]:
                gdata["nsfw_patterns"].remove(pattern)
                save_data(self.guild_data)
                await interaction.followup.send(f"✅ Törölve: `{pattern}`", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Nincs ilyen", ephemeral=True)

        @self.tree.command(name="listnsfwlinks", description="NSFW lista")
        async def listnsfwlinks(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            gdata = self.get_guild_data(interaction.guild.id)
            lst = "\n".join([f"- `{p}`" for p in gdata.get("nsfw_patterns", [])]) or "Nincs"
            embed = discord.Embed(title="NSFW minták", color=discord.Color.red())
            embed.description = lst[:4000]
            await interaction.followup.send(embed=embed, ephemeral=True)

        @self.tree.command(name="kamilaconfig", description="Kamila config")
        async def kamilaconfig(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            gdata = self.get_guild_data(interaction.guild.id)
            def ch_mention(cid):
                if not cid: return "Nincs"
                ch = interaction.guild.get_channel(cid)
                return ch.mention if ch else f"ID:{cid}"
            def role_mention(rid):
                if not rid: return "Nincs"
                r = interaction.guild.get_role(rid)
                return r.mention if r else f"ID:{rid}"
            embed = discord.Embed(title=f"🛡 Kamila Config - {interaction.guild.name}", color=discord.Color.purple())
            embed.add_field(name="Log", value=ch_mention(gdata.get("admin_channel")), inline=True)
            embed.add_field(name="Threshold", value=f"{gdata.get('threshold')} warn", inline=True)
            embed.add_field(name="Auto Role", value=f"{role_mention(gdata.get('auto_role_id'))} | {'BE' if gdata.get('auto_role_enabled') else 'KI'}", inline=False)
            embed.add_field(name="NSFW", value=f"{'BE' if gdata.get('nsfw_enabled') else 'KI'} | {len(gdata.get('nsfw_patterns', []))} minta", inline=True)
            embed.add_field(name="Badwords", value=f"{'BE' if gdata.get('badwords_enabled') else 'KI'} | {len(gdata.get('badwords_hard', []))}h+{len(gdata.get('badwords_soft', []))}s", inline=True)
            embed.add_field(name="Spam", value=f"{'BE' if gdata.get('spam_enabled') else 'KI'}", inline=True)
            embed.add_field(name="Warnok", value=f"{len(gdata.get('warnings', {}))} user", inline=True)
            embed.add_field(name="Kick/Ban", value=f"{len(gdata.get('kicked', set()))}/{len(gdata.get('banned', set()))}", inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

        @self.tree.command(name="ping", description="Teszt")
        async def ping(interaction: discord.Interaction):
            await interaction.response.send_message("🛡 Kamila Pong! Auto role + timeout OK ✅", ephemeral=True)

        @self.tree.command(name="sync", description="Sync tulaj only")
        async def sync(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            if interaction.user.id != 1047920915641548921:
                await interaction.followup.send("❌ Csak a tulaj!", ephemeral=True); return
            synced = await self.tree.sync()
            for g in self.guilds:
                try: await self.tree.sync(guild=g)
                except: pass
            await interaction.followup.send(f"✅ {len(synced)} syncelve!", ephemeral=True)

        try:
            synced = await self.tree.sync()
            print(f"✅ Global sync: {len(synced)} -> {', '.join([c.name for c in synced])}")
        except Exception as e:
            print(f"❌ Sync hiba: {e}\n{traceback.format_exc()}")

    async def on_ready(self):
        print(f"🤖 {self.user.name} | {len(self.guilds)} szerveren - AUTO ROLE + TIMEOUT")
        for guild in self.guilds:
            try:
                await self.tree.sync(guild=guild)
                print(f"✅ Guild sync {guild.name}")
            except: pass

    async def on_member_join(self, member):
        # Auto role
        gdata = self.get_guild_data(member.guild.id)
        if gdata.get("auto_role_enabled") and gdata.get("auto_role_id"):
            try:
                role = member.guild.get_role(gdata["auto_role_id"])
                if not role and gdata.get("auto_role_name"):
                    # név alapján keresés
                    role = discord.utils.get(member.guild.roles, name=gdata["auto_role_name"])
                if role:
                    if role < member.guild.me.top_role:
                        await member.add_roles(role, reason="Kamila auto role")
                        print(f"✅ Auto role {role.name} adva: {member.name} ({member.guild.name})")
                        await self.log_to_admin(member.guild, f"✨ Auto role {role.name} -> {member.name}")
                    else:
                        print(f"❌ Auto role hiba: bot rang alacsonyabb mint {role.name}")
            except Exception as e:
                print(f"Auto role hiba: {e}")

    async def on_message(self, message):
        if message.author == self.user or message.author.bot: return
        if not message.guild: return
        if message.author.guild_permissions.administrator or message.author.guild_permissions.manage_messages:
            return
        violations = await self.check_rule_violations(message, message.guild.id)
        if violations:
            await self.handle_violation(message, violations)

if __name__ == "__main__":
    bot = Kamila()
    token = os.getenv("DISCORD_TOKEN")
    bot.run(token)
