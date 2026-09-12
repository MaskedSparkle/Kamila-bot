import discord
from discord import app_commands
from discord.ext import commands
import os, json, traceback, re, asyncio, threading, datetime
from flask import Flask

app_web = Flask(__name__)
@app_web.route('/')
def home():
    return "Kamila FINAL - AutoRole Timeout + Discord Bridge"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host='0.0.0.0', port=port)
threading.Thread(target=run_web, daemon=True).start()

DATA_FILE = "kamila_data.json"
DEFAULT_NSFW = [r'\b(pornhub|onlyfans|xvideos|xnxx)\.com\b', r'discord\.gg/.*nsfw']
DEFAULT_BAD_HARD = [r'\bkurva\b', r'baszd meg', r'\bkurva anyád\b', r'\bbuzi\b', r'\bgeci\b']
DEFAULT_BAD_SOFT = [r'\bhülye\b', r'\bidi[oó]ta?\b', r'\bfasz\b']

def parse_duration(s):
    s=s.lower().strip()
    try:
        if s.endswith('s'): return datetime.timedelta(seconds=int(s[:-1]))
        if s.endswith('m'): return datetime.timedelta(minutes=int(s[:-1]))
        if s.endswith('h'): return datetime.timedelta(hours=int(s[:-1]))
        if s.endswith('d'): return datetime.timedelta(days=int(s[:-1]))
        return datetime.timedelta(minutes=int(s))
    except: return None

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

    def get_guild_data(self, gid):
        gid=str(gid)
        if gid not in self.guild_data:
            self.guild_data[gid] = {
                "warnings": {}, "kicked": set(), "banned": set(),
                "admin_channel": None, "threshold": 3,
                "nsfw_enabled": True, "badwords_enabled": True, "spam_enabled": True,
                "nsfw_patterns": DEFAULT_NSFW.copy(),
                "badwords_hard": DEFAULT_BAD_HARD.copy(),
                "badwords_soft": DEFAULT_BAD_SOFT.copy(),
                "auto_role_enabled": False, "auto_role_id": None, "auto_role_name": None,
            }
        g=self.guild_data[gid]
        defaults = {
            "threshold": 3, "nsfw_enabled": True, "badwords_enabled": True, "spam_enabled": True,
            "auto_role_enabled": False, "auto_role_id": None, "auto_role_name": None,
            "banned": set(), "kicked": set(), "warnings": {}, "admin_channel": None,
            "nsfw_patterns": DEFAULT_NSFW.copy(), "badwords_hard": DEFAULT_BAD_HARD.copy(), "badwords_soft": DEFAULT_BAD_SOFT.copy()
        }
        for k,v in defaults.items():
            if k not in g:
                g[k]=v if not isinstance(v,set) else set()
        return g

    def get_admin_channel_id(self, guild):
        gdata=self.get_guild_data(guild.id)
        if gdata.get("admin_channel"): return gdata["admin_channel"]
        for ch in guild.text_channels:
            if "log" in ch.name.lower() or "bridge" in ch.name.lower() or "ban" in ch.name.lower():
                return ch.id
        return None

    async def get_bridge_channel(self, guild):
        """Megkeresi a bridge/log csatornát ahol szólni tud Jasmine-nak"""
        # 1. admin_channel
        gdata=self.get_guild_data(guild.id)
        cid=gdata.get("admin_channel")
        if cid:
            ch=guild.get_channel(cid)
            if ch: return ch
        # 2. név alapján
        for name in ["ban-bridge", "bridge", "log", "logs", "kamila-log"]:
            for ch in guild.text_channels:
                if name in ch.name.lower():
                    if ch.permissions_for(guild.me).send_messages:
                        return ch
        # 3. első ahol tud írni
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                return ch
        return None

    async def setup_hook(self):
        print("🔧 Kamila FINAL DISCORD BRIDGE setup...")

        @self.tree.command(name="ban", description="Bannolás - Jasmine fogja DM-elni utolsó pillanatban!")
        @app_commands.describe(member="Kit", reason="Indok", delete_days="Üzenetek törlése 0-7")
        async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Nincs indok", delete_days: int = 0):
            await interaction.response.defer()
            if not interaction.user.guild_permissions.ban_members:
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            if member.guild_permissions.administrator:
                await interaction.followup.send("❌ Admin-t nem!", ephemeral=True); return
            if member.top_role >= interaction.guild.me.top_role:
                await interaction.followup.send("❌ Bot rangja alacsonyabb!", ephemeral=True); return

            # DISCORD BRIDGE - szólunk Jasmine-nak
            bridge_ch = await self.get_bridge_channel(interaction.guild)
            if bridge_ch:
                try:
                    # Titkos jel Jasmine-nak - ezt csak a botok értik
                    await bridge_ch.send(f"BRIDGE_BAN|{interaction.guild.id}|{member.id}|{reason}|{interaction.user.name}")
                    print(f"🌉 DISCORD BRIDGE elküldve: {member.name} -> {bridge_ch.name} | várok 3mp-et hogy Jasmine DM-eljen")
                except Exception as e:
                    print(f"Bridge hiba: {e}")

            await interaction.followup.send(f"⏳ {member.name} bannolása... Jasmine küldi a DM-et az utolsó pillanatban! (3mp) | Indok: {reason}")
            
            # Várunk 3mp-et hogy Jasmine el tudja küldeni a DM-et amíg még a szerveren van!
            await asyncio.sleep(3)

            try:
                await member.ban(reason=f"{interaction.user.name}: {reason}", delete_message_days=max(0,min(7,delete_days)))
                gdata=self.get_guild_data(interaction.guild.id)
                gdata["banned"].add(str(member.id))
                save_data(self.guild_data)
                await interaction.followup.send(f"🔨 {member.name} bannolva! {reason} | Jasmine DM-et küldött előtte! 🌸")
            except Exception as e:
                await interaction.followup.send(f"❌ Ban hiba: {e}", ephemeral=True)

        @self.tree.command(name="kick", description="Kick - Jasmine DM utolsó pillanatban")
        @app_commands.describe(member="Kit", reason="Indok")
        async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Nincs indok"):
            await interaction.response.defer()
            if not interaction.user.guild_permissions.kick_members:
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            bridge_ch = await self.get_bridge_channel(interaction.guild)
            if bridge_ch:
                try:
                    await bridge_ch.send(f"BRIDGE_KICK|{interaction.guild.id}|{member.id}|{reason}|{interaction.user.name}")
                except: pass
            await asyncio.sleep(2)
            try:
                await member.kick(reason=f"{interaction.user.name}: {reason}")
                gdata=self.get_guild_data(interaction.guild.id)
                gdata["kicked"].add(str(member.id))
                save_data(self.guild_data)
                await interaction.followup.send(f"👢 {member.name} kickelve! {reason}")
            except Exception as e:
                await interaction.followup.send(f"❌ {e}", ephemeral=True)

        # TÖBBI PARANCS VÁLTOZATLAN
        @self.tree.command(name="timeout", description="Timeout")
        @app_commands.describe(member="Kit", duration="Idő pl 10m, 1h", reason="Indok")
        async def timeout(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "Nincs indok"):
            await interaction.response.defer()
            if not interaction.user.guild_permissions.moderate_members:
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            delta=parse_duration(duration)
            if not delta:
                await interaction.followup.send("❌ Rossz idő! Pl: 10m, 1h, 1d", ephemeral=True); return
            if delta.total_seconds() < 60 or delta.total_seconds() > 2419200:
                await interaction.followup.send("❌ 1 perc és 28 nap között!", ephemeral=True); return
            try:
                until=discord.utils.utcnow()+delta
                await member.timeout(until, reason=f"{interaction.user.name}: {reason}")
                await interaction.followup.send(f"⏰ {member.mention} timeoutolva **{duration}**-re! {reason}")
            except Exception as e:
                await interaction.followup.send(f"❌ {e}", ephemeral=True)

        @self.tree.command(name="untimeout", description="Untimeout")
        @app_commands.describe(member="Kinek", reason="Indok")
        async def untimeout(interaction: discord.Interaction, member: discord.Member, reason: str = "Feloldva"):
            await interaction.response.defer()
            if not interaction.user.guild_permissions.moderate_members:
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            try:
                await member.timeout(None, reason=f"{interaction.user.name}: {reason}")
                await interaction.followup.send(f"✅ {member.mention} timeout feloldva! {reason}")
            except Exception as e:
                await interaction.followup.send(f"❌ {e}", ephemeral=True)

        @self.tree.command(name="setautorole", description="Auto rang belépésnél")
        @app_commands.describe(role="Melyik rangot adja")
        async def setautorole(interaction: discord.Interaction, role: discord.Role):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            if role >= interaction.guild.me.top_role:
                await interaction.followup.send(f"❌ Bot rangja alacsonyabb mint {role.name}!", ephemeral=True); return
            gdata=self.get_guild_data(interaction.guild.id)
            gdata["auto_role_id"]=role.id
            gdata["auto_role_name"]=role.name
            gdata["auto_role_enabled"]=True
            save_data(self.guild_data)
            await interaction.followup.send(f"✅ Auto rang: **{role.name}** | BE | {interaction.guild.name}", ephemeral=True)

        @self.tree.command(name="toggleautorole", description="Auto rang ki/be")
        @app_commands.choices(state=[app_commands.Choice(name="Be", value="on"), app_commands.Choice(name="Ki", value="off")])
        async def toggleautorole(interaction: discord.Interaction, state: str):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator: return
            gdata=self.get_guild_data(interaction.guild.id)
            gdata["auto_role_enabled"]=state=="on"
            save_data(self.guild_data)
            await interaction.followup.send(f"✅ Auto rang: {'BE' if gdata['auto_role_enabled'] else 'KI'} | {gdata.get('auto_role_name')}", ephemeral=True)

        @self.tree.command(name="setlog", description="Log csatorna (ez lesz a bridge is)")
        @app_commands.describe(channel="Csatorna")
        async def setlog(interaction: discord.Interaction, channel: discord.TextChannel):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator: return
            gdata=self.get_guild_data(interaction.guild.id)
            gdata["admin_channel"]=channel.id
            save_data(self.guild_data)
            await interaction.followup.send(f"✅ Log/Bridge: {channel.mention} | {interaction.guild.name}", ephemeral=True)

        @self.tree.command(name="kamilaconfig", description="Config")
        async def kamilaconfig(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            gdata=self.get_guild_data(interaction.guild.id)
            embed=discord.Embed(title=f"🛡 Kamila FINAL - {interaction.guild.name}", color=discord.Color.purple())
            embed.add_field(name="Auto Role", value=f"{gdata.get('auto_role_name') or 'Nincs'} | {'BE' if gdata.get('auto_role_enabled') else 'KI'}", inline=False)
            embed.add_field(name="Bridge", value="Discord csatornán keresztül szól Jasmine-nak -> Jasmine DM utolsó pillanatban", inline=False)
            embed.add_field(name="BAN DM", value="Csak Jasmine küldi, Kamila nem!", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

        @self.tree.command(name="ping", description="Teszt")
        async def ping(interaction: discord.Interaction):
            await interaction.response.send_message("🛡 Kamila FINAL Pong! Discord Bridge ✅", ephemeral=True)

        @self.tree.command(name="setthreshold", description="Hány warn után kick")
        @app_commands.describe(count="Szám")
        async def setthreshold(interaction: discord.Interaction, count: int):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator: return
            gdata=self.get_guild_data(interaction.guild.id)
            gdata["threshold"]=count
            save_data(self.guild_data)
            await interaction.followup.send(f"✅ Threshold: {count}", ephemeral=True)

        try:
            synced=await self.tree.sync()
            print(f"✅ Global sync: {len(synced)} -> {', '.join([c.name for c in synced])}")
        except Exception as e:
            print(f"❌ Sync hiba: {e}\n{traceback.format_exc()}")

    async def on_ready(self):
        print(f"🤖 Kamila FINAL DISCORD BRIDGE | {len(self.guilds)} szerveren")
        for g in self.guilds:
            try: await self.tree.sync(guild=g)
            except: pass

    async def on_member_join(self, member):
        gdata=self.get_guild_data(member.guild.id)
        if gdata.get("auto_role_enabled") and gdata.get("auto_role_id"):
            try:
                role=member.guild.get_role(gdata["auto_role_id"])
                if not role and gdata.get("auto_role_name"):
                    role=discord.utils.get(member.guild.roles, name=gdata["auto_role_name"])
                if role and role < member.guild.me.top_role:
                    await member.add_roles(role, reason="Kamila auto role")
            except Exception as e:
                print(f"Auto role hiba: {e}")

if __name__=="__main__":
    bot=Kamila()
    bot.run(os.getenv("DISCORD_TOKEN"))
