import os
from datetime import datetime

from discord import Embed
from discord.ext import commands


class MessageEditDelete(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot:
            return

        if message.content.lower().startswith(("!tend", "!add")):
            return

        d = datetime.now()  # 現在時刻の取得
        time = d.strftime("%Y/%m/%d %H:%M:%S")
        embed = Embed(description=f'**Deleted in <#{message.channel.id}>**\n\n{message.content}\n\n',
                      color=0xff0000)  # 発言内容をdescriptionにセット
        embed.set_author(name=message.author, icon_url=message.author.display_avatar, )  # ユーザー名+ID,アバターをセット
        embed.set_footer(text=f'User ID：{message.author.id} Time：{time}',
                         icon_url=message.guild.icon, )  # チャンネル名,時刻,鯖のアイコンをセット
        ch = message.guild.get_channel(int(os.environ["LOG_CHANNEL_ID"]))
        await ch.send(embed=embed)

    @commands.Cog.listener()  # point付与の術
    async def on_message_edit(self, before, after):
        # メッセージ送信者がBotだった場合は無視する
        if before.author.bot:
            return
        # URLの場合は無視する
        if "http" in before.content:
            return

        d = datetime.now()  # 現在時刻の取得
        time = d.strftime("%Y/%m/%d %H:%M:%S")
        # 発言内容をdescriptionにセット
        embed = Embed(
            description=f'**Changed in <#{before.channel.id}>**\n\n'
                        f'**before**\n{before.content}\n\n'
                        f'**after**\n{after.content}\n\n',
            color=0x1e90ff
        )
        embed.set_author(name=before.author, icon_url=before.author.display_avatar)  # ユーザー名+ID,アバターをセット
        embed.set_footer(text=f'User ID：{before.author.id} Time：{time}',
                         icon_url=before.guild.icon, )  # チャンネル名,時刻,鯖のアイコンをセット
        ch = before.guild.get_channel(int(os.environ["LOG_CHANNEL_ID"]))
        await ch.send(embed=embed)


async def setup(bot):
    await bot.add_cog(MessageEditDelete(bot))
