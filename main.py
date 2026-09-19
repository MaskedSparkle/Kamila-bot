import discord
from discord import app_commands
from discord.ext import commands
import os, json, traceback, re, asyncio, threading, datetime
from flask import Flask

app_web = Flask(__name__)
@app_web.route('/')
def home():
    return "Kamila FINAL - AutoRole + SecurityScan + Discord Bridge"

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
                    # NEW - Security Scan
                    if "security_scan_enabled" not in raw[gid]: raw[gid]["security_scan_enabled"] = True
                    if "security_channel" not in raw[gid]: raw[gid]["security_channel"] = raw[gid].get("admin_channel")
                    if "security_custom_template" not in raw[gid]: raw[gid]["security_custom_template"] = None
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
                
                "security_scan_enabled": data.get("security_scan_enabled", True),
                "security_channel": data.get("security_channel"),
                "security_custom_template": data.get("security_custom_template"),
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
                "security_scan_enabled": True, "security_channel": None, "security_custom_template": None,
            }
        g=self.guild_data[gid]
        defaults = {
            "threshold": 3, "nsfw_enabled": True, "badwords_enabled": True, "spam_enabled": True,
            "auto_role_enabled": False, "auto_role_id": None, "auto_role_name": None,
            "banned": set(), "kicked": set(), "warnings": {}, "admin_channel": None,
            "nsfw_patterns": DEFAULT_NSFW.copy(), "badwords_hard": DEFAULT_BAD_HARD.copy(), "badwords_soft": DEFAULT_BAD_SOFT.copy(),
            "security_scan_enabled": True, "security_channel": None, "security_custom_template": None,
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
        gdata=self.get_guild_data(guild.id)
        cid=gdata.get("admin_channel")
        if cid:
            ch=guild.get_channel(cid)
            if ch: return ch
        for name in ["ban-bridge", "bridge", "log", "logs", "kamila-log"]:
            for ch in guild.text_channels:
                if name in ch.name.lower():
                    if ch.permissions_for(guild.me).send_messages:
                        return ch
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                return ch
        return None

    def get_security_channel(self, guild):
        gdata = self.get_guild_data(guild.id)
        cid = gdata.get("security_channel") or gdata.get("admin_channel")
        if cid:
            ch = guild.get_channel(cid)
            if ch: return ch
        # fallback név alapján
        for name in ["security", "log", "logs", "belépő", "join-log"]:
            for ch in guild.text_channels:
                if name in ch.name.lower():
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
            bridge_ch = await self.get_bridge_channel(interaction.guild)
            if bridge_ch:
                try:
                    await bridge_ch.send(f"BRIDGE_BAN|{interaction.guild.id}|{member.id}|{reason}|{interaction.user.name}")
                    print(f"🌉 DISCORD BRIDGE elküldve: {member.name} -> {bridge_ch.name}")
                except Exception as e:
                    print(f"Bridge hiba: {e}")
            await interaction.followup.send(f"⏳ {member.name} bannolása... Jasmine küldi a DM-et az utolsó pillanatban! (3mp) | Indok: {reason}")
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
            if not interaction.user.guild_permissions.administrator: 
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            gdata=self.get_guild_data(interaction.guild.id)
            gdata["auto_role_enabled"]=state=="on"
            save_data(self.guild_data)
            await interaction.followup.send(f"✅ Auto rang: {'BE' if gdata['auto_role_enabled'] else 'KI'} | {gdata.get('auto_role_name')}", ephemeral=True)

        @self.tree.command(name="setlog", description="Log csatorna (ez lesz a bridge is)")
        @app_commands.describe(channel="Csatorna")
        async def setlog(interaction: discord.Interaction, channel: discord.TextChannel):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator: 
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            gdata=self.get_guild_data(interaction.guild.id)
            gdata["admin_channel"]=channel.id
            if not gdata.get("security_channel"):
                gdata["security_channel"]=channel.id
            save_data(self.guild_data)
            await interaction.followup.send(f"✅ Log/Bridge: {channel.mention} | {interaction.guild.name}", ephemeral=True)

       
        @self.tree.command(name="setsecuritychannel", description="Hova írja a NEW MEMBER SECURITY SCAN-t")
        @app_commands.describe(channel="Csatorna")
        async def setsecuritychannel(interaction: discord.Interaction, channel: discord.TextChannel):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator: 
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            gdata=self.get_guild_data(interaction.guild.id)
            gdata["security_channel"]=channel.id
            save_data(self.guild_data)
            await interaction.followup.send(f"✅ Security Scan csatorna: {channel.mention}", ephemeral=True)

        @self.tree.command(name="togglesecurityscan", description="Security Scan ki/be kapcsoló")
        @app_commands.choices(state=[app_commands.Choice(name="Be", value="on"), app_commands.Choice(name="Ki", value="off")])
        async def togglesecurityscan(interaction: discord.Interaction, state: str):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator: 
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            gdata=self.get_guild_data(interaction.guild.id)
            gdata["security_scan_enabled"]=state=="on"
            save_data(self.guild_data)
            await interaction.followup.send(f"✅ Security Scan: {'BE' if gdata['security_scan_enabled'] else 'KI'}", ephemeral=True)

        @self.tree.command(name="kamilatoggle", description="Bármelyik modul ki/be")
        @app_commands.describe(modul="Mit kapcsolsz", state="Állapot")
        @app_commands.choices(
            modul=[
                app_commands.Choice(name="NSFW szűrő", value="nsfw_enabled"),
                app_commands.Choice(name="Káromkodás szűrő", value="badwords_enabled"),
                app_commands.Choice(name="Spam szűrő", value="spam_enabled"),
                app_commands.Choice(name="Security Scan", value="security_scan_enabled"),
                app_commands.Choice(name="Auto Role", value="auto_role_enabled"),
            ],
            state=[
                app_commands.Choice(name="Be", value="on"),
                app_commands.Choice(name="Ki", value="off"),
            ]
        )
        async def kamilatoggle(interaction: discord.Interaction, modul: str, state: str):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator: 
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            gdata=self.get_guild_data(interaction.guild.id)
            gdata[modul]=state=="on"
            save_data(self.guild_data)
            await interaction.followup.send(f"✅ {modul} -> {'BE' if state=='on' else 'KI'}", ephemeral=True)

        @self.tree.command(name="kamilaconfig", description="Minden beállítás listázása - mi be, mi ki")
        async def kamilaconfig(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            gdata=self.get_guild_data(interaction.guild.id)
            
            embed=discord.Embed(title=f"🛡 Kamila CONFIG - {interaction.guild.name}", color=discord.Color.purple(), timestamp=datetime.datetime.now())
            
           
            auto_role_text = f"{gdata.get('auto_role_name') or 'Nincs beállítva'} | {'🟢 BE' if gdata.get('auto_role_enabled') else '🔴 KI'}"
            
            
            sec_enabled = "🟢 BEKAPCSOLVA" if gdata.get("security_scan_enabled") else "🔴 KIKAPCSOLVA"
            sec_ch_id = gdata.get("security_channel") or gdata.get("admin_channel")
            sec_ch_text = f"<#{sec_ch_id}>" if sec_ch_id else "Nincs beállítva (auto keresés)"
            
            
            def status(val): return "🟢 BE" if val else "🔴 KI"

            embed.add_field(name="👤 Auto Role", value=auto_role_text, inline=False)
            embed.add_field(name="🛡️ Security Scan", value=f"{sec_enabled}\nCsatorna: {sec_ch_text}", inline=False)
            embed.add_field(name="🔞 NSFW Szűrő", value=status(gdata.get("nsfw_enabled")), inline=True)
            embed.add_field(name="🤬 Káromkodás Szűrő", value=status(gdata.get("badwords_enabled")), inline=True)
            embed.add_field(name="🚫 Spam Szűrő", value=status(gdata.get("spam_enabled")), inline=True)
            embed.add_field(name="⚠️ Warn Limit", value=f"{gdata.get('threshold',3)} warn -> kick", inline=True)
            embed.add_field(name="📋 Bridge Log", value=f"<#{gdata.get('admin_channel')}>" if gdata.get('admin_channel') else "Nincs beállítva", inline=True)
            embed.add_field(name="📝 Parancsok", value="`/kamilatoggle` - modul ki/be\n`/setsecuritychannel` - scan csatorna\n`/setautorole` - auto rang\n`/setlog` - log csatorna", inline=False)
            embed.set_footer(text="Kamila FINAL - Custom & Toggle rendszer aktív")

            await interaction.followup.send(embed=embed, ephemeral=True)

        @self.tree.command(name="ping", description="Teszt")
        async def ping(interaction: discord.Interaction):
            await interaction.response.send_message("🛡 Kamila FINAL Pong! SecurityScan + Bridge ✅", ephemeral=True)

        @self.tree.command(name="setthreshold", description="Hány warn után kick")
        @app_commands.describe(count="Szám")
        async def setthreshold(interaction: discord.Interaction, count: int):
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator: 
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
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
        print(f"🤖 Kamila FINAL | {len(self.guilds)} szerveren | SecurityScan kész")
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

        
        if not gdata.get("security_scan_enabled", True):
            return

        sec_channel = self.get_security_channel(member.guild)
        if not sec_channel:
            print("Nincs security csatorna")
            return

        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            account_age = now - member.created_at
            days = account_age.days
            years = days // 365
            months = (days % 365) // 30
            rem_days = (days % 365) % 30

            
            if years > 0:
                age_text = f"{years} év, {months} hónap, {rem_days} nap ({days} nap)"
            elif months > 0:
                age_text = f"{months} hónap, {rem_days} nap ({days} nap)"
            else:
                age_text = f"{days} nap"

            
            if days < 7:
                status_val = "🔴 Gyanús - Nagyon új fiók"
                flag_text = "🚨 Új fiók (<7 nap) - Lehetséges alt / raid"
                color = 0xff0000
            elif days < 30:
                status_val = "🟡 Figyelmeztető - Új fiók"
                flag_text = "⚠️ Nincsenek rangok"
                color = 0xffa500
            else:
                status_val = "🟢 Megbízhatónak tűnő fiók"
                flag_text = "✅ Nincsenek rangok" if len(member.roles) <= 1 else "Nincsenek jelzések"
                color = 0x2b2d31

           
            role_count = len([r for r in member.roles if r.name != "@everyone"])

            
            embed = discord.Embed(
                title="",
                description=f"🚨 **NEW MEMBER SECURITY SCAN**",
                color=color,
                timestamp=now
            )
            
            embed.add_field(name="Felhasználó", value=f"{member.name}\n{member.mention}", inline=False)
            embed.add_field(name="Fiók Kora", value=f"{age_text}", inline=False)
            embed.add_field(name="Státusz Értékelés", value=f"✅ {status_val}" if "Megbízható" in status_val else status_val, inline=False)
            embed.add_field(name="Rangok száma", value=f"{role_count} db", inline=False)
            embed.add_field(name="Biztonsági Jelzések (Flags)", value=f"⚠️ {flag_text}", inline=False)
            embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else member.default_avatar.url)
            embed.set_footer(text=f"{now.strftime('%Y. %m. %d. %H:%M')}")

            
            await sec_channel.send(embed=embed)

        except Exception as e:
            print(f"Security scan hiba: {e}\n{traceback.format_exc()}")

if __name__=="__main__":
    bot=Kamila()
    bot.run(os.getenv("DISCORD_TOKEN"))
