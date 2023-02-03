import asyncio
import traceback
from discord.ext import commands, tasks
import discord
import psycopg2
import os
import datetime

SQLpath = os.environ["DATABASE_URL"]
db = psycopg2.connect(SQLpath)  # sqlに接続
cur = db.cursor()  # なんか操作する時に使うやつ


class CheckEndTime(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_time.start()

    @tasks.loop(minutes=1)
    async def check_time(self):
        try:
            await self.bot.wait_until_ready()
            now = datetime.datetime.now()
            kgx = self.bot.get_guild(558125111081697300)
            log_ch = self.bot.get_channel(558132754953273355)

            # オークションについて
            cur.execute("SELECT ch_id, auction_owner_id, embed_message_id, auction_item, auction_end_time, unit from auction;")
            auction_data = cur.fetchall()
            for ch_id, auction_owner_id, embed_message_id, item, auction_end_time, unit in auction_data:
                if auction_end_time == "undefined":
                    continue
                if datetime.datetime.strptime(auction_end_time, "%Y/%m/%d-%H:%M") <= now:
                    ch = self.bot.get_channel(ch_id)
                    owner = kgx.get_member(auction_owner_id)

                    self.bot.insert_auction_info(ch_id)

                    cur.execute("SELECT tender_id, tend_price from tend WHERE ch_id=%s;", (ch.id,))
                    tenders_id, tend_prices = cur.fetchone()
                    tender = kgx.get_member(tenders_id[-1])
                    price = self.bot.stack_check_reverse(tend_prices[-1])
                    if tend_prices[-1] == 0:
                        # 入札者なしという事
                        embed = discord.Embed(description=f"{ch.name}のオークションは入札者が誰もいなかったので終了します")
                        time = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                        embed.set_footer(text=f'channel:{ch.name}\nTime:{time}')
                        await self.bot.dm_send(auction_owner_id, embed)
                        embed = discord.Embed(description="オークションを終了しました", color=0xffaf60)
                        await ch.send(embed=embed)

                        deal_embed = await ch.fetch_message(embed_message_id)
                        await deal_embed.unpin()

                        # chのdbを消し去る。これをもってその人のオークション開催回数を減らしたことになる
                        self.bot.reset_ch_db(ch.id, "a")
                        await ch.send('--------ｷﾘﾄﾘ線--------')
                        await asyncio.sleep(0.3)
                        try:
                            await asyncio.wait_for(ch.edit(name=f"{ch.name}☆"), timeout=3.0)
                        except asyncio.TimeoutError:
                            continue
                        continue

                    tend_price = f"{unit}{price}"

                    if ch.id != 747728655735586876: # 椎名debug以外
                        embed = discord.Embed(title="オークション取引結果", color=0x36a64f)
                        embed.add_field(name="落札日", value=f'\n\n{now.strftime("%Y/%m/%d")}', inline=False)
                        embed.add_field(name="出品者", value=f'\n\n{owner.display_name}', inline=False)
                        embed.add_field(name="品物", value=f'\n\n{item}', inline=False)
                        embed.add_field(name="落札者", value=f'\n\n{tender.display_name}', inline=False)
                        embed.add_field(name="落札価格", value=f'\n\n{tend_price}', inline=False)
                        embed.add_field(name="チャンネル名", value=f'\n\n{ch.name}', inline=False)
                        await log_ch.send(embed=embed)

                    # オークションが終わったらその結果を主催者と落札者に通知
                    description = f"{ch.name}にて行われていた{owner.display_name}による 品物名: **{item}** のオークションは\n{tender.display_name}により" \
                                  f"**{tend_price}**にて落札されました"
                    embed = discord.Embed(description=description, color=0xffaf60)
                    time = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                    embed.set_footer(text=f'channel:{ch.name}\nTime:{time}')
                    await self.bot.dm_send(auction_owner_id, embed)
                    await self.bot.dm_send(tenders_id[-1], embed)

                    # ランキング送信
                    if "椎名" in ch.name and ch.id != 747728655735586876: # 椎名debug以外
                        # INSERTを実行。%sで後ろのタプルがそのまま代入される
                        cur.execute("INSERT INTO bid_ranking VALUES (%s, %s, %s, %s)",
                                    (tender.display_name, item, tend_prices[-1], owner.display_name))
                        db.commit()
                        await self.bot.update_high_bid_ranking()

                    embed = discord.Embed(description=f"{owner.display_name}が出品した{item}を{tender.display_name}が{tend_price}で落札しました！", color=0xffaf60)
                    await ch.send(embed=embed)

                    auction_embed = await ch.fetch_message(embed_message_id)
                    await auction_embed.unpin()

                    # chのdbを消し去る。これをもってその人のオークション開催回数を減らしたことになる
                    self.bot.reset_ch_db(ch.id, "a")
                    await ch.send('--------ｷﾘﾄﾘ線--------')

                    try:
                        kgx = self.bot.get_guild(558125111081697300)
                        auction_data_channel = self.bot.get_channel(id=771034285352026162)
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
                            channel_name = self.bot.get_channel(id=ch_id).name

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

                    await asyncio.sleep(0.3)
                    try:
                        await asyncio.wait_for(ch.edit(name=f"{ch.name}☆"), timeout=3.0)
                    except asyncio.TimeoutError:
                        continue
                await asyncio.sleep(1)

            # 取引について
            cur.execute("SELECT ch_id, deal_owner_id, embed_message_id, deal_end_time from deal;")
            deal_data = cur.fetchall()
            for ch_id, deal_owner_id, embed_message_id, deal_end_time in deal_data:
                if deal_end_time == "undefined":
                    continue
                if datetime.datetime.strptime(deal_end_time, "%Y/%m/%d-%H:%M") <= now:
                    ch = self.bot.get_channel(id=ch_id)
                    embed = discord.Embed(description=f"{ch.name}の取引は不成立でしたので終了します")
                    time = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                    embed.set_footer(text=f'channel:{ch.name}\nTime:{time}')
                    await self.bot.dm_send(deal_owner_id, embed)
                    embed = discord.Embed(description="取引が終了しました", color=0xffaf60)
                    await ch.send(embed=embed)

                    deal_embed = await ch.fetch_message(embed_message_id)
                    await deal_embed.unpin()

                    # chのdbを消し去る。これをもってその人のオークション開催回数を減らしたことになる
                    self.bot.reset_ch_db(ch_id, "d")
                    await ch.send('--------ｷﾘﾄﾘ線--------')

                    try:
                        kgx = self.bot.get_guild(558125111081697300)
                        deal_data_channel = self.bot.get_channel(id=771068489627861002)
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
                            channel_name = self.bot.get_channel(id=ch_id).name

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

                    await asyncio.sleep(0.3)
                    try:
                        await asyncio.wait_for(ch.edit(name=f"{ch.name}☆"), timeout=3.0)
                    except asyncio.TimeoutError:
                        continue

        except Exception as e:
            if isinstance(e, psycopg2.InterfaceError):
                await self.bot.close()

            orig_error = getattr(e, "original", e)
            error_msg = ''.join(traceback.TracebackException.from_exception(orig_error).format())
            error_message = f'```{error_msg}```'
            ch = self.bot.get_channel(628807266753183754)
            d = datetime.datetime.now()  # 現在時刻の取得
            time = d.strftime("%Y/%m/%d %H:%M:%S")
            embed = discord.Embed(title='Error_log', description=error_message, color=0xf04747)
            embed.set_footer(text=f'channel:on_check_time_loop\ntime:{time}\nuser:None')
            await ch.send(embed=embed)


def setup(bot):
    bot.add_cog(CheckEndTime(bot))
