import os
from datetime import datetime

import discord
import psycopg2
from discord.ext import commands

# TODO DB周りのクラス作る
SQLpath = os.environ["DATABASE_URL"]
db = psycopg2.connect(SQLpath)
cur = db.cursor()


class RawMemberRemove(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_member_remove(self, payload):
        await self.bot.wait_until_ready()

        # KGx以外は弾く
        if payload.guild_id != int(os.environ["KGX_GUILD_ID"]):
            return

        user = payload.user

        # オークション
        cur.execute("SELECT ch_id, embed_message_id FROM auction WHERE auction_owner_id = %s;", (user.id,))
        await self.end_auction(cur.fetchall(), "auction", user)

        # 取引
        cur.execute("SELECT ch_id, embed_message_id FROM deal WHERE deal_owner_id = %s;", (user.id,))
        await self.end_auction(cur.fetchall(), "deal", user)

    async def end_auction(self, auction_data: list, sales_format: str, user: discord.User) -> None:
        """オークションを終了させる

            Args:
                auction_data (list): オークションデータ(タプル)のリスト。[(auction_channel_id, embed_message_id)]
                sales_format (str): 販売形式。"auction"か"deal"。
                user (discord.User): 脱退したユーザー。
        """

        # データが無ければ早期リターン
        if len(auction_data) == 0:
            return

        for auction_channel_id, embed_message_id in auction_data:
            # レコードを初期化
            self.bot.reset_ch_db(auction_channel_id, "a" if sales_format == "auction" else "d")

            # ピン止めを外す
            auction_channel = self.bot.get_channel(auction_channel_id)
            auction_embed = await auction_channel.fetch_message(embed_message_id)
            await auction_embed.unpin()

            # 終了メッセージを送信
            sales_format_name = "オークション" if sales_format == "auction" else "取引"
            description = f"この{sales_format_name}の主催者であるユーザー: {user.display_name} は\n" \
                          f"このサーバーから退出したためこの{sales_format_name}は終了します。"
            time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            embed = discord.Embed(description=description, color=0xdc143c)
            embed.set_footer(text=f"channel:{auction_channel.name}\ntime:{time}")
            await auction_channel.send(embed=embed)
            await auction_channel.send("--------ｷﾘﾄﾘ線--------")

            # チャンネル名に☆をつける
            await auction_channel.edit(name=f"{auction_channel.name}{os.environ['NOT_HELD_SUFFIX']}")

        # 一覧を更新する
        await self.bot.update_auction_or_deal_list(sales_format)


async def setup(bot):
    await bot.add_cog(RawMemberRemove(bot))
