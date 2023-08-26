import os

from discord.ext import commands
import discord


class MemberJoin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.bot:
            role = discord.utils.get(member.guild.roles, name=os.environ["BOT_ROLE_NAME"])
            await member.add_roles(role)
            return

        newcomer = discord.utils.get(member.guild.roles, name=os.environ["ROOKIE_ROLE_NAME"])
        reported = discord.utils.get(member.guild.roles, name=os.environ["MCID_REPORTED_ROLE_NAME"])

        self.bot.cur.execute("SELECT COUNT(*) FROM user_data WHERE user_id = %s", (member.id,))
        if self.bot.cur.fetchone()[0]:
            await member.add_roles(reported)
            self.bot.cur.execute("SELECT bid_score FROM user_data WHERE user_id = %s", (member.id,))
            bidscore, = self.bot.cur.fetchone()
            await self.bot.update_bidscore_role(member, bidscore)
        else:
            await member.add_roles(newcomer)


async def setup(bot):
    await bot.add_cog(MemberJoin(bot))
