import discord
from discord import app_commands
from discord.ext import commands
import datetime
import re
import os
import json
from flask import Flask
import threading

# --- WEB PORT KAMILÁNAK (Render miatt) ---
app_web = Flask(__name__)
@app_web.route('/')
def home():
    return "Kamila is alive! 🛡 Safe Mode ON"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host='0.0.0.0', port=port)

threading.Thread(target=run_web, daemon=True).start()
# --- VÉGE ---

# --- MENTÉS RENDER ÚJRAINDULÁS ELLEN ---
DATA_FILE = "kamila_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("warnings", {}), set(data.get("kicked", []))
        except:
            pass
    return {}, set()

def save_data(warnings, kicked):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"warnings": warnings, "kicked": list(kicked)}, f)
    except Exception as e:
        print(f"Save error: {e}")

# --- ACCOUNT AGE ---
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
        
        self.ADMIN_CHANNEL_ID = 1497294782786048020
        self.WARNING_THRESHOLD = 3 
        
        warnings, kicked = load_data()
        self.user_warnings = warnings
        self.kicked_users = kicked
        
        # SAFE: \b szóhatárokkal, kevesebb false positive
        self.NSFW_PATTERNS = [
            r'\b(pornhub|onlyfans|xvideos|xnxx)\.com\b',
            r'https?://\S*(pornhub|onlyfans|xvideos)\S*',
        ]
        
        # Csak a durvák maradnak, a "hülye, buta, paraszt" kivéve vagy enyhébb
        self.BAD_WORDS_HARD = [
            r'\bkurva\b',
            r'baszd meg',
            r'\bkurva anyád\b',
            r'\bkurva apád\b',
            r'\banyád\b',
            r'\bköcsög\b',
            r'\bbuzi\b',
            r'\bbazmeg\b',
            r'\bribanc\b',
            r'\bgeci\b',
        ]
        
        self.BAD_WORDS_SOFT = [
            r'\bhülye\b',
            r'\bidi[oó]ta?\b',
            r'\bbarom\b',
            r'\bparaszt\b',
            r'\bkussolj\b',
        ]
        
        self.suspicious_users = []
    
    async def setup_hook(self):
        try:
            GUILD_ID = discord.Object(id=1497272521735671810)
            self.tree.copy_global_to(guild=GUILD_ID)
            synced = await self.tree.sync(guild=GUILD_ID)
            print(f"✅ Sikeresen szinkronizálva {len(synced)} parancs!")
        except Exception as e:
            print(f"❌ Hiba szinkronizáláskor: {e}")

    async def on_ready(self):
        print(f"🤖 Bejelentkezve mint: {self.user.name} (ID: {self.user.id}) | Safe Mode")

    async def on_message(self, message):
        if message.author == self.user or (hasattr(message.author, 'bot') and message.author.bot):
            return
        if not message.guild:
            return
        # Admin + mod bypass
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
        
        # Soft csak akkor számít ha ismételgeti, de most egyelőre csak logoljuk
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
        user_id = str(message.author.id)
        
        if user_id not in self.user_warnings:
            self.user_warnings[user_id] = 0
        self.user_warnings[user_id] += 1
        current_warnings = self.user_warnings[user_id]
        save_data(self.user_warnings, self.kicked_users)
        
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
            await self.log_to_admin(f"⚠ **Figyelmeztetés {message.author.name}** ({current_warnings}/{self.WARNING_THRESHOLD}) - {', '.join(violations)} | Üzenet: `{message.content[:100]}`")
        
        else:
            # Kick de NEM auto-ban vissza jövetelnél
            self.kicked_users.add(user_id)
            save_data(self.user_warnings, self.kicked_users)
            try:
                await message.author.kick(reason=f"{self.WARNING_THRESHOLD}x szabálysértés: {', '.join(violations)}")
                await message.channel.send(f"👢 **{message.author.name} kickelve lett {self.WARNING_THRESHOLD}x figyelmeztetés után.**", delete_after=20)
            except Exception as e:
                print(f"Kick hiba: {e}")
            await self.log_to_admin(f"👢 **KICKED {message.author.name}** ({current_warnings} warn) - {', '.join(violations)}")
    
    async def on_member_join(self, member):
        try:
            # SAFE: nem banolja auto, csak jelzi
            if str(member.id) in self.kicked_users:
                await self.log_to_admin(f"⚠ **Visszatérő {member.name}** - Korábban kickelve volt! Figyeljetek rá.")
                # await member.ban -> KIVÉVE, most már nem banoljuk!
            
            account_age_days = (datetime.datetime.now(datetime.timezone.utc) - member.created_at).days
            
            flags = []
            if account_age_days < 3:
                flags.append(f"🔴 Nagyon új fiók ({account_age_days} nap)")
            elif account_age_days < 7:
                flags.append(f"🟡 Új fiók ({account_age_days} nap)")
            if not member.avatar:
                flags.append("⚠ Nincs avatar")

            # Csak akkor gyanús ha tényleg gyanús
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
            
            await self.log_to_admin(embed=embed)
        
        except Exception as e:
            print(f"Join error: {e}")

    async def on_member_unban(self, guild, user):
        user_id = str(user.id)
        if user_id in self.kicked_users:
            self.kicked_users.remove(user_id)
            save_data(self.user_warnings, self.kicked_users)
        await self.log_to_admin(f"🔓 **{user.name}** unbanolva, újra beléphet!")
    
    async def log_to_admin(self, message=None, embed=None):
        try:
            ch = self.get_channel(self.ADMIN_CHANNEL_ID)
            if not ch:
                return
            if message:
                await ch.send(message)
            elif embed:
                await ch.send(embed=embed)
        except Exception as e:
            print(f"Log error: {e}")

    # SLASH PARANCSOK
    @app_commands.command(name="warnings", description="Megnézi egy felhasználó figyelmeztetéseit")
    async def warnings(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        warn_count = self.user_warnings.get(str(target.id), 0)
        await interaction.response.send_message(f"**{target.name}: {warn_count}/{self.WARNING_THRESHOLD} figyelmeztetés**", ephemeral=True)
    
    @app_commands.command(name="clearwarnings", description="Törli egy felhasználó figyelmeztetéseit")
    async def clearwarnings(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Nincs jogod!", ephemeral=True)
            return
        self.user_warnings[str(member.id)] = 0
        if str(member.id) in self.kicked_users:
            self.kicked_users.remove(str(member.id))
        save_data(self.user_warnings, self.kicked_users)
        await interaction.response.send_message(f"✅ Törölve {member.name} figyelmeztetései")
    
    @app_commands.command(name="statuscheck", description="Bot státusz")
    async def statuscheck(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🤖 Kamila Safe Status", color=discord.Color.purple())
        embed.add_field(name="Figyelt userek", value=len(self.user_warnings), inline=True)
        embed.add_field(name="Kick memória", value=len(self.kicked_users), inline=True)
        embed.add_field(name="Mód", value="SAFE - nincs auto-ban", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

if __name__ == "__main__":
    bot = Kamila()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Nincs DISCORD_TOKEN env!")
    else:
        bot.run(token)
