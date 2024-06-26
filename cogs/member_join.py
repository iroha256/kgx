import os

import discord
from discord.ext import commands


class MemberJoin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.bot:
            role = discord.utils.get(member.guild.roles, id=int(os.environ["BOT_ROLE_ID"]))
            await member.add_roles(role)
            return

        newcomer = discord.utils.get(member.guild.roles, id=int(os.environ["ROOKIE_ROLE_ID"]))
        reported = discord.utils.get(member.guild.roles, id=int(os.environ["MCID_REPORTED_ROLE_ID"]))

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
