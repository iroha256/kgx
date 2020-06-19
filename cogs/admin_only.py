import asyncio
import os
import re

import discord
import psycopg2
from discord.ext import commands

SQLpath = os.environ["DATABASE_URL"]
db = psycopg2.connect(SQLpath)  # sqlに接続
cur = db.cursor()  # なんか操作する時に使うやつ


class AdminOnly(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):  # cog内のコマンド全てに適用されるcheck
        if discord.utils.get(ctx.author.roles, name="Administrator"):
            return True
        await ctx.send('運営以外のコマンド使用は禁止です')

    @commands.command(name='del')
    async def _del(self, ctx, n):  # メッセージ削除用
        p = re.compile(r'^[0-9]+$')
        if p.fullmatch(n):
            kazu = int(n)
            await ctx.channel.purge(limit=kazu + 1)

    @commands.command()
    async def check_all_user_ID(self, ctx):
        channel = self.bot.get_channel(642052474672250880)
        bot_count = 0
        for member in range(self.bot.get_guild(558125111081697300).member_count):
            if self.bot.get_guild(558125111081697300).members[member].bot:
                bot_count += 1
                continue
            await channel.send(
                f"{self.bot.get_guild(558125111081697300).members[member].id} : "
                f"{self.bot.get_guild(558125111081697300).members[member].display_name}")
            if member == (self.bot.get_guild(558125111081697300).member_count - 1):
                embed = discord.Embed(
                    description=f"このサーバーの全メンバーのユーザーIDの照会が終わりました。 現在人数:{member - bot_count + 1}",
                    color=0x1e90ff)
                await channel.send(embed=embed)
                await channel.send("--------ｷﾘﾄﾘ線--------")

    @commands.command()
    async def bidscore_ranking(self, ctx):
        channel = self.bot.get_channel(677905288665235475)
        # とりあえず、ランキングチャンネルの中身を消す
        await channel.purge(limit=1)
        await channel.send(embed=self.bot.create_ranking_embed())
        await asyncio.sleep(0.3)
        embed = discord.Embed(
            description=f"このサーバーの全メンバーの落札ポイントの照会が終わりました。"
                        f"\nランキングを出力しました。 ",
            color=0x1e90ff
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def show_bid_ranking(self, ctx):
        await self.bot.get_channel(705040893593387039).purge(limit=10)
        await asyncio.sleep(0.1)
        embed = self.bot.create_high_bid_ranking()
        for i in range(len(embed)):
            await self.bot.get_channel(705040893593387039).send(embed=embed[i])

    @commands.command()
    async def stop_deal(self, ctx):
        embed = discord.Embed(
            description=f"{ctx.author.display_name}によりこの取引は停止させられました。",
            color=0xf04747
        )
        await ctx.channel.send(embed=embed)
        await ctx.channel.edit(name=ctx.channel.name + '☆')
        await ctx.channel.send('--------ｷﾘﾄﾘ線--------')

    @commands.command()
    async def star_delete(self, ctx):
        embed = discord.Embed(
            description=f"{ctx.author.display_name}により☆を強制的に取り外しました。",
            color=0xf04747
        )
        await ctx.channel.send(embed=embed)
        await ctx.channel.edit(name=ctx.channel.name.split('☆')[0])

    @commands.command()
    async def execute_sql(self, ctx, *, content):
        cur.execute(content)
        data = cur.fetchone()
        if len(data) == 0:
            return await ctx.send(f'SQL文`{content}`は正常に実行されました')
        embed = discord.Embed(title="SQL文の実行結果", description=''.join(f"{d}、" for d in data))
        await ctx.send(embed=embed)

    @commands.command()
    async def delete_to(self, ctx):
        if not ctx.channel.id == 722768808321876068:
            return
        delete_ch = ctx.channel
        msg = await delete_ch.fetch_message(722768855021256706)
        await delete_ch.purge(limit=None, after=msg)

    @commands.group(invoke_without_command=True)
    async def user_caution(self, ctx):
        await ctx.send(f'{ctx.prefix}user_caution [set, get]')

    @user_caution.command(name="get")
    async def _get(self, ctx, user: discord.Member):
        cur.execute("SELECT warn_level FROM user_data WHERE user_id = %s", (user.id,))
        data = cur.fetchone()
        caution_level = data[0]
        await ctx.send(f"{user}の警告レベルは{caution_level}です")

    @user_caution.command()
    async def set(self, ctx, user: discord.Member, n: int):
        cur.execute("UPDATE user_data SET warn_level = %s WHERE user_id = %s", (n, user.id))
        db.commit()
        await ctx.send(f'{user}に警告レベル{n}を付与しました')

    @commands.group(invoke_without_command=True)
    async def bidGS(self, ctx):
        await ctx.send(f'{ctx.prefix}score [set, get]')

    @bidGS.command(name="get")
    async def _get(self, ctx, user: discord.Member):
        cur.execute("SELECT bid_score FROM user_data WHERE user_id = %s", (user.id,))
        data = cur.fetchone()
        await ctx.send(f"{user}の落札ポイントは{data[0]}です")

    @bidGS.command()
    async def set(self, ctx, user: discord.Member, n: int):
        cur.execute("UPDATE user_data SET bid_score = %s WHERE user_id = %s", (n, user.id))
        db.commit()
        await ctx.send(f'{user.display_name}の落札ポイントを{n}にセットしました')

        channel = self.bot.get_channel(677905288665235475)
        # とりあえず、ランキングチャンネルの中身を消す
        await channel.purge(limit=1)
        await channel.send(embed=self.bot.create_ranking_embed())
        channel = self.bot.get_channel(602197766218973185)
        embed = discord.Embed(
            description=f"{ctx.author.display_name}により、{user.display_name}"
                        f"の落札ポイントが{n}にセットされました。",
            color=0xf04747
        )
        await channel.send(embed=embed)

    @commands.command()
    async def test(self, ctx, user_id):
        for i in self.bot.walk_commands():
            await ctx.send(f"{i}")


def setup(bot):
    bot.add_cog(AdminOnly(bot))
