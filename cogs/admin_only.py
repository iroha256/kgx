import asyncio
import datetime
import os
import re
import traceback
from traceback import TracebackException

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
        if discord.utils.get(ctx.author.roles, name=os.environ["ADMIN_ROLE_NAME"]): #Administrator
            return True
        if discord.utils.get(ctx.author.roles, id=int(os.environ["UNNEI_ROLE_ID"])): #運営
            return True
        if discord.utils.get(ctx.author.roles, id=int(os.environ["DEV_ROLE_ID"])):  # developer
            return True
        await ctx.send('運営以外のコマンド使用は禁止です')
        return False

    @commands.command(name='del')
    async def _del(self, ctx, limit: int, channel: discord.TextChannel=None):  # メッセージ削除用
        if channel is None:
            channel = ctx.channel
        await ctx.message.delete()
        await channel.purge(limit=limit)

    @commands.command()
    async def check_all_user_ID(self, ctx):
        channel = self.bot.get_channel(int(os.environ["USER_ID_LIST_CHANNEL_ID"]))
        guild = self.bot.get_guild(int(os.environ["KGX_GUILD_ID"]))
        bot_count = 0
        for member in guild.members:
            if member.bot:
                bot_count += 1
                continue
            await channel.send(
                f"{member.id} : "
                f"{member.display_name}")
            if member == guild.members[-1]:
                embed = discord.Embed(
                    description=f"このサーバーの全メンバーのユーザーIDの照会が終わりました。 現在人数:{len(guild.members) - bot_count}",
                    color=0x1e90ff)
                await channel.send(embed=embed)
                await channel.send("--------ｷﾘﾄﾘ線--------")

    @commands.command()
    async def bidscore_ranking(self, ctx):
        await self.bot.update_bidscore_ranking()
        await asyncio.sleep(0.3)
        embed = discord.Embed(
            description=f"このサーバーの全メンバーの落札ポイントの照会が終わりました。"
                        f"\nランキングを出力しました。 ",
            color=0x1e90ff
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def show_bid_ranking(self, ctx):
        await self.bot.update_high_bid_ranking()
        await ctx.send("落札額ランキングを更新しました")

    @commands.command()
    async def stop_deal(self, ctx):
        # dbのリセット
        if os.environ["AUCTION_CATEGORY_PREFIX"] in ctx.channel.category.name:
            cur.execute("SELECT embed_message_id FROM auction where ch_id = %s", (ctx.channel.id,))
            embed_message_id, = cur.fetchone()
            if embed_message_id == 0:
                await ctx.send("このチャンネルではオークションが行われていません")
                return
            auction_embed = await ctx.channel.fetch_message(embed_message_id)
            await auction_embed.unpin()
            self.bot.reset_ch_db(ctx.channel.id, "a")

            try:
                kgx = self.bot.get_guild(int(os.environ["KGX_GUILD_ID"]))
                auction_data_channel = self.bot.get_channel(int(os.environ["AUCTION_LIST_CHANNEL_ID"]))
                await auction_data_channel.purge(limit=100)
                cur.execute("SELECT DISTINCT auction.ch_id, auction.auction_owner_id, auction.auction_item,"
                            "tend.tender_id, auction.unit, tend.tend_price, auction.auction_end_time FROM "
                            "(auction JOIN tend ON auction.ch_id = tend.ch_id)")
                sql_data = cur.fetchall()

                def active_filter(record):
                    """
                    開催していないオークションならFalse。ついでにdebugも消す
                    """
                    ch_id, owner_id = record[:2]
                    if ch_id == int(os.environ["AUCTION_DEBUG_CHANNEL_ID"]):
                        return False # 椎名debug
                    elif owner_id == 0:
                        return False # 開催していない
                    else:
                        return True

                AUCTION_TYPES = [os.environ["CURRENCY_TYPE_SHIINA"], os.environ["CURRENCY_TYPE_GACHA"], os.environ["CURRENCY_TYPE_ALL"], os.environ["CURRENCY_TYPE_DARK"]] # オークションの種類一覧
                def order_func(record):
                    """
                    チャンネル名に対応したタプルを返す
                    椎名1 → (0, 1)、椎名2 → (0, 2), ガチャ券1 → (1, 1)など
                    """
                    ch_id = record[0]
                    channel_name = self.bot.get_channel(ch_id).name

                    for type_order, type_name in enumerate(AUCTION_TYPES):
                        if type_name in channel_name: 
                            # 該当すればtype_orderを確定させる
                            break
                    else:
                        type_order = len(AUCTION_TYPES) # いずれにも該当しなければ他よりも大きい値にする
                    
                    ch_num = int(re.search(r"\d+", channel_name).group())
                    return (type_order, ch_num) # type_order,ch_numの順に比較される
                
                auctions = list(filter(active_filter, sql_data))
                auctions.sort(key=order_func)

                if not auctions:
                    embed = discord.Embed(description="オークションはまだ一つも行われていません！", color=0x59a5e3)
                    await auction_data_channel.send(embed=embed)

                else:
                    auction_info_list = []
                    for ch_id, owner_id, auction_item, tender_id, unit, tend_price, end_time in auctions:
                        auction_info = []
                        channel = self.bot.get_channel(ch_id)
                        owner = kgx.get_member(owner_id)

                        # 終了時刻までの残り時間を計算
                        end_time_datetime = datetime.datetime.strptime(end_time, "%Y/%m/%d-%H:%M")
                        end_time_unix = int(end_time_datetime.timestamp())

                        auction_info.append(f"{channel.mention}:")
                        try:
                            auction_info.append(f"出品者 → {owner.display_name}")
                        except AttributeError:
                            auction_info.append(f"出品者 → サーバを抜けました")
                        auction_info.append(f"商品名 → {auction_item}")
                        # 多分no bidで更新すると死ぬ気がするので分岐
                        if tender_id[-1] == 0:
                            auction_info.append("入札者はまだいません！")
                        else:
                            highest_tender = kgx.get_member(tender_id[-1])
                            try:
                                auction_info.append(f"最高額入札者 → {highest_tender.display_name}")
                            except AttributeError:
                                auction_info.append(f"最高額入札者 → サーバを抜けました")
                            auction_info.append(f"入札額 → {unit}{self.bot.stack_check_reverse(tend_price[-1])}")

                        auction_info.append(f"終了 → <t:{end_time_unix}:R>")

                        auction_info_list.append("\n".join(auction_info))

                    for description in self.bot.join_within_limit(auction_info_list, sep="\n\n--------\n\n"):
                        embed = discord.Embed(description=description, color=0x59a5e3)
                        await auction_data_channel.send(embed=embed)

            except Exception as e:
                orig_error = getattr(e, "original", e)
                error_msg = ''.join(traceback.TracebackException.from_exception(orig_error).format())
                error_message = f'```{error_msg}```'
                ch = self.bot.get_channel(int(os.environ["LOG_CHANNEL_ID"]))
                d = datetime.datetime.now()  # 現在時刻の取得
                time = d.strftime("%Y/%m/%d %H:%M:%S")
                embed = discord.Embed(title='Error_log', description=error_message, color=0xf04747)
                embed.set_footer(text=f'channel:on_check_time_loop\ntime:{time}\nuser:None')
                await ch.send(embed=embed)

        elif os.environ["DEAL_CATEGORY_PREFIX"] in ctx.channel.category.name:
            cur.execute("SELECT embed_message_id FROM deal where ch_id = %s", (ctx.channel.id,))
            embed_message_id, = cur.fetchone()
            if embed_message_id == 0:
                await ctx.send("このチャンネルでは取引が行われていません")
                return
            deal_embed = await ctx.channel.fetch_message(embed_message_id)
            await deal_embed.unpin()
            self.bot.reset_ch_db(ctx.channel.id, "d")

            try:
                kgx = self.bot.get_guild(int(os.environ["KGX_GUILD_ID"]))
                deal_data_channel = self.bot.get_channel(int(os.environ["DEAL_LIST_CHANNEL_ID"]))
                await deal_data_channel.purge(limit=100)
                cur.execute("SELECT ch_id, deal_owner_id, deal_item, deal_hope_price, deal_end_time, unit from deal")
                sql_data = cur.fetchall()

                def active_filter(record):
                    """
                    開催していない取引ならFalse。ついでにdebugも消す
                    """
                    ch_id, owner_id = record[:2]
                    if ch_id == int(os.environ["DEAL_DEBUG_CHANNEL_ID"]):
                        return False # 取引debug
                    elif owner_id == 0:
                        return False # 開催していない
                    else:
                        return True

                DEAL_TYPES = [os.environ["CURRENCY_TYPE_SHIINA"], os.environ["CURRENCY_TYPE_GACHA"], os.environ["CURRENCY_TYPE_ALL"]] # 取引の種類一覧
                def order_func(record):
                    """
                    チャンネル名に対応したタプルを返す
                    椎名1 → (0, 1)、椎名2 → (0, 2), ガチャ券1 → (1, 1)など
                    """
                    ch_id = record[0]
                    channel_name = self.bot.get_channel(ch_id).name

                    for type_order, type_name in enumerate(DEAL_TYPES):
                        if type_name in channel_name: 
                            # 該当すればtype_orderを確定させる
                            break
                    else:
                        type_order = len(DEAL_TYPES) # いずれにも該当しなければ他よりも大きい値にする
                    
                    ch_num = int(re.search(r"\d+", channel_name).group())
                    return (type_order, ch_num) # type_order,ch_numの順に比較される
                
                deals = list(filter(active_filter, sql_data))
                deals.sort(key=order_func)

                if not deals:
                    embed = discord.Embed(description="取引はまだ一つも行われていません！", color=0x59a5e3)
                    await deal_data_channel.send(embed=embed)

                else:
                    deal_info_list = []
                    for ch_id, owner_id, deal_item, hope_price, end_time, unit in deals:
                        deal_info = []
                        channel = self.bot.get_channel(ch_id)
                        owner = kgx.get_member(owner_id)

                        # 終了時刻までの残り時間を計算
                        end_time_datetime = datetime.datetime.strptime(end_time, "%Y/%m/%d-%H:%M")
                        end_time_unix = int(end_time_datetime.timestamp())

                        deal_info.append(f"{channel.mention}:")
                        try:
                            deal_info.append(f"出品者 → {owner.display_name}")
                        except AttributeError:
                            deal_info.append(f"出品者 → サーバを抜けました")
                        deal_info.append(f"商品名 → {deal_item}")
                        deal_info.append(f"希望価格 → {unit}{self.bot.stack_check_reverse(int(hope_price))}")

                        deal_info.append(f"終了 → <t:{end_time_unix}:R>")

                        deal_info_list.append("\n".join(deal_info))


                    for description in self.bot.join_within_limit(deal_info_list, sep="\n\n--------\n\n"):
                        embed = discord.Embed(description=description, color=0x59a5e3)
                        await deal_data_channel.send(embed=embed)

            except Exception as e:
                orig_error = getattr(e, "original", e)
                error_msg = ''.join(traceback.TracebackException.from_exception(orig_error).format())
                error_message = f'```{error_msg}```'
                ch = self.bot.get_channel(int(os.environ["LOG_CHANNEL_ID"]))
                d = datetime.datetime.now()  # 現在時刻の取得
                time = d.strftime("%Y/%m/%d %H:%M:%S")
                embed = discord.Embed(title='Error_log', description=error_message, color=0xf04747)
                embed.set_footer(text=f'channel:on_check_time_loop\ntime:{time}\nuser:None')
                await ch.send(embed=embed)

        else:
            await ctx.send("オークションチャンネルまたは取引チャンネルで実行してください")
            return

        embed = discord.Embed(
            description=f"{ctx.author.display_name}によりこのフローは停止させられました。",
            color=0xf04747
        )
        await ctx.channel.send(embed=embed)
        try:
            await asyncio.wait_for(ctx.channel.edit(name=f"{ctx.channel.name}{os.environ['NOT_HELD_SUFFIX']}"), timeout=3.0)
        except asyncio.TimeoutError:
            pass
        await ctx.channel.send('--------ｷﾘﾄﾘ線--------')

    @commands.command()
    async def star_delete(self, ctx):
        embed = discord.Embed(
            description=f"{ctx.author.display_name}により{os.environ['NOT_HELD_SUFFIX']}を強制的に取り外しました。",
            color=0xf04747
        )
        await ctx.channel.send(embed=embed)
        try:
            await asyncio.wait_for(ctx.channel.edit(name=ctx.channel.name.split(os.environ["NOT_HELD_SUFFIX"])[0]), timeout=3.0)
        except asyncio.TimeoutError:
            pass

    @commands.command(aliases=["es"])
    async def execute_sql(self, ctx, *, content):
        cur.execute(content)
        if not content.lower().startswith("select"):  # select以外だったらcommitしてreturn
            await ctx.send(f'SQL文`{content}`は正常に実行されました')
            return db.commit()

        data = cur.fetchall()

        result = []
        for row in data:
            result.append(", ".join(map(repr, row)))

        if len("\n".join(result)) <= 2000:
            embed = discord.Embed(title="SQL文の実行結果", description="\n".join(result))
            await ctx.send(embed=embed)
        else:
            react_list = ["\U000025c0\U0000fe0f", "\U000025b6\U0000fe0f"]

            page = 0
            max_page = (len(result)-1)//10+1 # 切り上げ除算
            embed = discord.Embed(title=f"SQL文の実行結果(1-10件目)",
                                  description="\n".join(result[:10]))
            msg = await ctx.send(embed=embed)

            for react in react_list:
                await msg.add_reaction(react)

            def check(reaction, user):
                if reaction.message.id != msg.id:
                    return 0
                elif ctx.author.bot or user != ctx.author:
                    return 0
                elif str(reaction.emoji) in react_list:
                    return reaction, user
                else:
                    return 0

            while not self.bot.is_closed():
                try:
                    reaction, user = await self.bot.wait_for("reaction_add", check=check, timeout=300)
                except asyncio.TimeoutError:
                    return await msg.clear_reactions()
                else:
                    emoji = str(reaction.emoji)
                    await msg.remove_reaction(emoji, user)
                    if emoji == react_list[0]:  # 戻るリアクションだったら
                        page -= 1
                    elif emoji == react_list[1]:  # 進むリアクションだったら
                        page += 1
                    page %= max_page # (0 <= page < max_page) を満たすように

                    start_index = page * 10
                    if len(result) < start_index + 10:
                        embed = discord.Embed(title=f"SQL文の実行結果({start_index+1}-{len(result)}件目)",
                                              description="\n".join(result[start_index:]))
                    else:
                        embed = discord.Embed(title=f"SQL文の実行結果({start_index+1}-{start_index+10}件目)",
                                              description="\n".join(result[start_index:start_index+10]))
                    await msg.edit(embed=embed)

    @execute_sql.error
    async def sql_error(self, ctx, error):
        tb_format = "".join(TracebackException.from_exception(error).format_exception_only())
        await ctx.send(f"```\n{tb_format}```")
        db.commit()

    @commands.group(invoke_without_command=True)
    async def warn(self, ctx):
        await ctx.send(f'{ctx.prefix}warn [add, get]')

    @warn.command()
    async def get(self, ctx, user: discord.Member):
        cur.execute("SELECT warn_level FROM user_data WHERE user_id = %s", (user.id,))
        caution_level, = cur.fetchone()
        await ctx.send(f"{user}の警告レベルは{caution_level}です")

    @warn.command()
    async def add(self, ctx, user: discord.Member, n: int):
        cur.execute("SELECT warn_level FROM user_data WHERE user_id = %s", (user.id,))
        before_caution_level, = cur.fetchone()
        after_caution_level = before_caution_level + n
        cur.execute("UPDATE user_data SET warn_level = %s WHERE user_id = %s", (after_caution_level, user.id))
        db.commit()
        await ctx.send(f'{user}に警告レベル{n}を付与し、合計{after_caution_level}になりました')
        if after_caution_level >= 3:
            embed = discord.Embed(
                title="BANの確認",
                description=f"{user}の警告Lvが{after_caution_level}になりました。BANしますか？\nはい(BANする): 👍\nいいえ(しない): 👎",
                color=0xff0000
            )
            embed.set_thumbnail(url=user.display_avatar)
            msg = await ctx.send(embed=embed)
            await msg.add_reaction("👍")
            await msg.add_reaction("👎")
            def check(reaction, user):
                return user == ctx.author and (str(reaction.emoji) == "👍" or str(reaction.emoji) == "👎")
            try:
                reaction, _ = await self.bot.wait_for("reaction_add", check=check, timeout=600)
            except asyncio.TimeoutError:
                await ctx.send("タイムアウトしました。")
                return
            else:
                if str(reaction.emoji) == "👎":
                    await ctx.send("キャンセルしました")
                    return
            await user.guild.ban(user, reason="警告Lv3")
            await ctx.send(f"{user}は警告Lvが3を超えたのでBANされました")

    @commands.group(invoke_without_command=True)
    async def bidGS(self, ctx):
        await ctx.send(f'{ctx.prefix}score [set, get]')

    @bidGS.command(name="get")
    async def _get(self, ctx, user: discord.Member):
        cur.execute("SELECT bid_score FROM user_data WHERE user_id = %s", (user.id,))
        bid_score, = cur.fetchone()
        await ctx.send(f"{user}の落札ポイントは{bid_score}です")

    @bidGS.command(name="set")
    async def _set(self, ctx, user: discord.Member, n: int):
        cur.execute("UPDATE user_data SET bid_score = %s WHERE user_id = %s", (n, user.id))
        db.commit()
        await ctx.send(f'{user.display_name}の落札ポイントを{n}にセットしました')

        await self.bot.update_bidscore_ranking()
        channel = self.bot.get_channel(int(os.environ["BID_SCORE_NOTIFICATION_CHANNEL_ID"]))
        embed = discord.Embed(
            description=f"{ctx.author.display_name}により、{user.display_name}"
                        f"の落札ポイントが{n}にセットされました。",
            color=0xf04747
        )
        await channel.send(embed=embed)

    @commands.command()
    async def dbsetup(self, ctx, set_type):
        if set_type == "a":
            cur.execute("INSERT INTO auction (ch_id) values (%s)", (ctx.channel.id,))
            cur.execute("INSERT INTO tend (ch_id) values (%s)", (ctx.channel.id,))
            db.commit()
            self.bot.reset_ch_db(ctx.channel.id, set_type)
            await ctx.send(f"{ctx.channel.name}をオークションチャンネルとしてデータベースに登録しました")
        elif set_type == "d":
            cur.execute("INSERT INTO deal (ch_id) values (%s)", (ctx.channel.id,))
            db.commit()
            self.bot.reset_ch_db(ctx.channel.id, set_type)
            await ctx.send(f"{ctx.channel.name}を取引チャンネルとしてデータベースに登録しました")
        else:
            await ctx.send(f"{ctx.prefix}dbsetup [a, d]")

    @commands.command()
    async def restart(self, ctx):
        await ctx.send("restarting ")
        await self.bot.close()

    @commands.command()
    async def kick(self, ctx, role: discord.Role):
        n = len(role.members)
        for mem in role.members:
            await mem.kick()

        await ctx.channel.send(f"{role.mention}持ちの{n}人を吹き飛ばしました")


async def setup(bot):
    await bot.add_cog(AdminOnly(bot))
