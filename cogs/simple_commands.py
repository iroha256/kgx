import os

import discord
from discord.ext import commands


class SimpleCommand(commands.Cog):
    """引数を持たないコマンド"""

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return ctx.message.content == ctx.prefix + ctx.invoked_with

    @commands.command()
    async def version(self, ctx):
        if not self.bot.is_normal_category(ctx) and not self.bot.is_auction_category(ctx):
            version = "6.0.3"
            embed = discord.Embed(description=f"現在のバージョンは**{version}**です\nNow version **{version}** working.", color=0x4259fb)
            await ctx.send(embed=embed)

    @commands.command()
    async def invite(self, ctx):
        if not self.bot.is_normal_category(ctx) and not self.bot.is_auction_category(ctx):
            await ctx.send(f"招待用URL:https://discord.gg/{os.environ['INVITE_CODE']}")


async def setup(bot):
    await bot.add_cog(SimpleCommand(bot))
