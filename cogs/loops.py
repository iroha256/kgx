import os

import discord
import psycopg2
from discord.ext import commands, tasks

SQLpath = os.environ["DATABASE_URL"]
db = psycopg2.connect(SQLpath)  # sqlに接続
cur = db.cursor()  # なんか操作する時に使うやつ


class Loops(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.presence_change_task.start()

    @tasks.loop(seconds=20)
    async def presence_change_task(self):
        await self.bot.wait_until_ready()
        game = discord.Game(f"{self.bot.get_guild(int(os.environ['KGX_GUILD_ID'])).member_count}人を監視中")
        await self.bot.change_presence(status=discord.Status.online, activity=game)


async def setup(bot):
    await bot.add_cog(Loops(bot))
