import discord
from discord import app_commands
from discord.ext import commands
import datetime
import re
import os
from datetime import timedelta

# Segédfüggvény az évek, hónapok és napok kiszámításához
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
        intents.bans = True  # Fontos a tiltások és unbanok figyeléséhez!
        
        super().__init__(command_prefix='!', intents=intents)
        
        self.ADMIN_CHANNEL_ID = 1497294782786048020
        self.WARNING_THRESHOLD = 2  # 2 csúnya beszéd után repül!
        
        self.kicked_users = set()
        
        self.NSFW_PATTERNS = [
            r'(pornhub|onlyfans|xvideos|xbunker|xnxx)\.com',
            r'(nsfw|adult|18\+|xxx|sexy)',
            r'(spam|phishing|scam|fake)',
        ]
        
        self.BAD_WORDS_PATTERNS = [
            r'kurva(?!san)',
            r'baszd meg',
            r'aszód meg',
            r'tokaszod',
            r'kurva anyád',
            r'anyád',
            r'anád',
            r'kurva apád',
            r'hülye',
            r'idiot',
            r'stupid',
            r'dumbass',
            r'motherfucker',
            r'sonofabitch',
            r'shit',
            r'bitch',
            r'asshole',
            r'pénisze',
            r'puncija',
            r'gödörbe',
            r'kussolj',
            r'csukd be a',
            r'szarozás',
            r'buta',
            r'barom',
            r'azembertolvaj',
            r'paraszt',
            r'ribanc',
            r'prostit',
            r'csitri',
            r'pofátlan',
            r'köcsög',
            r'bazmeg',
            r'buzi',
        ]
        
        self.BAD_BEHAVIOR_PATTERNS = [
            r'(hate|bully|threat|harass)',
        ]
        
        self.user_warnings = {}
        self.suspicious_users = []
    
    async def setup_hook(self):
        try:
            GUILD_ID = discord.Object(id=1497272521735671810)
            self.tree.copy_global_to(guild=GUILD_ID)
            synced = await self.tree.sync(guild=GUILD_ID)
            print(f"✅ Sikeresen szinkronizálva {len(synced)} perjel parancs erre a szerverre!")
        except Exception as e:
            print(f"❌ Hiba a parancsok szinkronizálásakor: {e}")

    async def on_ready(self):
        print(f"🤖 Bejelentkezve mint: {self.user.name} (ID: {self.user.id})")
    
    async def on_message(self, message):
        if message.author == self.user or (hasattr(message.author, 'bot') and message.author.bot):
            return
            
        if message.guild and (message.author == message.guild.owner or message.author.guild_permissions.administrator):
            return
        
        violation = await self.check_rule_violations(message)
        
        if violation:
            await self.handle_violation(message, violation)
    
    async def check_rule_violations(self, message):
        violations = []
        
        for pattern in self.NSFW_PATTERNS:
            if re.search(pattern, message.content, re.IGNORECASE):
                violations.append("NSFW_CONTENT")
                break
        
        for pattern in self.BAD_WORDS_PATTERNS:
            if re.search(pattern, message.content, re.IGNORECASE):
                violations.append("BAD_LANGUAGE_HU")
                break
        
        for pattern in self.BAD_BEHAVIOR_PATTERNS:
            if re.search(pattern, message.content, re.IGNORECASE):
                violations.append("BAD_LANGUAGE_EN")
                break
        
        if len(message.content) > 500 or message.content.count('http') > 3:
            violations.append("SPAM")
        
        if message.content.isupper() and len(message.content) > 50:
            violations.append("CAPS_LOCK")
        
        return violations
    
    async def handle_violation(self, message, violations):
        user_id = str(message.author.id)
        
        if user_id not in self.user_warnings:
            self.user_warnings[user_id] = 0
        
        self.user_warnings[user_id] += 1
        
        # 1. Figyelmeztetés: törli az üzenetet és kiírja a figyelmeztetést
        if self.user_warnings[user_id] == 1:
            await message.delete()
            await message.channel.send(
                f"**⚠️ {message.author.name}, ha még egyszer csunyát írsz, akkor repülsz innen a szerverről!**",
                delete_after=10
            )
            await self.log_to_admin(f"❌ **Figyelmeztetés küldve {message.author.name}-nek** - Első szabálysértés: {', '.join(violations)}")
        
        # 2. (vagy több) alkalom: repül a szerverről!
        else:
            self.kicked_users.add(user_id)
            await message.delete()
            try:
                await message.author.kick(reason="Többszöri csúnya beszéd / szabálysértés")
            except Exception:
                pass
            await self.log_to_admin(f"👢 **KICKED {message.author.name}** - Második alkalom után kirúgva és hozzáadva a tiltólistához!")
    
    # Kamila csendben figyeli, ha bárkit unbanolsz a szerveren
    async def on_member_unban(self, guild, user):
        user_id = str(user.id)
        if user_id in self.kicked_users:
            self.kicked_users.remove(user_id)
        await self.log_to_admin(f"🔓 **Kamila észlelte:** **{user.name}** unbanolva lett, így már újra beléphet a szerverre! ✨")

    async def on_member_join(self, member):
        try:
            if str(member.id) in self.kicked_users:
                await member.ban(reason="Return ban - Previously kicked and returned!")
                await self.log_to_admin(f"🚫 **AUTO BANNED returning user {member.name}** - Was previously kicked!")
                return
            
            account_age_str = get_account_age_string(member.created_at)
            account_age_days = (datetime.datetime.now(datetime.timezone.utc) - member.created_at).days
            
            flags = []
            if account_age_days < 7:
                flags.append("NEW_ACCOUNT")
            if member.nick:
                flags.append("HAS_NICK")
            if len(member.roles) == 1:
                flags.append("NO_ROLES")
            
            embed = discord.Embed(
                title="🚨 NEW MEMBER ALERT",
                color=discord.Color.yellow() if flags else discord.Color.green(),
                timestamp=datetime.datetime.utcnow()
            )
            
            embed.add_field(name="Username", value=member.name, inline=True)
            embed.add_field(name="Account Age", value=account_age_str, inline=True)
            embed.add_field(name="Roles", value=f"{len(member.roles)}", inline=True)
            
            if flags:
                embed.add_field(name="Suspicious Flags", value=', '.join(flags), inline=False)
                if member.avatar:
                    embed.set_thumbnail(url=member.avatar.url)
            
            await self.log_to_admin(embed=embed)
        
        except Exception as e:
            print(f"Error checking new member: {e}")
    
    async def log_to_admin(self, message=None, embed=None):
        try:
            admin_channel = self.get_channel(self.ADMIN_CHANNEL_ID)
            if message:
                await admin_channel.send(message)
            elif embed:
                await admin_channel.send(embed=embed)
        except Exception as e:
            print(f"Error logging to admin: {e}")
    
    @app_commands.command(name="warnings", description="Megnézi egy felhasználó figyelmeztetéseit")
    async def warnings(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        warn_count = self.user_warnings.get(str(target.id), 0)
        await interaction.response.send_message(f"**Warnings for {target.name}: {warn_count}/{self.WARNING_THRESHOLD}**")
    
    @app_commands.command(name="clearwarnings", description="Törli egy felhasználó figyelmeztetéseit")
    async def clearwarnings(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Ehhez nincs jogod!", ephemeral=True)
            return
        
        self.user_warnings[str(member.id)] = 0
        await interaction.response.send_message(f"✅ Cleared warnings for {member.name}")
    
    @app_commands.command(name="statuscheck", description="Megnézi a bot státuszát")
    async def statuscheck(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🤖 Bot Status", color=discord.Color.purple())
        embed.add_field(name="Users tracked", value=len(self.user_warnings), inline=True)
        embed.add_field(name="Kick memory", value=f"{len(self.kicked_users)}", inline=True)
        embed.add_field(name="Pending reports", value=len(self.suspicious_users), inline=True)
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="kicklist", description="Kilistázza a kickelt felhasználókat")
    async def kicklist(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Ehhez nincs jogod!", ephemeral=True)
            return
        
        if len(self.kicked_users) == 0:
            await interaction.response.send_message("ℹ️ No users in kick memory", ephemeral=True)
        else:
            await interaction.response.send_message(f"📋 **Kicked Users Memory ({len(self.kicked_users)})**:\n```\n{'\n'.join(self.kicked_users)}\n```", ephemeral=True)

if __name__ == "__main__":
    bot = Kamila()
    token = os.getenv("DISCORD_TOKEN")  # A Railway környezeti változójából olvassa be
    bot.run(token)
