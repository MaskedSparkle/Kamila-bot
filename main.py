import discord
from discord import app_commands
from discord.ext import commands
import datetime
import re
import os
import json
from flask import Flask
import threading

app_web = Flask(__name__)
@app_web.route('/')
def home():
    return "Kamila is alive! 🛡 Safe Mode ON - Multi Server FIXED"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host='0.0.0.0', port=port)

threading.Thread(target=run_web, daemon=True).start()

DATA_FILE = "kamila_data.json"

def get_account_age_string(created_at):
    now = datetime.datetime.now(datetime.timezone.utc)
    delta = now - created_at
    days = delta.days
    years = days // 365
    remaining_days = days % 365
    months = remaining_days // 30
    final_days = remaining_days % 30
    parts = []
    if years > 0:
        parts.append(f"{years} év")
    if months > 0:
        parts.append(f"{months} hónap")
    if final_days > 0 or not parts:
        parts.append(f"{final_days} nap")
    return f"{', '.join(parts)} ({days} nap)"

class Kamila(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.messages = True
        intents.guilds = True
        intents.bans = True 
        super().__init__(command_prefix='!', intents=intents)
        self.WARNING_THRESHOLD = 3 
        self.guild_data = self.load_all_data()
        self.NSFW_PATTERNS = [
            r'\b(pornhub|onlyfans|xvideos|xnxx)\.com\b',
            r'https?://\S*(pornhub|onlyfans|xvideos)\S*',
        ]
        self.BAD_WORDS_HARD = [
            r'\bkurva\b', r'baszd meg', r'\bkurva anyád\b', r'\bkurva apád\b',
            r'\banyád\b', r'\bköcsög\b', r'\bbuzi\b', r'\bbazmeg\b', r'\bribanc\b', r'\bgeci\b',
        ]
        self.BAD_WORDS_SOFT = [
            r'\bhülye\b', r'\bidi[oó]ta?\b', r'\bbarom\b', r'\bparaszt\b', r'\bkussolj\b',
        ]

    def load_all_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    for gid in raw:
                        raw[gid]["kicked"] = set(raw[gid].get("kicked", []))
                        raw[gid]["warnings"] = raw[gid].get("warnings", {})
                        if "admin_channel" not in raw[gid]:
                            raw[gid]["admin_channel"] = None
                    return raw
            except Exception as e:
                print(f"Load error: {e}")
        return {}

    def save_all_data(self):
        try:
            to_save = {}
            for gid, data in self.guild_data.items():
                to_save[gid] = {
                    "warnings": data.get("warnings", {}),
                    "kicked": list(data.get("kicked", set())),
                    "admin_channel": data.get("admin_channel")
                }
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(to_save, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Save error: {e}")

    def get_guild_data(self, guild_id):
        gid = str(guild_id)
        if gid not in self.guild_data:
            self.guild_data[gid] = {"warnings": {}, "kicked": set(), "admin_channel": None}
        return self.guild_data[gid]

    def get_admin_channel_id(self, guild):
        gdata = self.get_guild_data(guild.id)
        if gdata.get("admin_channel"):
            return gdata["admin_channel"]
        for ch in guild.text_channels:
            if ch.name.lower() in ["logs", "log", "admin", "admin-log", "mod-log", "kamila-log"]:
                return ch.id
        return None

    async def setup_hook(self):
        
        self.tree.add_command(self.warnings_cmd)
        self.tree.add_command(self.clearwarnings_cmd)
        self.tree.add_command(self.statuscheck_cmd)
        self.tree.add_command(self.setlogchannel_cmd)
        self.tree.add_command(self.sync_cmd)

        try:
           
            OLD_GUILD = discord.Object(id=1497272521735671810)
            self.tree.clear_commands(guild=OLD_GUILD)
            await self.tree.sync(guild=OLD_GUILD)
            print("🗑️ Régi guild parancsok törölve")
            
            
            synced = await self.tree.sync()
            print(f"✅ Global sync: {len(synced)} parancs minden szerveren! {', '.join([c.name for c in synced])}")
        except Exception as e:
            print(f"❌ Hiba szinkronizáláskor: {e}")

    async def on_ready(self):
        print(f"🤖 {self.user.name} | {len(self.guilds)} szerveren | Safe Mode")

    async def on_message(self, message):
        if message.author == self.user or (hasattr(message.author, 'bot') and message.author.bot):
            return
        if not message.guild:
            return
        if message.author.guild_permissions.administrator or message.author.guild_permissions.manage_messages:
            return
        violation = await self.check_rule_violations(message)
        if violation:
            await self.handle_violation(message, violation)

    async def check_rule_violations(self, message):
        content = message.content
        violations = []
        for pattern in self.NSFW_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                violations.append("NSFW link")
                break
        for pattern in self.BAD_WORDS_HARD:
            if re.search(pattern, content, re.IGNORECASE):
                violations.append(f"Durva szó: {pattern}")
                break
        for pattern in self.BAD_WORDS_SOFT:
            if re.search(pattern, content, re.IGNORECASE):
                violations.append(f"Enyhe: {pattern}")
                break
        if len(content) > 800 or content.count('http') > 4 or len(message.mentions) > 5:
            violations.append("SPAM")
        if content.isupper() and len(content) > 80:
            violations.append("CAPS_LOCK")
        return violations
    
    async def handle_violation(self, message, violations):
        gdata = self.get_guild_data(message.guild.id)
        user_id = str(message.author.id)
        if user_id not in gdata["warnings"]:
            gdata["warnings"][user_id] = 0
        gdata["warnings"][user_id] += 1
        current_warnings = gdata["warnings"][user_id]
        self.save_all_data()
        try:
            await message.delete()
        except:
            pass
        if current_warnings < self.WARNING_THRESHOLD:
            try:
                await message.channel.send(
                    f"**⚠ {message.author.mention}, ez a(z) {current_warnings}. figyelmeztetésed! ({', '.join(violations)}) Ha eléred a {self.WARNING_THRESHOLD}-at, kick!**",
                    delete_after=15
                )
            except:
                pass
            await self.log_to_admin(message.guild, f"⚠ **Figyelmeztetés {message.author.name}** ({current_warnings}/{self.WARNING_THRESHOLD}) - {', '.join(violations)} | `{message.content[:100]}`")
        else:
            gdata["kicked"].add(user_id)
            self.save_all_data()
            try:
                await message.author.kick(reason=f"{self.WARNING_THRESHOLD}x szabálysértés: {', '.join(violations)}")
                await message.channel.send(f"👢 **{message.author.name} kickelve lett {self.WARNING_THRESHOLD}x figyelmeztetés után.**", delete_after=20)
            except Exception as e:
                print(f"Kick hiba: {e}")
            await self.log_to_admin(message.guild, f"👢 **KICKED {message.author.name}** ({current_warnings} warn) - {', '.join(violations)}")
    
    async def on_member_join(self, member):
        try:
            gdata = self.get_guild_data(member.guild.id)
            if str(member.id) in gdata["kicked"]:
                await self.log_to_admin(member.guild, f"⚠ **Visszatérő {member.name}** - Korábban kickelve volt!")
            account_age_days = (datetime.datetime.now(datetime.timezone.utc) - member.created_at).days
            flags = []
            if account_age_days < 3:
                flags.append(f"🔴 Nagyon új fiók ({account_age_days} nap)")
            elif account_age_days < 7:
                flags.append(f"🟡 Új fiók ({account_age_days} nap)")
            if not member.avatar:
                flags.append("⚠ Nincs avatar")
            is_suspicious = account_age_days < 1 and not member.avatar
            embed = discord.Embed(
                title="👋 Új tag belépett",
                color=discord.Color.red() if is_suspicious else discord.Color.green(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.add_field(name="Felhasználó", value=member.mention, inline=True)
            embed.add_field(name="Fiók kora", value=get_account_age_string(member.created_at), inline=True)
            if flags:
                embed.add_field(name="Megjegyzés", value="\n".join(flags), inline=False)
            if member.avatar:
                embed.set_thumbnail(url=member.avatar.url)
            await self.log_to_admin(member.guild, embed=embed)
        except Exception as e:
            print(f"Join error: {e}")

    async def on_member_unban(self, guild, user):
        gdata = self.get_guild_data(guild.id)
        user_id = str(user.id)
        if user_id in gdata["kicked"]:
            gdata["kicked"].remove(user_id)
            self.save_all_data()
        await self.log_to_admin(guild, f"🔓 **{user.name}** unbanolva!")
    
    async def log_to_admin(self, guild, message=None, embed=None):
        try:
            admin_channel_id = self.get_admin_channel_id(guild)
            if not admin_channel_id:
                for ch in guild.text_channels:
                    if ch.permissions_for(guild.me).send_messages:
                        admin_channel_id = ch.id
                        break
            ch = self.get_channel(admin_channel_id) if admin_channel_id else None
            if not ch:
                for c in guild.text_channels:
                    if "log" in c.name.lower() and c.permissions_for(guild.me).send_messages:
                        ch = c
                        break
            if not ch:
                return
            if message:
                await ch.send(message)
            elif embed:
                await ch.send(embed=embed)
        except Exception as e:
            print(f"Log error: {e}")

    # SLASH PARANCSOK - JAVÍTOTT REGISZTRÁCIÓ
    @app_commands.command(name="warnings", description="Megnézi egy felhasználó figyelmeztetéseit")
    async def warnings_cmd(self, interaction: discord.Interaction, member: discord.Member = None):
        gdata = self.get_guild_data(interaction.guild.id)
        target = member or interaction.user
        warn_count = gdata["warnings"].get(str(target.id), 0)
        await interaction.response.send_message(f"**{target.name}: {warn_count}/{self.WARNING_THRESHOLD} figyelmeztetés ezen a szerveren**", ephemeral=True)
    
    @app_commands.command(name="clearwarnings", description="Törli egy felhasználó figyelmeztetéseit")
    async def clearwarnings_cmd(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Nincs jogod!", ephemeral=True)
            return
        gdata = self.get_guild_data(interaction.guild.id)
        gdata["warnings"][str(member.id)] = 0
        if str(member.id) in gdata["kicked"]:
            gdata["kicked"].remove(str(member.id))
        self.save_all_data()
        await interaction.response.send_message(f"✅ Törölve {member.name} figyelmeztetései")
    
    @app_commands.command(name="statuscheck", description="Bot státusz")
    async def statuscheck_cmd(self, interaction: discord.Interaction):
        gdata = self.get_guild_data(interaction.guild.id)
        embed = discord.Embed(title="🤖 Kamila Safe Status - Multi Server", color=discord.Color.purple())
        embed.add_field(name="Szerver", value=interaction.guild.name, inline=False)
        embed.add_field(name="Figyelt userek (itt)", value=len(gdata["warnings"]), inline=True)
        embed.add_field(name="Kick memória (itt)", value=len(gdata["kicked"]), inline=True)
        embed.add_field(name="Összes szerver", value=len(self.guilds), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="setlogchannel", description="Beállítja a log csatornát ezen a szerveren")
    async def setlogchannel_cmd(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Nincs jogod!", ephemeral=True)
            return
        gdata = self.get_guild_data(interaction.guild.id)
        gdata["admin_channel"] = channel.id
        self.save_all_data()
        await interaction.response.send_message(f"✅ Log csatorna beállítva: {channel.mention}", ephemeral=True)

    @app_commands.command(name="sync", description="Manuálisan sync-eli a slash parancsokat (owner only)")
    async def sync_cmd(self, interaction: discord.Interaction):
        if interaction.user.id != 1047920915641548921:
            await interaction.response.send_message("❌ Csak a tulaj használhatja!", ephemeral=True)
            return
        synced = await self.tree.sync()
        await interaction.response.send_message(f"✅ {len(synced)} parancs syncelve globálisan!", ephemeral=True)

if __name__ == "__main__":
    bot = Kamila()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Nincs DISCORD_TOKEN env!")
    else:
        bot.run(token)
