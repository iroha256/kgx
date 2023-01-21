from discord.ext import commands
import discord


class RawReactionAdd(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        # botが付けたリアクションは早期リターンする
        try:
            if payload.member.bot:
                return
        except AttributeError:
            try:
                ch = self.bot.get_channel(628807266753183754)
                channel = self.bot.get_channel(payload.channel_id)
                message = await channel.fetch_message(payload.message_id)
                await ch.send(
                    "on_raw_reaction_addでAttributeError\n"
                    f"msg: {message.jump_url}\n"
                    f"mem: {payload.member} <-予想が正しければNonetype"
                )
            except:
                ch = self.bot.get_channel(628807266753183754)
                await ch.send("エラー検知でまだエラー")
                return

        # 今回、各種権限の不足については考慮していない
        # また、役職IDが存在しない場合も考慮していない

        # ここに反応させたいメッセージIDを入れる
        if payload.message_id == 726365095797456927:
            channel = self.bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)

            # ここに反応させたい絵文字IDを入れる
            if payload.emoji.id == 558175789284196354:
                await message.remove_reaction(str(payload.emoji), payload.member)

                # ここに付与,剥奪させたい役職のIDを入れる
                role = message.guild.get_role(678502401707212800)
                if discord.utils.get(payload.member.roles, id=role.id):
                    await payload.member.remove_roles(role, reason="役職剥奪のリアクションを押したため")
                    action = "剥奪"
                else:
                    await payload.member.add_roles(role, reason="役職付与のリアクションを押したため")
                    action = "付与"

                # DMに結果を報告
                await payload.member.send(f"役職「{role.name}」を{action}しました")


def setup(bot):
    bot.add_cog(RawReactionAdd(bot))
