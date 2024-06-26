import os

import discord
from discord.ext import commands


class RawReactionAdd(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        #DMなら早期リターンする
        if payload.member is None:
            return

        # botが付けたリアクションは早期リターンする
        if payload.member.bot:
            return

        # 今回、各種権限の不足については考慮していない
        # また、役職IDが存在しない場合も考慮していない

        # ここに反応させたいメッセージIDを入れる
        if payload.message_id == int(os.environ["ROLE_PANEL_MESSAGE_ID"]):
            channel = self.bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)

            # ここに反応させたい絵文字IDを入れる
            if payload.emoji.id == int(os.environ["SHIINA_EMOJI_ID"]):
                await message.remove_reaction(str(payload.emoji), payload.member)

                # ここに付与,剥奪させたい役職のIDを入れる
                role = message.guild.get_role(int(os.environ["AUCTION_NOTIFICATION_ROLE_ID"]))
                if discord.utils.get(payload.member.roles, id=role.id):
                    await payload.member.remove_roles(role, reason="役職剥奪のリアクションを押したため")
                    action = "剥奪"
                else:
                    await payload.member.add_roles(role, reason="役職付与のリアクションを押したため")
                    action = "付与"

                # DMに結果を報告
                await payload.member.send(f"役職「{role.name}」を{action}しました")


async def setup(bot):
    await bot.add_cog(RawReactionAdd(bot))
