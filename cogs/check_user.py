import asyncio
import datetime
import os
import traceback

import discord
import psycopg2
from discord.ext import commands, tasks

SQLpath = os.environ["DATABASE_URL"]
db = psycopg2.connect(SQLpath)  # sqlに接続
cur = db.cursor()  # なんか操作する時に使うやつ

"""開催されているオークション、取引の主がいなくなった時close."""


class CheckUser(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_user.start()

    @tasks.loop(minutes=1)
    async def check_user(self):
        try:
            await self.bot.wait_until_ready()
            kgx = self.bot.get_guild(int(os.environ["KGX_GUILD_ID"]))
            # オークションについて
            cur.execute("SELECT ch_id, auction_owner_id, embed_message_id from auction;")
            auction_data = cur.fetchall()
            for ch_id, auction_owner_id, embed_message_id in auction_data:
                if auction_owner_id == 0:
                    continue
                if not kgx.get_member(auction_owner_id):
                    ch = self.bot.get_channel(ch_id)
                    d = datetime.datetime.now()  # 現在時刻の取得
                    time = d.strftime("%Y/%m/%d %H:%M:%S")

                    description = f"このオークションの主催者であるユーザーID: {auction_owner_id} は\n" \
                                  f"このサーバーから退出したためこのオークションは終了します。"
                    embed = discord.Embed(description=description, color=0xdc143c)
                    embed.set_footer(text=f'channel:{ch.name}\ntime:{time}')
                    auction_embed = await ch.fetch_message(embed_message_id)
                    await auction_embed.unpin()
                    self.bot.reset_ch_db(ch_id, "a")
                    await ch.send(embed=embed)
                    await ch.send('--------ｷﾘﾄﾘ線--------')
                    await asyncio.sleep(0.3)
                    try:
                        await asyncio.wait_for(ch.edit(name=f"{ch.name}{os.environ['NOT_HELD_SUFFIX']}"), timeout=3.0)
                    except asyncio.TimeoutError:
                        continue

            # 取引について
            cur.execute("SELECT ch_id, deal_owner_id, embed_message_id from deal;")
            deal_data = cur.fetchall()
            for ch_id, deal_owner_id, embed_message_id in deal_data:
                if deal_owner_id == 0:
                    continue
                if not kgx.get_member(deal_owner_id):
                    ch = self.bot.get_channel(ch_id)
                    d = datetime.datetime.now()  # 現在時刻の取得
                    time = d.strftime("%Y/%m/%d %H:%M:%S")

                    description = f"この取引の主催者であるユーザーID: {deal_owner_id} は\n" \
                                  f"このサーバーから退出したためこの取引は終了します。"
                    embed = discord.Embed(description=description, color=0xdc143c)
                    embed.set_footer(text=f'channel:{ch.name}\ntime:{time}')
                    auction_embed = await ch.fetch_message(embed_message_id)
                    await auction_embed.unpin()
                    self.bot.reset_ch_db(ch_id, "d")
                    await ch.send(embed=embed)
                    await ch.send('--------ｷﾘﾄﾘ線--------')
                    await asyncio.sleep(0.3)
                    try:
                        await asyncio.wait_for(ch.edit(name=f"{ch.name}{os.environ['NOT_HELD_SUFFIX']}"), timeout=3.0)
                    except asyncio.TimeoutError:
                        continue

        except Exception as e:
            orig_error = getattr(e, "original", e)
            error_msg = ''.join(traceback.TracebackException.from_exception(orig_error).format())
            await self.bot.send_error_log("on_check_time_loop", "None", error_msg)


async def setup(bot):
    await bot.add_cog(CheckUser(bot))
