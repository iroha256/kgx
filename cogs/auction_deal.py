import asyncio
import io
import os
import re
import traceback
from datetime import datetime, timedelta

import discord
import psycopg2
import requests
from PIL import Image
from dateutil.relativedelta import relativedelta
from discord.ext import commands

SQLpath = os.environ["DATABASE_URL"]
db = psycopg2.connect(SQLpath)  # sqlに接続
cur = db.cursor()  # なんか操作する時に使うやつ

auction_notice_ch_id = 727333695450775613


class AuctionDael(commands.Cog):
    """オークション、取引に関するcog"""

    def is_admin(self, user):
        kgx_guild = self.bot.get_guild(558125111081697300)
        if user.guild != kgx_guild:
            return False
        admin_role = kgx_guild.get_role(558129132161073164)
        dev_role = kgx_guild.get_role(558138575225356308)
        return bool(set(user.roles) & {admin_role, dev_role})

    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["bs"])
    async def bidscore(self, ctx, pt: int):  # カウントしてその数字に対応する役職を付与する
        if ctx.channel.id not in (558265536430211083, 711682097928077322):
            return # 落札申請所またはbot-commandのみ使用可能

        channel = self.bot.get_channel(602197766218973185)
        p = re.compile(r'^[0-9]+$')
        if p.fullmatch(str(pt)):
            cur.execute("SELECT bid_score FROM user_data where user_id = %s", (ctx.author.id,))
            old_score, = cur.fetchone()
            new_score = old_score + pt
            cur.execute("UPDATE user_data SET bid_score = %s WHERE user_id = %s", (new_score, ctx.author.id))
            db.commit()

            if ctx.channel.id == 558265536430211083:
                embed = discord.Embed(description=f'**{ctx.author.display_name}**の現在の落札ポイントは**{new_score}**です。',
                                    color=0x9d9d9d)
                embed.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)  # ユーザー名+ID,アバターをセット
                await channel.send(embed=embed)

            before, after = await ctx.bot.update_bidscore_role(ctx.author, new_score)
            if before != after:  # beforeとafterで違うランクだったら
                if before is None:
                    before_name = "落札初心者"
                else:
                    before_name = before.name

                embed = discord.Embed(
                    description=f'**{ctx.author.display_name}**がランクアップ！``{before_name}⇒{after.name}``',
                    color=after.color)
                embed.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)  # ユーザー名+ID,アバターをセット
                await ctx.channel.send(embed=embed)

            embed = discord.Embed(description=f'**{ctx.author.display_name}**に落札ポイントを付与しました。', color=0x9d9d9d)
            embed.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)  # ユーザー名+ID,アバターをセット
            await ctx.channel.send(embed=embed)
            await asyncio.sleep(0.5)
            # ランキングを出力する
            await self.bot.update_bidscore_ranking()

    @commands.command()
    async def start(self, ctx):

        def check(m):
            """ユーザーの次のメッセージを待つ"""
            if m.author.bot:
                return
            return m.channel == ctx.channel and m.author == ctx.author

        abs_datetime_pattern = re.compile(r'(\d{1,4})/(\d{1,2})/(\d{1,2})-(\d{1,2}):(\d{1,2})')
        rel_datetime_pattern = re.compile(r'(?i)(?=.+)((\d+)(month|m))?((\d+(\.\d+)?)(week|w))?((\d+(\.\d+)?)(day|d))?((\d+(\.\d+)?)(hour|h))?((\d+(\.\d+)?)(minute|m))?')

        def is_exist_date(year, month, day):
            """
            存在しない月なら1、存在しない日なら2を返す
            """
            if month in (1, 3, 5, 7, 8, 10, 12):
                if not 1 <= day <= 31:
                    return 2
            elif month in (4, 6, 9, 11):
                if not 1 <= day <= 30:
                    return 2
            elif month == 2:
                if year % 400 == 0 or year % 4 == 0 and year % 100 != 0:  # 閏年なら
                    if not 1 <= day <= 29:
                        return 2
                else:
                    if not 1 <= day <= 28:
                        return 2
            else:
                return 1
            return 0

        # 2つ行ってる場合はreturn
        user = ctx.author.id
        if self.bot.get_user_auction_count(user) >= 2 and ctx.author.id != 251365193127297024:
            description = "貴方はすでに取引を2つ以上行っているためこれ以上取引を始められません。\n" \
                          "行っている取引が2つ未満になってから再度行ってください。"
            await ctx.channel.send(embed=discord.Embed(description=description, color=0xf04747))
            await ctx.channel.send("--------ｷﾘﾄﾘ線--------")
            return

        first_message_object = None
        # オークション系
        if self.bot.is_auction_category(ctx):

            # 既にオークションが行われていたらreturn
            if "☆" not in ctx.channel.name:
                description = "このチャンネルでは既にオークションが行われています。\n☆がついているチャンネルでオークションを始めてください。"
                await ctx.channel.send(embed=discord.Embed(description=description, color=0xf04747), delete_after=3)
                await asyncio.sleep(3)
                await ctx.message.delete()
                return

            # 単位の設定
            if self.bot.is_siina_category(ctx):
                unit = "椎名"
            elif self.bot.is_gacha_category(ctx):
                unit = "ガチャ券"
            else:
                embed = discord.Embed(description="何によるオークションですか？単位を入力してください。(ex.GTギフト券, がちゃりんご, エメラルド etc)",
                                      color=0xffaf60)
                first_message_object = await ctx.channel.send(embed=embed)
                try:
                    input_unit = await self.bot.wait_for('message', check=check, timeout=600.0)
                except asyncio.TimeoutError:
                    await ctx.send("10分間操作がなかったためキャンセルしました\n--------ｷﾘﾄﾘ線--------")
                    return
                unit = input_unit.content

            # ALLにおいて
            if "all" in ctx.channel.name.lower() and unit in ("椎名", "椎名林檎", "ガチャ券"):
                embed = discord.Embed(description="椎名、ガチャ券のオークションは専用のチャンネルで行ってください。",
                                      color=0xffaf60)
                await ctx.channel.send(embed=embed)
                return

            embed = discord.Embed(
                description="出品するものを入力してください。",
                color=0xffaf60)
            if first_message_object is not None:
                await ctx.channel.send(embed=embed)
            else:
                first_message_object = await ctx.channel.send(embed=embed)
            try:
                input_item = await self.bot.wait_for('message', check=check, timeout=600.0)
            except asyncio.TimeoutError:
                await ctx.send("10分間操作がなかったためキャンセルしました\n--------ｷﾘﾄﾘ線--------")
                return

            embed = discord.Embed(description="開始価格を入力してください。\n**※次のように入力してください。"
                                              "【〇LC+△ST+□】 or　【〇ST+△】 or 【△】 ex.1lc+1st+1 or 1st+1 or 32**\n"
                                              "終了したい場合は`cancel`と入力してください",
                                  color=0xffaf60)
            await ctx.channel.send(embed=embed)

            while not self.bot.is_closed():  # 正しい入力が来るまでwhile
                try:
                    user_start_price = await self.bot.wait_for('message', check=check, timeout=600.0)
                except asyncio.TimeoutError:
                    await ctx.send("10分間操作がなかったためキャンセルしました\n--------ｷﾘﾄﾘ線--------")
                    return
                start_price = self.bot.stack_check(user_start_price.content)
                if user_start_price.content.lower() == "cancel":
                    await ctx.send("キャンセルしました\n--------ｷﾘﾄﾘ線--------")
                    return
                if start_price is None:
                    await ctx.send("価格の形式が正しくありません\n**"
                                   "※次のように入力してください。【〇LC+△ST+□】 or　【〇ST+△】 or 【△】 ex.1lc+1st+1 or 1st+1 or 32**")
                elif start_price == 0:
                    await ctx.send("開始価格を0にすることはできません。入力しなおしてください。")
                else:  # 正しい入力ならbreak
                    break

            embed = discord.Embed(description="即決価格を入力してください。\n**※次のように入力してください。"
                                              "【〇LC+△ST+□】 or　【〇ST+△】 or 【△】 ex.1lc+1st+1 or 1st+1 or 32**\n"
                                              "ない場合は`なし`とお書きください。\n"
                                              "終了したい場合は`cancel`と入力してください",
                                  color=0xffaf60)
            await ctx.channel.send(embed=embed)

            while not self.bot.is_closed():
                try:
                    input_bin_price = await self.bot.wait_for('message', check=check, timeout=600.0)
                except asyncio.TimeoutError:
                    await ctx.send("10分間操作がなかったためキャンセルしました\n--------ｷﾘﾄﾘ線--------")
                    return
                if input_bin_price.content.lower() == "cancel":
                    await ctx.send("キャンセルしました\n--------ｷﾘﾄﾘ線--------")
                    return
                if input_bin_price.content == "なし":
                    bin_price = "なし"
                    break
                bin_price = self.bot.stack_check(input_bin_price.content)
                if bin_price is None:
                    await ctx.send("価格の形式が正しくありません\n**"
                                   "※次のように入力してください。【〇LC+△ST+□】 or　【〇ST+△】 or 【△】 ex.1lc+1st+1 or 1st+1 or 32**")
                elif bin_price < start_price:
                    await ctx.send("即決価格が開始価格より低いです。入力しなおしてください。")
                elif bin_price == start_price:
                    await ctx.send("即決価格が開始価格と等しいです。入力しなおしてください。\n価格が決まっているのであれば、取引チャンネルをお使いください。")
                else:
                    break

            embed = discord.Embed(
                description="オークション終了日時を入力してください。\n**注意！**時間の書式に注意してください！\n\n"
                            f"例 {datetime.now().year}年5月14日の午後8時に終了したい場合：\n**{datetime.now().year}/05/14-20:00**と入力してください。\n\n"
                            "例 1カ月2週間3日4時間5分後に終了したい場合:\n**1M2w3d4h5m**と入力してください。\n\n"
                            "終了したい場合は**cancel**と入力してください",
                color=0xffaf60)
            await ctx.channel.send(embed=embed)

            now = datetime.now()  # 都度生成するとタイムラグが生じてしまうため、あらかじめ取得した値を使いまわす
            while not self.bot.is_closed():
                try:
                    input_end_time = await self.bot.wait_for('message', check=check, timeout=600.0)
                except asyncio.TimeoutError:
                    await ctx.send("10分間操作がなかったためキャンセルしました\n--------ｷﾘﾄﾘ線--------")
                    return
                if input_end_time.content.lower() == "cancel":
                    await ctx.send("キャンセルしました\n--------ｷﾘﾄﾘ線--------")
                    return

                if abs_datetime_pattern.fullmatch(input_end_time.content):  # 絶対時刻の書式の場合
                    year, month, day, hour, minute = map(int, abs_datetime_pattern.fullmatch(input_end_time.content).groups())

                    if not 2000 <= year <= 3000:
                        await ctx.send("年は2000~3000の範囲のみ指定可能です。入力しなおしてください。")
                        continue
                    if is_exist_date(year, month, day) == 1:
                        await ctx.send(f"{month}月は存在しません。入力しなおしてください。")
                        continue
                    if is_exist_date(year, month, day) == 2:
                        await ctx.send(f"{year}年{month}月に{day}日は存在しません。入力しなおしてください。")
                        continue

                    if (hour, minute) == (24, 00):
                        end_time = datetime(year, month, day) + timedelta(days=1)
                    elif hour not in range(24) or minute not in range(60):
                        await ctx.send(f"{hour}時{minute}分は存在しません。入力しなおしてください。")
                        continue
                    else:
                        end_time = datetime(year, month, day, hour, minute)

                elif rel_datetime_pattern.fullmatch(input_end_time.content):  # 相対時刻の書式の場合
                    """
                    入力が"1m1.5w"の場合のマッチオブジェクトに対してMatch.groups()した場合は('1m', '1', 'm', '1.5w', '1.5', '.5', 'w',…)となるため、
                    (0-indexedで)6番目が単位、4番目が数値となる
                    ただし、monthの部分は小数を受け付けないため、別で処理をする
                    """
                    groups = rel_datetime_pattern.fullmatch(input_end_time.content).groups()
                    week_u, day_u, hour_u, minute_u = groups[6::4]  # 単位部分
                    week_n, day_n, hour_n, minute_n = groups[4::4]  # 数値部分
                    month_u, month_n = groups[2], groups[1]

                    if month_u == "m" and not any((week_u, day_u, hour_u, minute_u)):
                        # month_uが"m"、かつweek~minuteが指定されていないとき ("1m"のような入力)
                        minute_u, minute_n = month_u, month_n  # monthの内容をminuteに移動する
                        month_u = None  # monthを指定されていないことにする

                    end_time = now
                    if month_u:
                        end_time += relativedelta(months=int(month_n))
                    # month以外の各単位について、単位部分がNoneでなければend_timeに加算
                    if week_u:
                        end_time += timedelta(weeks=float(week_n))
                    if day_u:
                        end_time += timedelta(days=float(day_n))
                    if hour_u:
                        end_time += timedelta(hours=float(hour_n))
                    if minute_u:
                        end_time += timedelta(minutes=float(minute_n))

                    year, month, day, hour, minute = end_time.year, end_time.month, end_time.day, end_time.hour, end_time.minute  # 表示用に属性を展開しておく

                else:  # 正しくない入力の場合
                    await ctx.send("時間の書式が正しくありません\n\n"
                                   f"例 {datetime.now().year}年5月14日の午後8時に終了したい場合：\n**{datetime.now().year}/05/14-20:00**と入力してください。\n\n"
                                   "例 1カ月2週間3日4時間5分後に終了したい場合:\n**1M2w3d4h5m**と入力してください。\n\n"
                                   "終了したい場合は**cancel**と入力してください")
                    continue

                if end_time <= now:
                    await ctx.channel.send("終了時刻を現在時刻以前にすることはできません。入力しなおしてください。")
                    continue
                elif end_time - now <= timedelta(hours=12):
                    await ctx.send("開催期間を12時間以下にすることはできません。入力しなおしてください。")
                    continue
                elif end_time - now >= timedelta(weeks=8):
                    await ctx.channel.send("2ヶ月以上にわたるオークションはできません。入力しなおしてください。")
                    continue
                break
            end_time_sql = end_time.strftime('%Y/%m/%d-%H:%M')
            end_time_text = f"{year}/{month:0>2}/{day:0>2}-{hour:0>2}:{minute:0>2}"  # 24:00の場合はそのまま表示

            embed = discord.Embed(
                description="その他、即決特典などありましたらお書きください。\n長い場合、改行などをして**１回の送信**で書いてください。\n"
                            "何も無ければ「なし」で構いません。",
                color=0xffaf60)
            await ctx.channel.send(embed=embed)
            try:
                input_notice = await self.bot.wait_for('message', check=check, timeout=600.0)
            except asyncio.TimeoutError:
                await ctx.send("10分間操作がなかったためキャンセルしました\n--------ｷﾘﾄﾘ線--------")
                return

            display_start_price = f"{unit}{self.bot.stack_check_reverse(start_price)}"
            # 即決価格なしなら単位は付与しない
            if bin_price == "なし":
                display_bin_price = "なし"
            else:
                display_bin_price = f"{unit}{self.bot.stack_check_reverse(bin_price)}"

            embed = discord.Embed(title="これで始めます。よろしいですか？YES/NOで答えてください。(小文字でもOK。NOの場合初めからやり直してください。)",
                                  color=0xffaf60)
            embed.add_field(name="出品者", value=f'{ctx.author.display_name}', inline=True)
            embed.add_field(name="出品物", value=f'{input_item.content}', inline=True)
            embed.add_field(name="開始価格", value=f'{display_start_price}', inline=False)

            embed.add_field(name="即決価格", value=f'{display_bin_price}', inline=False)
            embed.add_field(name="終了日時", value=f'{end_time_text}', inline=True)
            embed.add_field(name="特記事項", value=f'{input_notice.content}', inline=True)
            await ctx.channel.send(embed=embed)
            try:
                input_confirm = await self.bot.wait_for('message', check=check, timeout=600.0)
            except asyncio.TimeoutError:
                await ctx.send("10分間操作がなかったためキャンセルしました\n--------ｷﾘﾄﾘ線--------")
                return

            if input_confirm.content.lower() in ("yes", "いぇｓ", "いぇs"):
                await ctx.channel.purge(limit=3)
                await asyncio.sleep(0.3)
                embed = discord.Embed(title="オークション内容", color=0xffaf60)
                embed.add_field(name="出品者", value=f'{ctx.author.display_name}', inline=True)
                embed.add_field(name="出品物", value=f'{input_item.content}', inline=True)
                embed.add_field(name="開始価格", value=f'{display_start_price}', inline=False)
                embed.add_field(name="即決価格", value=f'{display_bin_price}', inline=False)
                embed.add_field(name="終了日時", value=f'{end_time_text}', inline=True)
                embed.add_field(name="特記事項", value=f'{input_notice.content}', inline=True)
                await ctx.channel.send("<:siina:558251559394213888>オークションを開始します<:siina:558251559394213888>")
                auction_embed = await ctx.channel.send(embed=embed)
                await auction_embed.pin()

                # SQLにデータ登録
                cur.execute("UPDATE auction SET auction_owner_id = %s, embed_message_id = %s, auction_item = %s, "
                            "auction_start_price = %s, auction_bin_price = %s, auction_end_time = %s, "
                            "unit = %s, notice = %s WHERE ch_id = %s",
                            (ctx.author.id, auction_embed.id, input_item.content, str(start_price),
                             str(bin_price), end_time_sql, unit, input_notice.content, ctx.channel.id))
                db.commit()

                try:
                    kgx = self.bot.get_guild(558125111081697300)
                    auction_data_channel = self.bot.get_channel(771034285352026162)
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
                        if ch_id == 747728655735586876:
                            return False # 椎名debug
                        elif owner_id == 0:
                            return False # 開催していない
                        else:
                            return True

                    AUCTION_TYPES = ["椎名", "ガチャ券", "all", "闇取引"] # オークションの種類一覧
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

                    if not auctions: #returnされると☆が付かなくなるがたぶんこれが発火することはないので無視する
                        embed = discord.Embed(description="オークションはまだ一つも行われていません！", color=0x59a5e3)
                        await auction_data_channel.send(embed=embed)
                        return

                    auction_info_list = []
                    for ch_id, owner_id, auction_item, tender_id, unit, tend_price, end_time in auctions:
                        auction_info = []
                        channel = self.bot.get_channel(ch_id)
                        owner = kgx.get_member(owner_id)

                        # 終了時刻までの残り時間を計算
                        end_time_datetime = datetime.strptime(end_time, "%Y/%m/%d-%H:%M")
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
                    ch = self.bot.get_channel(628807266753183754)
                    d = datetime.datetime.now()  # 現在時刻の取得
                    time = d.strftime("%Y/%m/%d %H:%M:%S")
                    embed = discord.Embed(title='Error_log', description=error_message, color=0xf04747)
                    embed.set_footer(text=f'channel:on_check_time_loop\ntime:{time}\nuser:None')
                    await ch.send(embed=embed)

                try:
                    await asyncio.wait_for(ctx.channel.edit(name=ctx.channel.name.split('☆')[0]), timeout=3.0)
                except asyncio.TimeoutError:
                    pass

            else:
                await ctx.channel.purge(limit=2)
                await ctx.channel.send("初めからやり直してください。\n--------ｷﾘﾄﾘ線--------")

        # 通常取引について
        elif self.bot.is_normal_category(ctx):

            # 既に取引が行われていたらreturn
            if "☆" not in ctx.channel.name:
                description = "このチャンネルでは既に取引が行われています。\n☆がついているチャンネルで取引を始めてください。"
                await ctx.channel.send(embed=discord.Embed(description=description, color=0xf04747))
                await asyncio.sleep(3)
                await ctx.channel.purge(limit=2)
                return

            # 単位の設定
            if self.bot.is_siina_category(ctx):
                unit = "椎名"
            elif self.bot.is_gacha_category(ctx):
                unit = "ガチャ券"
            else:
                embed = discord.Embed(description="何による取引ですか？単位を入力してください。(ex.GTギフト券, がちゃりんご, エメラルド etc)",
                                      color=0xffaf60)
                first_message_object = await ctx.channel.send(embed=embed)
                try:
                    input_unit = await self.bot.wait_for('message', check=check, timeout=600.0)
                except asyncio.TimeoutError:
                    await ctx.send("10分間操作がなかったためキャンセルしました\n--------ｷﾘﾄﾘ線--------")
                    return
                unit = input_unit.content

            # ALLにおいて
            if "all" in ctx.channel.name.lower() and unit in ("椎名", "椎名林檎", "ガチャ券"):
                await ctx.channel.purge(limit=2)
                embed = discord.Embed(description="椎名、ガチャ券の取引は専用のチャンネルで行ってください。",
                                      color=0xffaf60)
                await ctx.channel.send(embed=embed)
                await ctx.channel.send("--------ｷﾘﾄﾘ線--------")
                return

            embed = discord.Embed(
                description="出品するものを入力してください。",
                color=0xffaf60)
            if first_message_object is not None:
                await ctx.channel.send(embed=embed)
            else:
                first_message_object = await ctx.channel.send(embed=embed)
            try:
                input_item = await self.bot.wait_for('message', check=check, timeout=600.0)
            except asyncio.TimeoutError:
                await ctx.send("10分間操作がなかったためキャンセルしました\n--------ｷﾘﾄﾘ線--------")
                return

            embed = discord.Embed(description="希望価格を入力してください。\n**※次のように入力してください。"
                                              "【〇LC+△ST+□】 or　【〇ST+△】 or 【△】 ex.1lc+1st+1 or 1st+1 or 32**\n"
                                              "終了したい場合は`cancel`と入力してください",
                                  color=0xffaf60)
            await ctx.channel.send(embed=embed)
            while not self.bot.is_closed():
                try:
                    input_hope_price = await self.bot.wait_for('message', check=check, timeout=600.0)
                except asyncio.TimeoutError:
                    await ctx.send("10分間操作がなかったためキャンセルしました\n--------ｷﾘﾄﾘ線--------")
                    return
                if input_hope_price.content.lower() == "cancel":
                    await ctx.send("キャンセルしました\n--------ｷﾘﾄﾘ線--------")
                    return
                hope_price = self.bot.stack_check(input_hope_price.content)
                if hope_price is None:
                    await ctx.send("価格の形式が正しくありません\n**"
                                   "※次のように入力してください。【〇LC+△ST+□】 or　【〇ST+△】 or 【△】 ex.1lc+1st+1 or 1st+1 or 32**")
                elif hope_price == 0:
                    await ctx.send("希望価格を0にすることはできません。入力しなおしてください。")
                else:
                    break

            embed = discord.Embed(
                description="取引終了日時を入力してください。\n**注意！**時間の書式に注意してください！\n\n"
                            f"例　5月14日の午後8時に終了したい場合：\n**{datetime.now().year}/05/14-20:00**と入力してください。\n\n"
                            "例 1カ月2週間3日4時間5分後に終了したい場合:\n**1M2w3d4h5m**と入力してください。\n\n"
                            "終了したい場合は**cancel**と入力してください",
                color=0xffaf60)
            await ctx.channel.send(embed=embed)

            now = datetime.now()  # 都度生成するとタイムラグが生じてしまうため、あらかじめ取得した値を使いまわす
            while not self.bot.is_closed():
                try:
                    input_end_time = await self.bot.wait_for('message', check=check, timeout=600.0)
                except asyncio.TimeoutError:
                    await ctx.send("10分間操作がなかったためキャンセルしました\n--------ｷﾘﾄﾘ線--------")
                    return
                if input_end_time.content.lower() == "cancel":
                    await ctx.send("キャンセルしました\n--------ｷﾘﾄﾘ線--------")
                    return

                if abs_datetime_pattern.fullmatch(input_end_time.content):  # 絶対時刻の書式の場合
                    year, month, day, hour, minute = map(int, abs_datetime_pattern.fullmatch(input_end_time.content).groups())

                    if not 2000 <= year <= 3000:
                        await ctx.send("年は2000~3000の範囲のみ指定可能です。入力しなおしてください。")
                        continue
                    if is_exist_date(year, month, day) == 1:
                        await ctx.send(f"{month}月は存在しません。入力しなおしてください。")
                        continue
                    if is_exist_date(year, month, day) == 2:
                        await ctx.send(f"{year}年{month}月に{day}日は存在しません。入力しなおしてください。")
                        continue

                    if (hour, minute) == (24, 00):
                        end_time = datetime(year, month, day) + timedelta(days=1)
                    elif hour not in range(24) or minute not in range(60):
                        await ctx.send(f"{hour}時{minute}分は存在しません。入力しなおしてください。")
                        continue
                    else:
                        end_time = datetime(year, month, day, hour, minute)

                elif rel_datetime_pattern.fullmatch(input_end_time.content):  # 相対時刻の書式の場合
                    """
                    入力が"1m1.5w"の場合のマッチオブジェクトに対してMatch.groups()した場合は('1m', '1', 'm', '1.5w', '1.5', '.5', 'w',…)となるため、
                    (0-indexedで)6番目が単位、4番目が数値となる
                    ただし、monthの部分は小数を受け付けないため、別で処理をする
                    """
                    groups = rel_datetime_pattern.fullmatch(input_end_time.content).groups()
                    week_u, day_u, hour_u, minute_u = groups[6::4]  # 単位部分
                    week_n, day_n, hour_n, minute_n = groups[4::4]  # 数値部分
                    month_u, month_n = groups[2], groups[1]

                    if month_u == "m" and not any((week_u, day_u, hour_u, minute_u)):
                        # month_uが"m"、かつweek~minuteが指定されていないとき ("1m"のような入力)
                        minute_u, minute_n = month_u, month_n  # monthの内容をminuteに移動する
                        month_u = None  # monthを指定されていないことにする

                    end_time = now
                    if month_u:
                        end_time += relativedelta(months=int(month_n))
                    # month以外の各単位について、単位部分がNoneでなければend_timeに加算
                    if week_u:
                        end_time += timedelta(weeks=float(week_n))
                    if day_u:
                        end_time += timedelta(days=float(day_n))
                    if hour_u:
                        end_time += timedelta(hours=float(hour_n))
                    if minute_u:
                        end_time += timedelta(minutes=float(minute_n))

                    year, month, day, hour, minute = end_time.year, end_time.month, end_time.day, end_time.hour, end_time.minute  # 表示用に属性を展開しておく

                else:  # 正しくない入力の場合
                    await ctx.send("時間の書式が正しくありません\n\n"
                                   f"例 {datetime.now().year}年5月14日の午後8時に終了したい場合：\n**{datetime.now().year}/05/14-20:00**と入力してください。\n\n"
                                   "例 1カ月2週間3日4時間5分後に終了したい場合:\n**1M2w3d4h5m**と入力してください。\n\n"
                                   "終了したい場合は**cancel**と入力してください")
                    continue

                if end_time <= now:
                    await ctx.channel.send("終了時刻を現在時刻以前にすることはできません。入力しなおしてください。")
                    continue
                elif end_time - now <= timedelta(hours=12):
                    await ctx.send("開催期間を12時間以下にすることはできません。入力しなおしてください。")
                    continue
                elif end_time - now >= timedelta(weeks=8):
                    await ctx.channel.send("2ヶ月以上にわたる取引はできません。入力しなおしてください。")
                    continue
                break
            end_time_sql = end_time.strftime('%Y/%m/%d-%H:%M')
            end_time_text = f"{year}/{month:0>2}/{day:0>2}-{hour:0>2}:{minute:0>2}"  # 24:00の場合はそのまま表示

            embed = discord.Embed(
                description="その他、出品物の詳細等などありましたらお書きください。\n長い場合、改行などをして**１回の送信**で書いてください。\n"
                            "何も無ければ「なし」で構いません。",
                color=0xffaf60)
            await ctx.channel.send(embed=embed)
            try:
                input_notice = await self.bot.wait_for('message', check=check, timeout=600.0)
            except asyncio.TimeoutError:
                await ctx.send("10分間操作がなかったためキャンセルしました\n--------ｷﾘﾄﾘ線--------")
                return

            display_hope_price = f"{unit}{self.bot.stack_check_reverse(hope_price)}"

            embed = discord.Embed(title="これで始めます。よろしいですか？YES/NOで答えてください。(小文字でもOK。NOの場合初めからやり直してください。)",
                                  color=0xffaf60)
            embed.add_field(name="出品者", value=f'{ctx.author.display_name}', inline=True)
            embed.add_field(name="出品物", value=f'{input_item.content}', inline=False)
            embed.add_field(name="希望価格", value=f'{display_hope_price}', inline=True)
            embed.add_field(name="終了日時", value=f'{end_time_text}', inline=True)
            embed.add_field(name="特記事項", value=f'{input_notice.content}', inline=False)
            await ctx.channel.send(embed=embed)

            try:
                input_confirm = await self.bot.wait_for('message', check=check, timeout=600.0)
            except asyncio.TimeoutError:
                await ctx.send("10分間操作がなかったためキャンセルしました\n--------ｷﾘﾄﾘ線--------")
                return
            if input_confirm.content.lower() in ("yes", "いぇｓ", "いぇs"):
                await ctx.channel.purge(limit=3)
                await asyncio.sleep(0.3)
                embed = discord.Embed(title="取引内容", color=0xffaf60)
                embed.add_field(name="出品者", value=f'{ctx.author.display_name}', inline=True)
                embed.add_field(name="出品物", value=f'{input_item.content}', inline=False)
                embed.add_field(name="希望価格", value=f'{display_hope_price}', inline=True)
                embed.add_field(name="終了日時", value=f'{end_time_text}', inline=True)
                embed.add_field(name="特記事項", value=f'{input_notice.content}', inline=False)
                await ctx.channel.send(
                    "<:shiina_balance:558175954686705664>取引を開始します<:shiina_balance:558175954686705664>")
                deal_embed = await ctx.channel.send(embed=embed)
                await deal_embed.pin()

                cur.execute("UPDATE deal SET deal_owner_id = %s, embed_message_id = %s, deal_item = %s, "
                            "deal_hope_price = %s, deal_end_time = %s, unit = %s, notice = %s WHERE ch_id = %s",
                            (ctx.author.id, deal_embed.id, input_item.content, str(hope_price),
                             end_time_sql, unit, input_notice.content, ctx.channel.id))
                db.commit()

                try:
                    kgx = self.bot.get_guild(558125111081697300)
                    deal_data_channel = self.bot.get_channel(771068489627861002)
                    await deal_data_channel.purge(limit=100)
                    cur.execute("SELECT ch_id, deal_owner_id, deal_item, deal_hope_price, deal_end_time, unit from deal")
                    sql_data = cur.fetchall()

                    def active_filter(record):
                        """
                        開催していない取引ならFalse。ついでにdebugも消す
                        """
                        ch_id, owner_id = record[:2]
                        if ch_id == 858158727576027146:
                            return False # 取引debug
                        elif owner_id == 0:
                            return False # 開催していない
                        else:
                            return True

                    DEAL_TYPES = ["椎名", "ガチャ券", "all"] # 取引の種類一覧
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

                    if not deals: #returnされると☆が付かなくなるがたぶんこれが発火することはないので無視する
                        embed = discord.Embed(description="取引はまだ一つも行われていません！", color=0x59a5e3)
                        await deal_data_channel.send(embed=embed)
                        return

                    deal_info_list = []
                    for ch_id, owner_id, deal_item, hope_price, end_time, unit in deals:
                        deal_info = []
                        channel = self.bot.get_channel(ch_id)
                        owner = kgx.get_member(owner_id)

                        # 終了時刻までの残り時間を計算
                        end_time_datetime = datetime.strptime(end_time, "%Y/%m/%d-%H:%M")
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
                    ch = self.bot.get_channel(628807266753183754)
                    d = datetime.datetime.now()  # 現在時刻の取得
                    time = d.strftime("%Y/%m/%d %H:%M:%S")
                    embed = discord.Embed(title='Error_log', description=error_message, color=0xf04747)
                    embed.set_footer(text=f'channel:on_check_time_loop\ntime:{time}\nuser:None')
                    await ch.send(embed=embed)

                try:
                    await asyncio.wait_for(ctx.channel.edit(name=ctx.channel.name.split('☆')[0]), timeout=3.0)
                except asyncio.TimeoutError:
                    pass

            else:
                await ctx.channel.purge(limit=2)
                await ctx.channel.send("初めからやり直してください。\n--------ｷﾘﾄﾘ線--------")

    @commands.command(aliases=["Tend"])
    @commands.cooldown(1, 1, type=commands.BucketType.channel)
    async def tend(self, ctx, price: str):
        if not self.bot.is_auction_category(ctx):
            embed = discord.Embed(description="このコマンドはオークションでのみ使用可能です。", color=0x4259fb)
            await ctx.send(embed=embed)
            return

        # そもそもオークションが開催してなかったらreturn
        if '☆' in ctx.channel.name:
            embed = discord.Embed(
                description=f'{ctx.author.display_name}さん。このチャンネルではオークションは行われていません',
                color=0xff0000)
            await ctx.channel.send(embed=embed)
            return

        price = self.bot.stack_check(price)

        if price is not None or price == 0:
            # 開始価格、即決価格、現在の入札額を取り寄せ
            # auction[0] - auction[7]が各種auctionDBのデータとなる
            cur.execute("SELECT * FROM auction where ch_id = %s", (ctx.channel.id,))
            auction = cur.fetchone()
            cur.execute("SELECT * FROM tend where ch_id = %s", (ctx.channel.id,))
            tend_data = cur.fetchone()

            # ARRAYから最新の入札状況を引き抜く。初期状態は0
            tend = [tend_data[0], tend_data[1], tend_data[2]]

            # 条件に1つでも合致していたらreturn
            # 入札人物の判定
            try:
                if ctx.author.id == auction[1]:
                    embed = discord.Embed(description="出品者が入札は出来ません。", color=0x4259fb)
                    await ctx.send(embed=embed)
                    return

                elif ctx.author.id == tend[1][-1] and not price >= int(auction[5]):
                    embed = discord.Embed(description="同一人物による入札は出来ません。", color=0x4259fb)
                    await ctx.send(embed=embed)
                    return
            except ValueError:  # 629行目にて、int(auction[5])で、即決価格が「なし」の場合、これがValueErrorを出す。とりあえず握りつぶす
                pass

            # 入札価格の判定
            if price < int(auction[4]) or price <= int(tend[2][-1]):
                embed = discord.Embed(description="入札価格が現在の入札価格、もしくは開始価格より低いです。", color=0x4259fb)
                await ctx.send(embed=embed)
                return

            elif auction[5] != "なし":
                if price >= int(auction[5]):
                    embed = discord.Embed(description=f"即決価格と同額以上の価格が入札されました。{ctx.author.display_name}さんの落札です。",
                                          color=0x4259fb)
                    await ctx.send(embed=embed)

                    ctx.bot.insert_auction_info(ctx.channel.id)

                    # オークション情報を取る
                    cur.execute(f"SELECT * FROM auction where ch_id = {ctx.channel.id}")
                    auction_data = cur.fetchone()
                    tend_price = f"{auction_data[7]}{self.bot.stack_check_reverse(price)}"

                    if ctx.channel.id != 747728655735586876: # 椎名debug以外
                        embed = discord.Embed(title="オークション取引結果", color=0x36a64f)
                        embed.add_field(name="落札日", value=f'\n\n{datetime.now().strftime("%Y/%m/%d")}', inline=False)
                        embed.add_field(name="出品者", value=f'\n\n{self.bot.get_user(auction_data[1]).display_name}',
                                        inline=False)
                        embed.add_field(name="品物", value=f'\n\n{auction_data[3]}', inline=False)
                        embed.add_field(name="落札者", value=f'\n\n{ctx.author.display_name}', inline=False)
                        embed.add_field(name="落札価格", value=f'\n\n{tend_price}', inline=False)
                        embed.add_field(name="チャンネル名", value=f'\n\n{ctx.channel.name}', inline=False)
                        await self.bot.get_channel(558132754953273355).send(embed=embed)
                        # オークションが終わったらその結果を通知
                    description = f"{ctx.channel.name}にて行われていた{self.bot.get_user(auction_data[1]).display_name}による 品物名: **{auction_data[3]}** のオークションは\n{ctx.author.display_name}により" \
                                  f"**{tend_price}**にて落札されました"
                    embed = discord.Embed(description=description, color=0xffaf60)
                    time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                    embed.set_footer(text=f'channel:{ctx.channel.name}\nTime:{time}')
                    await self.bot.dm_send(auction[1], embed)
                    await self.bot.dm_send(ctx.author.id, embed)

                    # ランキング送信
                    if "椎名" in ctx.channel.name and ctx.channel.id != 747728655735586876: # 椎名debug以外
                        # INSERTを実行。%sで後ろのタプルがそのまま代入される
                        cur.execute("INSERT INTO bid_ranking VALUES (%s, %s, %s, %s)",
                                    (ctx.author.display_name, auction_data[3], price,
                                     self.bot.get_user(auction_data[1]).display_name))
                        db.commit()
                        await self.bot.update_high_bid_ranking()

                    embed = discord.Embed(description="オークションを終了しました", color=0xffaf60)
                    await ctx.channel.send(embed=embed)

                    auction_embed = await ctx.channel.fetch_message(auction[2])
                    await auction_embed.unpin()

                    # chのdbを消し去る。これをもってその人のオークション開催回数を減らしたことになる
                    self.bot.reset_ch_db(ctx.channel.id, "a")
                    await ctx.channel.send('--------ｷﾘﾄﾘ線--------')
                    await asyncio.sleep(0.3)
                    try:
                        await asyncio.wait_for(ctx.channel.edit(name=f"{ctx.channel.name}☆"), timeout=3.0)
                    except asyncio.TimeoutError:
                        pass

                    try:
                        kgx = self.bot.get_guild(558125111081697300)
                        auction_data_channel = self.bot.get_channel(771034285352026162)
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
                            if ch_id == 747728655735586876:
                                return False # 椎名debug
                            elif owner_id == 0:
                                return False # 開催していない
                            else:
                                return True

                        AUCTION_TYPES = ["椎名", "ガチャ券", "all", "闇取引"] # オークションの種類一覧
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
                                end_time_datetime = datetime.strptime(end_time, "%Y/%m/%d-%H:%M")
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
                        ch = self.bot.get_channel(628807266753183754)
                        d = datetime.datetime.now()  # 現在時刻の取得
                        time = d.strftime("%Y/%m/%d %H:%M:%S")
                        embed = discord.Embed(title='Error_log', description=error_message, color=0xf04747)
                        embed.set_footer(text=f'channel:on_check_time_loop\ntime:{time}\nuser:None')
                        await ch.send(embed=embed)

                    return

            elif price == 0 or price is None:
                embed = discord.Embed(description="不正な値です。", color=0x4259fb)
                await ctx.send(embed=embed)
                return

            # 入札時間の判定
            time = datetime.now() + timedelta(hours=1)
            finish_time = datetime.strptime(auction[6], r"%Y/%m/%d-%H:%M")
            flag = False

            if time > finish_time:
                embed = discord.Embed(description="終了1時間前以内の入札です。終了時刻を1日延長します。", color=0x4259fb)
                await ctx.send(embed=embed)
                await asyncio.sleep(2)

                embed = discord.Embed(title="オークション内容", color=0xffaf60)
                embed.add_field(name="出品者", value=f'\n\n{self.bot.get_user(auction[1]).display_name}')
                embed.add_field(name="出品物", value=f'\n\n{auction[3]}')
                value = "なし" if auction[5] == "なし" else f"{auction[7]}{self.bot.stack_check_reverse(int(auction[5]))}"
                embed.add_field(name="開始価格", value=f'\n\n{auction[7]}{self.bot.stack_check_reverse(int(auction[4]))}',
                                inline=False)
                embed.add_field(name="即決価格", value=f'\n\n{value}', inline=False)
                finish_time = (finish_time + timedelta(days=1)).strftime("%Y/%m/%d-%H:%M")
                embed.add_field(name="終了日時", value=f'\n\n{finish_time}')
                embed.add_field(name="特記事項", value=f'\n\n{auction[8]}')
                msg = await ctx.channel.fetch_message(auction[2])
                await msg.edit(embed=embed)  # メッセージの更新で対応する
                # 変更点をUPDATE
                cur.execute("UPDATE auction SET embed_message_id = %s, auction_end_time = %s WHERE ch_id = %s",
                            (msg.id, finish_time, ctx.channel.id))
                db.commit()

                # 延長をオークション主催者に伝える
                flag = True

            # オークション情報が変わってる可能性があるのでここで再度auctionのデータを取る
            cur.execute("SELECT * FROM auction where ch_id = %s", (ctx.channel.id,))
            auction = cur.fetchone()

            # チャンネルid, 入札者idのlist, 入札額のリストが入っている
            tend_data = [tend_data[0], list(tend_data[1]), list(tend_data[2])]

            updated_tend_data = tend_data.copy()
            updated_tend_data[1].append(ctx.author.id)
            updated_tend_data[2].append(self.bot.stack_check(price))

            updated_tend_data[1] = self.bot.list_to_tuple_string(updated_tend_data[1])
            updated_tend_data[2] = self.bot.list_to_tuple_string(updated_tend_data[2])

            cur.execute(
                f"UPDATE tend SET tender_id = '{updated_tend_data[1]}', tend_price = '{updated_tend_data[2]}' WHERE ch_id = %s",
                (ctx.channel.id,))
            db.commit()
            await ctx.message.delete()  # !tendのメッセージを削除する
            await asyncio.sleep(0.1)

            if flag:  # 終了時間が延長される場合は通知する
                text = f"チャンネル名: {self.bot.get_channel(auction[0]).name}において終了1時間前に入札があったため終了時刻を1日延長します。"
                embed = discord.Embed(description=text, color=0x4259fb)
                time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                embed.set_footer(text=f'channel:{ctx.channel.name}\nTime:{time}')
                await self.bot.dm_send(auction[1], embed)

            time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            cur.execute(f"SELECT * FROM user_data where user_id = {ctx.author.id}")
            sql_data = cur.fetchone()
            player_head_avatarurl = f"https://cravatar.eu/helmhead/{sql_data[3][0]}"  # uuidのカラムがなーぜかlistで保管されているため[0]で取り出し
            image = requests.get(player_head_avatarurl)
            image = io.BytesIO(image.content)
            image.seek(0)
            image = Image.open(image)
            image = image.resize((100, 100))
            image.save("./icon.png")
            image = discord.File("./icon.png", filename="icon.png")
            embed = discord.Embed(description=f"入札者: **{ctx.author.display_name}**, \n"
                                              f"入札額: **{auction[7]}{self.bot.stack_check_reverse(self.bot.stack_check(price))}**\n",
                                  color=0x4259fb)
            embed.set_image(url="attachment://icon.png")
            embed.set_footer(text=f"入札時刻: {time}")
            await ctx.send(file=image, embed=embed)

            # 一つ前のtenderにDMする。ただし存在を確認してから。[0,なにか](初回tend)は送信しない(before_tender==0)
            # 今までの状態だと初回IndexErrorが発生するので順番を前に持ってきました
            if len(tend[1]) == 1:  # 初回の入札(tend_data=[0]の状態)は弾く
                return

            before_tender_id = int(tend[1][-1])

            text = f"チャンネル名: {ctx.channel.name}において貴方より高い入札がされました。\n" \
                   f"入札者: {ctx.author.display_name}, 入札額: **{auction[7]}{self.bot.stack_check_reverse(self.bot.stack_check(price))}**\n"
            embed = discord.Embed(description=text, color=0x4259fb)
            time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            embed.set_footer(text=f'channel:{ctx.channel.name}\nTime:{time}')

            await self.bot.dm_send(before_tender_id, embed)

            try:
                kgx = self.bot.get_guild(558125111081697300)
                deal_data_channel = self.bot.get_channel(771068489627861002)
                await deal_data_channel.purge(limit=100)
                cur.execute("SELECT ch_id, deal_owner_id, deal_item, deal_hope_price, deal_end_time, unit from deal")
                sql_data = cur.fetchall()

                def active_filter(record):
                    """
                    開催していない取引ならFalse。ついでにdebugも消す
                    """
                    ch_id, owner_id = record[:2]
                    if ch_id == 858158727576027146:
                        return False # 取引debug
                    elif owner_id == 0:
                        return False # 開催していない
                    else:
                        return True

                DEAL_TYPES = ["椎名", "ガチャ券", "all"] # 取引の種類一覧
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

                if not deals: #returnされると☆が付かなくなるがたぶんこれが発火することはないので無視する
                    embed = discord.Embed(description="取引はまだ一つも行われていません！", color=0x59a5e3)
                    await deal_data_channel.send(embed=embed)
                    return

                deal_info_list = []
                for ch_id, owner_id, deal_item, hope_price, end_time, unit in deals:
                    deal_info = []
                    channel = self.bot.get_channel(ch_id)
                    owner = kgx.get_member(owner_id)

                    # 終了時刻までの残り時間を計算
                    end_time_datetime = datetime.strptime(end_time, "%Y/%m/%d-%H:%M")
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
                ch = self.bot.get_channel(628807266753183754)
                d = datetime.datetime.now()  # 現在時刻の取得
                time = d.strftime("%Y/%m/%d %H:%M:%S")
                embed = discord.Embed(title='Error_log', description=error_message, color=0xf04747)
                embed.set_footer(text=f'channel:on_check_time_loop\ntime:{time}\nuser:None')
                await ch.send(embed=embed)

        else:
            embed = discord.Embed(description=f"{ctx.author.display_name}さん。入力した値が不正です。もう一度正しく入力を行ってください。",
                                  color=0x4259fb)
            await ctx.send(embed=embed)

    @commands.command()
    @commands.cooldown(1, 1, type=commands.BucketType.channel)
    async def add(self, ctx: commands.Context, add_price: str):
        if not self.bot.is_auction_category(ctx):
            embed = discord.Embed(description="このコマンドはオークションでのみ使用可能です。", color=0x4259fb)
            await ctx.send(embed=embed)
            return
        cur.execute("SELECT * FROM tend where ch_id = %s", (ctx.channel.id,))
        tend_data = cur.fetchone()
        tend_data = [tend_data[0], list(tend_data[1]), list(tend_data[2])]

        if tend_data[1][-1] == 0:
            embed = discord.Embed(description="入札がなにもありません。最初の入札はtendコマンドで行ってください。", color=0x4259fb)
            await ctx.send(embed=embed)
            return

        add_price = self.bot.stack_check(add_price)
        if add_price is None or add_price <= 0:
            await ctx.send("入力値が不正です。")
            return

        price = tend_data[2][-1] + add_price
        tend = self.bot.get_command("tend")
        await ctx.invoke(tend, price=str(price))

    @commands.command()
    async def remand(self, ctx):
        if self.bot.is_auction_category(ctx):

            cur.execute("SELECT auction_owner_id, unit FROM auction where ch_id = %s", (ctx.channel.id,))
            auction_owner_id, unit = cur.fetchone()

            # オークションが行われていなければ警告して終了
            if "☆" in ctx.channel.name:
                embed = discord.Embed(description="このコマンドはオークション開催中のみ使用可能です。", color=0x4259fb)
                await ctx.send(embed=embed)
                return
            # オークション主催者じゃなければ警告して終了
            elif ctx.author.id != auction_owner_id:
                embed = discord.Embed(description="このコマンドはオークション主催者のみ使用可能です。", color=0x4259fb)
                await ctx.send(embed=embed)
                return

            cur.execute("select tender_id, tend_price from tend where ch_id = %s", (ctx.channel.id,))
            tenders_id, tend_prices = cur.fetchone()

            if tenders_id[-1] == 0:
                await ctx.send("入札がありません")
                return

            tenders_id.pop()
            tend_prices.pop()

            cur.execute(
                "UPDATE tend SET tender_id = %s, tend_price = %s WHERE ch_id = %s",
                (tenders_id, tend_prices, ctx.channel.id))
            db.commit()

            last_tender_id = tenders_id[-1]

            if last_tender_id == 0:
                embed = discord.Embed(
                    description="最初の入札が取り消されたため、現在入札はありません。",
                    color=0x4259fb
                )
                image = None
            else:
                # 退出したユーザーのときはNoneになり、getattrの第三引数がlast_tender_nameになる
                last_tender_name = getattr(self.bot.get_user(last_tender_id), "display_name", "退出したユーザー")
                embed = discord.Embed(
                    description=f"入札者: **{last_tender_name}**, \n"
                                f"入札額: **{unit}{self.bot.stack_check_reverse(tend_prices[-1])}**\n",
                    color=0x4259fb
                )
            
                cur.execute(f"SELECT uuid FROM user_data where user_id = %s", (last_tender_id,))
                uuid_list, = cur.fetchone()
                player_head_avatarurl = f"https://cravatar.eu/helmhead/{uuid_list[0]}"  # uuidのカラムがなーぜかlistで保管されているため[0]で取り出し
                image = requests.get(player_head_avatarurl)
                image = io.BytesIO(image.content)
                image.seek(0)
                image = Image.open(image)
                image = image.resize((100, 100))
                image.save("./icon.png")
                image = discord.File("./icon.png", filename="icon.png")
                embed.set_image(url="attachment://icon.png")
            
            time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            embed.set_footer(text=f"入札時刻: {time}")
            await ctx.channel.send(file=image, embed=embed)

            try:
                kgx = self.bot.get_guild(558125111081697300)
                auction_data_channel = self.bot.get_channel(771034285352026162)
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
                    if ch_id == 747728655735586876:
                        return False # 椎名debug
                    elif owner_id == 0:
                        return False # 開催していない
                    else:
                        return True

                AUCTION_TYPES = ["椎名", "ガチャ券", "all", "闇取引"] # オークションの種類一覧
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

                if not auctions: #returnされると☆が付かなくなるがたぶんこれが発火することはないので無視する
                    embed = discord.Embed(description="オークションはまだ一つも行われていません！", color=0x59a5e3)
                    await auction_data_channel.send(embed=embed)
                    return

                auction_info_list = []
                for ch_id, owner_id, auction_item, tender_id, unit, tend_price, end_time in auctions:
                    auction_info = []
                    channel = self.bot.get_channel(ch_id)
                    owner = kgx.get_member(owner_id)

                    # 終了時刻までの残り時間を計算
                    end_time_datetime = datetime.strptime(end_time, "%Y/%m/%d-%H:%M")
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
                ch = self.bot.get_channel(628807266753183754)
                d = datetime.datetime.now()  # 現在時刻の取得
                time = d.strftime("%Y/%m/%d %H:%M:%S")
                embed = discord.Embed(title='Error_log', description=error_message, color=0xf04747)
                embed.set_footer(text=f'channel:on_check_time_loop\ntime:{time}\nuser:None')
                await ch.send(embed=embed)

        else:
            embed = discord.Embed(description="このコマンドはオークションでのみ使用可能です。", color=0x4259fb)
            await ctx.send(embed=embed)
    
    @commands.command(aliases=["ar"])
    async def auction_rollback(self, ctx):
        cur.execute("SELECT auction_owner_id, before_auction FROM auction WHERE ch_id = %s", (ctx.channel.id,))
        database_data = cur.fetchall()

        if not database_data:
            embed = discord.Embed(description="このコマンドはオークションチャンネルでのみ使用可能です。", color=0x4259fb)
            await ctx.send(embed=embed)
            return
        
        (now_owner, before_auction,), = database_data

        if now_owner != 0:
            await ctx.send("このチャンネルでは既にオークションが行われています。")
            return

        if before_auction is None:
            await ctx.send("前回のオークションデータがありません")
            return
        
        cur.execute("SELECT owner_id, item, start_price, bin_price, end_time, unit, notice, tend FROM auction_info where id = %s", (before_auction,))
        owner_id, item, start_price, bin_price, end_time, unit, notice, tend = cur.fetchone()
        
        now = datetime.now()
        if end_time <= now:
            await ctx.send("オークションの終了時刻を過ぎています")
            return
        
        if ctx.author.id != owner_id and not self.is_admin(ctx.author):
            await ctx.send("オークション開催者、運営、開発者以外がオークションの復元を行うことはできません")
            return

        bin_price = "なし" if bin_price is None else bin_price
        end_time_text = end_time.strftime("%Y/%m/%d-%H:%M:%S")
        end_time_sql = end_time.strftime("%Y/%m/%d-%H:%M")

        display_start_price = f"{unit}{self.bot.stack_check_reverse(start_price)}"
        # 即決価格なしなら単位は付与しない
        if bin_price == "なし":
            display_bin_price = "なし"
        else:
            display_bin_price = f"{unit}{self.bot.stack_check_reverse(bin_price)}"

        embed = discord.Embed(title="これで始めます。よろしいですか？YES/NOで答えてください。(小文字でもOK。NOの場合初めからやり直してください。)",
                                color=0xffaf60)
        embed.add_field(name="出品者", value=f'{ctx.author.display_name}', inline=True)
        embed.add_field(name="出品物", value=f'{item}', inline=True)
        embed.add_field(name="開始価格", value=f'{display_start_price}', inline=False)

        embed.add_field(name="即決価格", value=f'{display_bin_price}', inline=False)
        embed.add_field(name="終了日時", value=f'{end_time_text}', inline=True)
        embed.add_field(name="特記事項", value=f'{notice}', inline=True)
        await ctx.channel.send(embed=embed)
        try:
            input_confirm = await self.bot.wait_for('message', check=lambda msg: (msg.author, msg.channel)==(ctx.author, ctx.channel), timeout=600.0)
        except asyncio.TimeoutError:
            await ctx.send("10分間操作がなかったためキャンセルしました\n--------ｷﾘﾄﾘ線--------")
            return

        if input_confirm.content.lower() in ("yes", "いぇｓ", "いぇs"):
            await ctx.channel.purge(limit=3)
            await asyncio.sleep(0.3)
            embed = discord.Embed(title="オークション内容", color=0xffaf60)
            embed.add_field(name="出品者", value=f'{ctx.author.display_name}', inline=True)
            embed.add_field(name="出品物", value=f'{item}', inline=True)
            embed.add_field(name="開始価格", value=f'{display_start_price}', inline=False)
            embed.add_field(name="即決価格", value=f'{display_bin_price}', inline=False)
            embed.add_field(name="終了日時", value=f'{end_time_text}', inline=True)
            embed.add_field(name="特記事項", value=f'{notice}', inline=True)
            await ctx.channel.send("<:siina:558251559394213888>オークションを開始します<:siina:558251559394213888>")
            auction_embed = await ctx.channel.send(embed=embed)
            await auction_embed.pin()

            # DBにデータ登録
            cur.execute("UPDATE auction SET auction_owner_id = %s, embed_message_id = %s, auction_item = %s, "
                        "auction_start_price = %s, auction_bin_price = %s, auction_end_time = %s, "
                        "unit = %s, notice = %s WHERE ch_id = %s",
                        (ctx.author.id, auction_embed.id, item, str(start_price),
                            str(bin_price), end_time_sql, unit, notice, ctx.channel.id))
            
            while tend and tend[-1][1] >= bin_price:
                tend.pop() # 即決価格以上の入札を消す
            tender_id, tend_price = map(list, zip(*([[0, 0]]+tend)))
            cur.execute("UPDATE tend SET tender_id = %s, tend_price = %s WHERE ch_id = %s", (tender_id, tend_price, ctx.channel.id))
            db.commit()

            await ctx.channel.edit(name=ctx.channel.name.split('☆')[0])

            if tend:
                # 入札があったら履歴を表示
                await ctx.invoke(self.bot.get_command("tend_history"))

        else:
            await ctx.channel.send("キャンセルしました\n--------ｷﾘﾄﾘ線--------")



    @commands.command()
    @commands.cooldown(1, 1, type=commands.BucketType.channel)
    async def consent(self, ctx):
        if not self.bot.is_normal_category(ctx):
            return

        if '☆' in ctx.channel.name:
            embed = discord.Embed(
                description=f'{ctx.author.display_name}さん。このチャンネルでは取引は行われていません',
                color=0xff0000)
            await ctx.channel.send(embed=embed)
            return

        # chのdbを消し去る
        cur.execute("SELECT * from deal WHERE ch_id = %s", (ctx.channel.id,))
        dael_data = cur.fetchone()
        owner = self.bot.get_user(int(dael_data[1]))
        try:
            await owner.send(f"{ctx.author.display_name}が{ctx.channel.mention}の取引を承諾しました")
        except discord.errors.Forbidden: #DM着信拒否
            await ctx.send(f"{owner.mention}\n{ctx.author.display_name}が{ctx.channel.mention}の取引を承諾しました")

        deal_embed = await ctx.channel.fetch_message(dael_data[2])
        await deal_embed.unpin()

        self.bot.reset_ch_db(ctx.channel.id, "d")

        await ctx.channel.send('--------ｷﾘﾄﾘ線--------')

        try:
            kgx = self.bot.get_guild(558125111081697300)
            deal_data_channel = self.bot.get_channel(771068489627861002)
            await deal_data_channel.purge(limit=100)
            cur.execute("SELECT ch_id, deal_owner_id, deal_item, deal_hope_price, deal_end_time, unit from deal")
            sql_data = cur.fetchall()

            def active_filter(record):
                """
                開催していない取引ならFalse。ついでにdebugも消す
                """
                ch_id, owner_id = record[:2]
                if ch_id == 858158727576027146:
                    return False # 取引debug
                elif owner_id == 0:
                    return False # 開催していない
                else:
                    return True

            DEAL_TYPES = ["椎名", "ガチャ券", "all"] # 取引の種類一覧
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

            if not deals: #returnされると☆が付かなくなるがたぶんこれが発火することはないので無視する
                embed = discord.Embed(description="取引はまだ一つも行われていません！", color=0x59a5e3)
                await deal_data_channel.send(embed=embed)
                return

            deal_info_list = []
            for ch_id, owner_id, deal_item, hope_price, end_time, unit in deals:
                deal_info = []
                channel = self.bot.get_channel(ch_id)
                owner = kgx.get_member(owner_id)

                # 終了時刻までの残り時間を計算
                end_time_datetime = datetime.strptime(end_time, "%Y/%m/%d-%H:%M")
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
            ch = self.bot.get_channel(628807266753183754)
            d = datetime.datetime.now()  # 現在時刻の取得
            time = d.strftime("%Y/%m/%d %H:%M:%S")
            embed = discord.Embed(title='Error_log', description=error_message, color=0xf04747)
            embed.set_footer(text=f'channel:on_check_time_loop\ntime:{time}\nuser:None')
            await ch.send(embed=embed)

        try:
            await asyncio.wait_for(ctx.channel.edit(name=f"{ctx.channel.name}☆"), timeout=3.0)
        except asyncio.TimeoutError:
            pass

    @commands.command()
    async def tend_history(self, ctx):
        cur.execute("SELECT auction_owner_id, unit FROM auction where ch_id = %s", (ctx.channel.id,))
        auction_owner_id, unit = cur.fetchone()

        # オークションが行われていなければ警告して終了
        if "☆" in ctx.channel.name:
            embed = discord.Embed(description="このコマンドはオークション開催中のみ使用可能です。", color=0x4259fb)
            await ctx.send(embed=embed)
            return
        else:
            cur.execute("select tender_id, tend_price from tend where ch_id = %s", (ctx.channel.id,))
            tenders_id, tend_prices = cur.fetchone()

            if len(tenders_id) == 1:
                await ctx.send("入札者はまだいません")
                return

            tend_info_list = []

            for i, (tenders_id, tend_price) in enumerate(zip(tenders_id[1:], tend_prices[1:]), 1):
                tend_info_list.append(f"{i}: {self.bot.get_guild(558125111081697300).get_member(tenders_id).display_name}, {unit}{self.bot.stack_check_reverse(tend_price)}")

            await ctx.channel.send(embed=discord.Embed(title="現在の入札状況", description="\n\n".join(tend_info_list), color=0xffaf60))


async def setup(bot):
    await bot.add_cog(AuctionDael(bot))
