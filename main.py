import discord
from discord.ext import commands
import datetime
import re
import os
from datetime import timedelta

class Kamila(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.messages = True
        intents.guilds = True
        
        super().__init__(command_prefix='!', intents=intents)
        
        self.ADMIN_CHANNEL_ID = 1539415065873350686
        self.WARNING_THRESHOLD = 3
        
        # ✅ HOZZÁADVA: Kicked users tracking (memória)
        self.kicked_users = set()  # ID-k tárolása
        
        # NSFW linkek
        self.NSFW_PATTERNS = [
            r'(pornhub|onlyfans|xvideos|xbunker|xnxx)\.com',
            r'(nsfw|adult|18\+|xxx|sexy)',
            r'(spam|phishing|scam|fake)',
        ]
        
        # Csúnya szavak
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
            r'(caps lock|SHOUTING)',
            r'(advertising|advert|promo|server)',
        ]
        
        self.user_warnings = {}
        self.suspicious_users = []
    
    async def setup_hook(self):
        print(f"🤖 Logged in as {self.user.name}")
    
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.user or (hasattr(message.author, 'bot') and message.author.bot):
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
        
        if self.user_warnings[user_id] == 1:
            await message.delete()
            await message.channel.send(
                f"**⚠️ {message.author.name}, ez sértő nyelvhasználat!**",
                delete_after=10
            )
            await self.log_to_admin(f"❌ **Figyelmeztetés issued to {message.author.name}** - First violation: {', '.join(violations)}")
        
        elif self.user_warnings[user_id] == self.WARNING_THRESHOLD:
            # ✅ Return ban system! Ha már kirúgták, most BAN lesz!
            if user_id in self.kicked_users:
                await message.author.ban(reason="Return ban - Previously kicked")
                await self.log_to_admin(f"🚫 **RETURN BANNED {message.author.name}** - Previously kicked!")
            else:
                await message.author.timeout(datetime.datetime.utcnow() + timedelta(hours=1))
                await self.log_to_admin(f"🔇 **Timed out {message.author.name} for 1 hour** - Reached warning threshold")
        
        else:
            # ✅ MEMORIZE - Kirúgás előtt!
            self.kicked_users.add(user_id)
            await message.author.kick(reason="Multiple rule violations")
            await self.log_to_admin(f"👢 **KICKED {message.author.name}** - Added to return ban list")
    
    @commands.Cog.listener()
    async def on_member_join(self, member):
        try:
            # ✅ RETURN BAN CHECK! Ha visszajön a kirúgott!
            if str(member.id) in self.kicked_users:
                await member.ban(reason="Return ban - Previously kicked and returned!")
                await self.log_to_admin(f"🚫 **AUTO BANNED returning user {member.name}** - Was previously kicked!")
                return  # Ne folytasd, már bannolva!
            
            account_age = datetime.datetime.now(datetime.timezone.utc) - member.created_at
            
            report = {
                'user': member.name,
                'discriminator': member.discriminator,
                'user_id': member.id,
                'account_age_days': account_age.days,
                'joined_at': member.joined_at,
                'nicknames': 1 if member.nick else 0,
                'roles': len(member.roles),
                'is_verified': 'N/A'
            }
            
            flags = []
            if account_age.days < 7:
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
            embed.add_field(name="Account Age", value=f"{report['account_age_days']} days", inline=True)
            embed.add_field(name="Roles", value=f"{report['roles']}", inline=True)
            
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
    
    @commands.command()
    async def warnings(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        warn_count = self.user_warnings.get(str(target.id), 0)
        await ctx.send(f"**Warnings for {target.name}: {warn_count}/{self.WARNING_THRESHOLD}**")
    
    @commands.command()
    async def clearwarnings(self, ctx, member: discord.Member):
        if not ctx.author.guild_permissions.administrator:
            return
        
        self.user_warnings[str(member.id)] = 0
        await ctx.send(f"✅ Cleared warnings for {member.name}")
    
    @commands.command()
    async def statuscheck(self, ctx):
        embed = discord.Embed(title="🤖 Bot Status", color=discord.Color.purple())
        embed.add_field(name="Users tracked", value=len(self.user_warnings), inline=True)
        embed.add_field(name="Kick memory", value=f"{len(self.kicked_users)}", inline=True)
        embed.add_field(name="Pending reports", value=len(self.suspicious_users), inline=True)
        await ctx.send(embed=embed)
    
    @commands.command()
    async def kicklist(self, ctx):
        """Megmutatja a kirúgottak listáját"""
        if not ctx.author.guild_permissions.administrator:
            return
        
        if len(self.kicked_users) == 0:
            await ctx.send("ℹ️ No users in kick memory")
        else:
            await ctx.send(f"📋 **Kicked Users Memory ({len(self.kicked_users)})**:\n```\n{'\n'.join(self.kicked_users)}\n```")

if __name__ == "__main__":
    bot = Kamila()
    token = os.getenv('BOT_TOKEN')
    if not token:
        print("❌ BOT_TOKEN not set!")
        exit(1)
    bot.run(token)
