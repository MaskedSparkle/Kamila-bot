import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import traceback
from flask import Flask
import threading

app_web = Flask(__name__)
@app_web.route('/')
def home():
    return "Kamila WORKING - All slash fixed"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host='0.0.0.0', port=port)

threading.Thread(target=run_web, daemon=True).start()

DATA_FILE = "kamila_data.json"

def load_data():
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
        except: pass
    return {}

def save_data(guild_data):
    try:
        to_save = {}
        for gid, data in guild_data.items():
            to_save[gid] = {
                "warnings": data.get("warnings", {}),
                "kicked": list(data.get("kicked", set())),
                "admin_channel": data.get("admin_channel")
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
        self.WARNING_THRESHOLD = 3 
        self.guild_data = load_data()

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
            if "log" in ch.name.lower():
                return ch.id
        return None

    async def setup_hook(self):
        print("🔧 setup_hook indul...")
        
        # Töröljük a régi rossz parancsokat
        try:
            old_guild = discord.Object(id=1497272521735671810)
            self.tree.clear_commands(guild=old_guild)
            await self.tree.sync(guild=old_guild)
            print("🗑️ Old guild cleared")
        except: pass

        # ÚJ PARANCSOK - direktben itt definiálva, ez a 100% működő módszer
        @self.tree.command(name="warnings", description="Megnézi egy felhasználó figyelmeztetéseit")
        @app_commands.describe(member="Kinek nézzük a warnjait")
        async def warnings(interaction: discord.Interaction, member: discord.Member = None):
            try:
                await interaction.response.defer(ephemeral=True)
                gdata = self.get_guild_data(interaction.guild.id)
                target = member or interaction.user
                cnt = gdata["warnings"].get(str(target.id), 0)
                await interaction.followup.send(f"**{target.name}: {cnt}/{self.WARNING_THRESHOLD} figyelmeztetés**", ephemeral=True)
            except Exception as e:
                print(f"warnings error: {traceback.format_exc()}")
                try:
                    await interaction.followup.send(f"❌ Hiba: {e}", ephemeral=True)
                except: pass

        @self.tree.command(name="clearwarnings", description="Törli egy felhasználó figyelmeztetéseit")
        @app_commands.describe(member="Kinek töröljük")
        async def clearwarnings(interaction: discord.Interaction, member: discord.Member):
            try:
                await interaction.response.defer()
                if not interaction.user.guild_permissions.administrator:
                    await interaction.followup.send("❌ Nincs jogod!", ephemeral=True)
                    return
                gdata = self.get_guild_data(interaction.guild.id)
                gdata["warnings"][str(member.id)] = 0
                gdata["kicked"].discard(str(member.id))
                save_data(self.guild_data)
                await interaction.followup.send(f"✅ Törölve {member.name} warnjai ezen a szerveren")
            except Exception as e:
                print(traceback.format_exc())
                try: await interaction.followup.send(f"❌ {e}", ephemeral=True)
                except: pass

        @self.tree.command(name="statuscheck", description="Bot státusz")
        async def statuscheck(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
                gdata = self.get_guild_data(interaction.guild.id)
                embed = discord.Embed(title="🤖 Kamila Status - WORKING", color=discord.Color.green())
                embed.add_field(name="Szerver", value=interaction.guild.name, inline=False)
                embed.add_field(name="Figyelt userek", value=len(gdata["warnings"]), inline=True)
                embed.add_field(name="Kick memória", value=len(gdata["kicked"]), inline=True)
                embed.add_field(name="Összes szerver", value=len(self.guilds), inline=True)
                embed.add_field(name="Mód", value="MULTI SERVER FIXED", inline=True)
                await interaction.followup.send(embed=embed, ephemeral=True)
            except Exception as e:
                print(traceback.format_exc())

        @self.tree.command(name="setlog", description="Beállítja a log csatornát ezen a szerveren")
        @app_commands.describe(channel="Melyik csatornába logoljon")
        async def setlog(interaction: discord.Interaction, channel: discord.TextChannel):
            try:
                await interaction.response.defer(ephemeral=True)
                if not interaction.user.guild_permissions.administrator:
                    await interaction.followup.send("❌ Nincs jogod!", ephemeral=True)
                    return
                gdata = self.get_guild_data(interaction.guild.id)
                gdata["admin_channel"] = channel.id
                save_data(self.guild_data)
                await interaction.followup.send(f"✅ Log csatorna beállítva: {channel.mention} | Szerver: {interaction.guild.name}", ephemeral=True)
                print(f"✅ Log set: {interaction.guild.name} -> {channel.name}")
            except Exception as e:
                print(f"setlog error: {traceback.format_exc()}")
                try:
                    await interaction.followup.send(f"❌ Hiba: {e}", ephemeral=True)
                except: pass

        @self.tree.command(name="sync", description="Manuálisan sync-eli a parancsokat (tulaj only)")
        async def sync(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
                if interaction.user.id != 1047920915641548921:
                    await interaction.followup.send("❌ Csak a tulaj!", ephemeral=True)
                    return
                synced = await self.tree.sync()
                # Guild sync is
                for guild in self.guilds:
                    try:
                        await self.tree.sync(guild=guild)
                    except: pass
                await interaction.followup.send(f"✅ {len(synced)} parancs syncelve! Nevek: {', '.join([c.name for c in synced])}", ephemeral=True)
            except Exception as e:
                print(traceback.format_exc())
                try: await interaction.followup.send(f"❌ {e}", ephemeral=True)
                except: pass

        @self.tree.command(name="ping", description="Teszt hogy működik-e a slash")
        async def ping(interaction: discord.Interaction):
            await interaction.response.send_message("🏓 Pong! Slash működik! ✅", ephemeral=True)

        try:
            synced = await self.tree.sync()
            print(f"✅ GLOBAL SYNC: {len(synced)} parancs -> {', '.join([c.name for c in synced])}")
        except Exception as e:
            print(f"❌ Global sync hiba: {e}\n{traceback.format_exc()}")

    async def on_ready(self):
        print(f"🤖 {self.user.name} | {len(self.guilds)} szerveren")
        # on_ready-ben is sync-elünk guild-enként, mert setup_hook-ban még üres a guild lista
        try:
            for guild in self.guilds:
                try:
                    await self.tree.sync(guild=guild)
                    print(f"✅ Guild sync {guild.name}: OK")
                except Exception as e:
                    print(f"❌ Guild {guild.name} sync hiba: {e}")
        except Exception as e:
            print(f"on_ready sync hiba: {e}")

    async def on_message(self, message):
        if message.author == self.user or (hasattr(message.author, 'bot') and message.author.bot): return
        if not message.guild: return
        if message.author.guild_permissions.administrator or message.author.guild_permissions.manage_messages: return
        # egyszerű spam védelem
        if len(message.content) > 800:
            try:
                await message.delete()
                gdata = self.get_guild_data(message.guild.id)
                uid = str(message.author.id)
                gdata["warnings"][uid] = gdata["warnings"].get(uid, 0) + 1
                save_data(self.guild_data)
                await message.channel.send(f"⚠ {message.author.mention} {gdata['warnings'][uid]}/{self.WARNING_THRESHOLD} warn", delete_after=10)
            except: pass

if __name__ == "__main__":
    bot = Kamila()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Nincs DISCORD_TOKEN!")
    else:
        bot.run(token)
