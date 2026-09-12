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
    return "Kamila is alive! FIXED setlog"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host='0.0.0.0', port=port)

threading.Thread(target=run_web, daemon=True).start()

DATA_FILE = "kamila_data.json"

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
            except: pass
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
        except: pass
        try:
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
            print("🗑️ Összes régi parancs törölve")
        except Exception as e:
            print(f"Clear hiba: {e}")

        
        self.tree.add_command(self.warnings_cmd)
        self.tree.add_command(self.clearwarnings_cmd)
        self.tree.add_command(self.statuscheck_cmd)
        self.tree.add_command(self.setlog_cmd) 
        self.tree.add_command(self.sync_cmd)

       
        try:
            synced_global = await self.tree.sync()
            print(f"✅ Global sync: {len(synced_global)} parancs")
            
            for guild in self.guilds:
                try:
                    self.tree.copy_global_to(guild=guild)
                    synced_guild = await self.tree.sync(guild=guild)
                    print(f"✅ Guild sync {guild.name}: {len(synced_guild)}")
                except Exception as ge:
                    print(f"Guild {guild.id} sync hiba: {ge}")
        except Exception as e:
            print(f"❌ Sync hiba: {e}\n{traceback.format_exc()}")

    async def on_ready(self):
        print(f"🤖 {self.user.name} | {len(self.guilds)} szerveren")

    async def on_message(self, message):
        if message.author == self.user or (hasattr(message.author, 'bot') and message.author.bot): return
        if not message.guild: return
        if message.author.guild_permissions.administrator or message.author.guild_permissions.manage_messages: return
        if len(message.content) > 800: 
            try:
                await message.delete()
                gdata = self.get_guild_data(message.guild.id)
                uid = str(message.author.id)
                gdata["warnings"][uid] = gdata["warnings"].get(uid, 0) + 1
                self.save_all_data()
            except: pass

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
        await interaction.response.defer(ephemeral=True)
        gdata = self.get_guild_data(interaction.guild.id)
        target = member or interaction.user
        cnt = gdata["warnings"].get(str(target.id), 0)
        await interaction.followup.send(f"**{target.name}: {cnt}/{self.WARNING_THRESHOLD} warn**", ephemeral=True)

    @app_commands.command(name="clearwarnings", description="Törli egy felhasználó figyelmeztetéseit")
    async def clearwarnings_cmd(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer()
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ Nincs jogod!", ephemeral=True); return
        gdata = self.get_guild_data(interaction.guild.id)
        gdata["warnings"][str(member.id)] = 0
        gdata["kicked"].discard(str(member.id))
        self.save_all_data()
        await interaction.followup.send(f"✅ Törölve {member.name}")

    @app_commands.command(name="statuscheck", description="Bot státusz")
    async def statuscheck_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gdata = self.get_guild_data(interaction.guild.id)
        embed = discord.Embed(title="🤖 Kamila Status", color=discord.Color.purple())
        embed.add_field(name="Szerver", value=interaction.guild.name)
        embed.add_field(name="Warns", value=len(gdata["warnings"]))
        embed.add_field(name="Szerverek", value=len(self.guilds))
        await interaction.followup.send(embed=embed, ephemeral=True)

    
    @app_commands.command(name="setlog", description="Beállítja a log csatornát (ÚJ)")
    @app_commands.describe(channel="Melyik csatornába logoljon")
    async def setlog_cmd(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ Nincs jogod!", ephemeral=True)
            return
        gdata = self.get_guild_data(interaction.guild.id)
        gdata["admin_channel"] = channel.id
        self.save_all_data()
        await interaction.followup.send(f"✅ Log csatorna beállítva: {channel.mention}\nSzerver: {interaction.guild.name}", ephemeral=True)

    @app_commands.command(name="sync", description="Manuálisan sync-eli a parancsokat")
    async def sync_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if interaction.user.id != 1047920915641548921:
            await interaction.followup.send("❌ Csak a tulaj!", ephemeral=True); return
        
        await self.tree.sync()
        for guild in self.guilds:
            try:
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            except: pass
        await interaction.followup.send(f"✅ Sync kész! Próbáld újra a /setlog-ot", ephemeral=True)

if __name__ == "__main__":
    bot = Kamila()
    token = os.getenv("DISCORD_TOKEN")
    bot.run(token)
