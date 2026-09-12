import discord
from discord import app_commands
from discord.ext import commands
import datetime
import re
import os
import json
import traceback
from flask import Flask
import threading

app_web = Flask(__name__)
@app_web.route('/')
def home():
    return "Kamila is alive! 🛡 Fixed SignatureMismatch"

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
    if years > 0: parts.append(f"{years} év")
    if months > 0: parts.append(f"{months} hónap")
    if final_days > 0 or not parts: parts.append(f"{final_days} nap")
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
        self.NSFW_PATTERNS = [r'\b(pornhub|onlyfans|xvideos|xnxx)\.com\b']
        self.BAD_WORDS_HARD = [r'\bkurva\b', r'baszd meg', r'\bkurva anyád\b', r'\bbuzi\b', r'\bgeci\b']
        self.BAD_WORDS_SOFT = [r'\bhülye\b', r'\bidi[oó]ta?\b']

    def load_all_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    for gid in raw:
                        raw[gid]["kicked"] = set(raw[gid].get("kicked", []))
                        raw[gid]["warnings"] = raw[gid].get("warnings", {})
                        raw[gid]["admin_channel"] = raw[gid].get("admin_channel")
                    return raw
            except Exception as e:
                print(f"Load error: {e}")
        return {}

    def save_all_data(self):
        try:
            to_save = {}
            for gid, data in self.guild_data.items():
                to_save[gid] = {"warnings": data.get("warnings", {}), "kicked": list(data.get("kicked", set())), "admin_channel": data.get("admin_channel")}
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
        if gdata.get("admin_channel"): return gdata["admin_channel"]
        for ch in guild.text_channels:
            if ch.name.lower() in ["logs", "log", "admin", "kamila-log"]:
                return ch.id
        return None

    async def setup_hook(self):
        
        try:
            OLD_GUILD = discord.Object(id=1497272521735671810)
            self.tree.clear_commands(guild=OLD_GUILD)
            await self.tree.sync(guild=OLD_GUILD)
            print("🗑️ Régi guild parancsok törölve")
        except: pass

        try:
           
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
            print("🗑️ Global parancsok törölve - most újra regisztráljuk")
        except Exception as e:
            print(f"Clear hiba: {e}")

        # Új parancsok hozzáadása
        self.tree.add_command(self.warnings_cmd)
        self.tree.add_command(self.clearwarnings_cmd)
        self.tree.add_command(self.statuscheck_cmd)
        self.tree.add_command(self.setlogchannel_cmd)
        self.tree.add_command(self.sync_cmd)

        try:
            synced = await self.tree.sync()
            print(f"✅ Global sync OK: {len(synced)} parancs -> {', '.join([c.name for c in synced])}")
        except Exception as e:
            print(f"❌ Sync hiba: {e}\n{traceback.format_exc()}")

    async def on_ready(self):
        print(f"🤖 {self.user.name} | {len(self.guilds)} szerveren")

    async def on_message(self, message):
        if message.author == self.user or (hasattr(message.author, 'bot') and message.author.bot): return
        if not message.guild: return
        if message.author.guild_permissions.administrator or message.author.guild_permissions.manage_messages: return
        violation = await self.check_rule_violations(message)
        if violation: await self.handle_violation(message, violation)

    async def check_rule_violations(self, message):
        content = message.content
        violations = []
        for p in self.NSFW_PATTERNS:
            if re.search(p, content, re.I): violations.append("NSFW link"); break
        for p in self.BAD_WORDS_HARD:
            if re.search(p, content, re.I): violations.append("Durva szó"); break
        for p in self.BAD_WORDS_SOFT:
            if re.search(p, content, re.I): violations.append("Enyhe"); break
        if len(content) > 800 or content.count('http') > 4: violations.append("SPAM")
        return violations
    
    async def handle_violation(self, message, violations):
        gdata = self.get_guild_data(message.guild.id)
        uid = str(message.author.id)
        gdata["warnings"][uid] = gdata["warnings"].get(uid, 0) + 1
        self.save_all_data()
        try: await message.delete()
        except: pass
        if gdata["warnings"][uid] < self.WARNING_THRESHOLD:
            try: await message.channel.send(f"**⚠ {message.author.mention} {gdata['warnings'][uid]}. figyelmeztetés!**", delete_after=15)
            except: pass
            await self.log_to_admin(message.guild, f"⚠ {message.author.name} warn {gdata['warnings'][uid]}/{self.WARNING_THRESHOLD}")
        else:
            gdata["kicked"].add(uid)
            self.save_all_data()
            try: await message.author.kick(reason="3x warn")
            except: pass
            await self.log_to_admin(message.guild, f"👢 KICK {message.author.name}")

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

    @app_commands.command(name="warnings", description="Megnézi egy felhasználó figyelmeztetéseit")
    async def warnings_cmd(self, interaction: discord.Interaction, member: discord.Member = None):
        try:
            await interaction.response.defer(ephemeral=True)
            gdata = self.get_guild_data(interaction.guild.id)
            target = member or interaction.user
            cnt = gdata["warnings"].get(str(target.id), 0)
            await interaction.followup.send(f"**{target.name}: {cnt}/{self.WARNING_THRESHOLD} warn**", ephemeral=True)
        except Exception as e:
            print(traceback.format_exc())
            try: await interaction.followup.send(f"❌ {e}", ephemeral=True)
            except: pass

    @app_commands.command(name="clearwarnings", description="Törli egy felhasználó figyelmeztetéseit")
    async def clearwarnings_cmd(self, interaction: discord.Interaction, member: discord.Member):
        try:
            await interaction.response.defer()
            if not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            gdata = self.get_guild_data(interaction.guild.id)
            gdata["warnings"][str(member.id)] = 0
            gdata["kicked"].discard(str(member.id))
            self.save_all_data()
            await interaction.followup.send(f"✅ Törölve {member.name}")
        except Exception as e:
            print(traceback.format_exc())
            try: await interaction.followup.send(f"❌ {e}", ephemeral=True)
            except: pass

    @app_commands.command(name="statuscheck", description="Bot státusz")
    async def statuscheck_cmd(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            gdata = self.get_guild_data(interaction.guild.id)
            embed = discord.Embed(title="🤖 Kamila Status", color=discord.Color.purple())
            embed.add_field(name="Szerver", value=interaction.guild.name)
            embed.add_field(name="Warns", value=len(gdata["warnings"]))
            embed.add_field(name="Szerverek", value=len(self.guilds))
            await interaction.followup.send(embed=embed, ephemeral=True)
        except: pass

    @app_commands.command(name="setlogchannel", description="Beállítja a log csatornát ezen a szerveren")
    async def setlogchannel_cmd(self, interaction: discord.Interaction, channel: discord.TextChannel):
        try:
            await interaction.response.defer(ephemeral=True)
            if not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
            gdata = self.get_guild_data(interaction.guild.id)
            gdata["admin_channel"] = channel.id
            self.save_all_data()
            await interaction.followup.send(f"✅ Log csatorna beállítva: {channel.mention}", ephemeral=True)
        except Exception as e:
            print(f"setlogchannel error: {traceback.format_exc()}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ {e}", ephemeral=True)
            except: pass

    @app_commands.command(name="sync", description="Manuálisan sync-eli a slash parancsokat")
    async def sync_cmd(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            if interaction.user.id != 1047920915641548921:
                await interaction.followup.send("❌ Csak a tulaj!", ephemeral=True); return
            synced = await self.tree.sync()
            await interaction.followup.send(f"✅ {len(synced)} parancs syncelve!", ephemeral=True)
        except Exception as e:
            try: await interaction.followup.send(f"❌ {e}", ephemeral=True)
            except: pass

if __name__ == "__main__":
    bot = Kamila()
    token = os.getenv("DISCORD_TOKEN")
    bot.run(token)
