import json
import os
import random
import re
import traceback

import discord
import psycopg2
import qrcode
import requests
from discord import Embed
from discord.ext import commands

SQLpath = os.environ["DATABASE_URL"]
db = psycopg2.connect(SQLpath)  # sqlに接続
cur = db.cursor()  # なんか操作する時に使うやつ


class Message(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        # メッセージ送信者がBotだった場合は無視する
        if message.author.bot:
            return
        try:
            #乗っ取りアカウントを釣る
            #数行前の記述によりbotが乗っ取られても反応しないが仕様
            if message.channel.id == int(os.environ["BAN_CHANNEL_ID"]): #do not type here
                comment = f"{message.author.display_name}、id:{message.author.id}を、ハニートラップでbanしました"
                await message.author.ban(reason=comment)

                log_ch = self.bot.get_channel(int(os.environ["LOG_CHANNEL_ID"])) #log
                embed = discord.Embed(
                    description=comment,
                    color=0xff7700
                )
                await log_ch.send(embed=embed)
                await message.delete()

            # MCID_check
            if message.channel.id == int(os.environ["MCID_REPORT_CHANNEL_ID"]):
                mcid = message.content.replace("\\", "")
                if re.fullmatch("[a-zA-Z0-9_]{2,16}", mcid):
                    url = f"https://api.mojang.com/users/profiles/minecraft/{mcid}"
                    try:
                        res = requests.get(url)
                        res.raise_for_status()
                        try:
                            res = res.json()
                        except json.decoder.JSONDecodeError:
                            exsit = False
                        else:
                            exsit = True

                    except requests.exceptions.HTTPError:
                        exsit = None

                    if exsit is None:
                        await message.channel.send("現在データ参照元が使用できない状態です。しばらく待ってからもう一度お試しください。")
                        return

                    if exsit: #存在した場合の処理
                        uuid = res["id"]
                        cur.execute("SELECT count(*) FROM user_data WHERE %s = ANY(uuid)", (uuid,))
                        if cur.fetchone()[0] >= 1:
                            await message.channel.send("そのidは既にいずれかのユーザーに登録されています")
                            return

                        # SQLのuser_dataに新規登録
                        cur.execute("INSERT INTO user_data values (%s, %s, %s, ARRAY[%s]);", (message.author.id, 0, 0, uuid))
                        db.commit()

                        role1 = discord.utils.get(message.guild.roles, id=int(os.environ["ROOKIE_ROLE_ID"]))
                        role2 = discord.utils.get(message.guild.roles, id=int(os.environ["MCID_REPORTED_ROLE_ID"]))
                        await message.author.remove_roles(role1)
                        await message.author.add_roles(role2)
                        try:
                            await message.author.edit(nick=mcid)
                        except discord.errors.Forbidden:
                            await message.channel.send(f"{message.author.mention}権限エラー\nニックネームを申請したMCIDに変更してください。")

                        emoji = ['👍', '🙆']
                        await message.add_reaction(random.choice(emoji))
                        channel = self.bot.get_channel(int(os.environ["MCID_NOTIFICATION_CHANNEL_ID"]))
                        color = [
                            0x3efd73, 0xfb407c, 0xf3f915, 0xc60000,
                            0xed8f10, 0xeacf13, 0x9d9d9d, 0xebb652,
                            0x4259fb, 0x1e90ff
                        ]
                        embed = discord.Embed(description=f'{message.author.display_name}のMCIDの報告を確認したよ！',
                                                color=random.choice(color))
                        embed.set_author(name=message.author, icon_url=message.author.display_avatar)
                        await channel.send(embed=embed)

                    else:
                        embed = discord.Embed(
                            description=f'{message.author} さん。\n入力されたMCIDは実在しません。\n'
                                        '続けて間違った入力を行うと規定によりBANの対象になることがあります。',
                            color=0xff0000)
                        await message.channel.send(embed=embed)
                else:
                    embed = discord.Embed(description="MCIDに使用できない文字が含まれています'\n続けて間違った入力を行うと規定によりBANの対象になることがあります。",
                                          color=0xff0000)
                    await message.channel.send(embed=embed)

            #mcid変更申請chでspamが来るとmojangAPIに何度もアクセスさせてしまう
            #一度変更したら何日間アクセスしないとかにすれば防げるがダルい
            #ユーザーの良心を信じる
            if message.channel.id == int(os.environ["MCID_UPDATE_CHANNEL_ID"]): #mcid変更申請ch
                #カラム名: uuid
                cur.execute("SELECT * FROM user_data where user_id = %s", (message.author.id,))
                user_data = cur.fetchone()
                uuid = user_data[3][0]
                try:
                    url = f"https://sessionserver.mojang.com/session/minecraft/profile/{uuid}"
                    res = requests.get(url)
                    player_data = res.json()
                    new_mcid = player_data["name"]
                except requests.exceptions.HTTPError:
                    await message.channel.send("requests.exceptions.HTTPError")
                    return

                #変更後のmcidが既にニックネームに含まれているならニックネーム変更の必要はない
                if new_mcid in message.author.display_name:
                    return

                try:
                    await message.author.edit(nick=new_mcid)
                except discord.errors.Forbidden:
                    await message.channel.send(f"{message.author.mention}権限エラー\nニックネームを変更したMCIDに変更してください。")

                

            # 引用機能
            message_link_regexp = fr"https://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/" \
                                  fr"{re.escape(os.environ['KGX_GUILD_ID'])}((?:/[0-9]+){{2}})"
            url_filter = [msg.split("/")[1:] for msg in re.split(message_link_regexp, message.content)
                          if re.match("(/[0-9]+){2}", msg)]
            if len(url_filter) >= 1:
                for url in url_filter:
                    try:
                        channel_id = int(url[0])
                        message_id = int(url[1])
                        ch = message.guild.get_channel(channel_id)
                        if ch is None:
                            continue
                        msg = await ch.fetch_message(message_id)

                        def quote_reaction(msg, embed):
                            if msg.reactions:
                                reaction_send = ''
                                for reaction in msg.reactions:
                                    emoji = reaction.emoji
                                    count = str(reaction.count)
                                    reaction_send = f'{reaction_send}{emoji}{count} '
                                embed.add_field(name='reaction', value=reaction_send, inline=False)
                            return embed

                        if msg.embeds or msg.content or msg.attachments:
                            embed = Embed(description=msg.content, timestamp=msg.created_at)
                            embed.set_author(name=msg.author, icon_url=msg.author.display_avatar)
                            embed.set_footer(text=msg.channel.name, icon_url=msg.guild.icon)
                            if msg.attachments:
                                embed.set_image(url=msg.attachments[0].url)
                            embed = quote_reaction(msg, embed)
                            if msg.content or msg.attachments:
                                await message.channel.send(embed=embed)
                            if len(msg.attachments) >= 2:
                                for attachment in msg.attachments[1:]:
                                    embed = Embed().set_image(url=attachment.url)
                                    await message.channel.send(embed=embed)
                            for embed in msg.embeds:
                                embed = quote_reaction(msg, embed)
                                await message.channel.send(embed=embed)
                        else:
                            await message.channel.send('メッセージIDは存在しますが、内容がありません')
                    except discord.errors.NotFound:
                        await message.channel.send("指定したメッセージが見つかりません")

        except Exception:
            await self.bot.send_error_log(message.channel.name, message.author.display_name, traceback.format_exc())

    @commands.command()
    async def qr(self, ctx, qrcode_context: str):
        try:
            img = qrcode.make(f"{qrcode_context}")
            img.save("./icon.png")
            image = discord.File("./icon.png", filename="icon.png")
            embed = discord.Embed(description=f"作成結果",
                                  color=0x4259fb
                                  )
            embed.set_image(url="attachment://icon.png")
            await ctx.send(file=image, embed=embed)
        except Exception:
            await ctx.send("QRコードに含めるデータ量が大きすぎます")

    @commands.command()
    async def uuid_report(self, ctx, mcid: str):
        if discord.utils.get(ctx.author.roles, id=int(os.environ["UUID_UNCHECKED_ROLE_ID"])):
            uuid = self.bot.mcid_to_uuid(mcid)
            if uuid:
                cur.execute(f"update  user_data set uuid = ARRAY['{uuid}'] where user_id = {ctx.author.id}")
                db.commit()
                await ctx.send(f"{mcid}さんのuuid: {uuid}をシステムに登録しました。")
                role = discord.utils.get(ctx.guild.roles, id=int(os.environ["UUID_UNCHECKED_ROLE_ID"]))
                await ctx.author.remove_roles(role)
                role = discord.utils.get(ctx.guild.roles, id=int(os.environ["MCID_REPORTED_ROLE_ID"]))  # MCID報告済み
                await ctx.author.add_roles(role)
            else:
                await ctx.send(f"MCID:{mcid}は存在しません。もう一度確認してください。")
        else:
            await ctx.send("貴方のuuidは認証済みです。1アカウントにつき申請できるmcid/uuidは一つです。")

    @commands.command()
    async def add_account(self, ctx, mcid: str):
        uuid = self.bot.mcid_to_uuid(mcid)
        if not uuid:
            await ctx.send(f"MCID:{mcid}は存在しません。もう一度確認してください。")
            return
        
        cur.execute("SELECT count(*) FROM user_data WHERE %s = ANY(uuid)", (uuid,))
        if cur.fetchone()[0] >= 1:
            await ctx.send("そのidは既にいずれかのユーザーに登録されています")
            return

        cur.execute(f"update user_data set uuid = array_append(uuid, %s) where user_id = %s", (uuid, ctx.author.id))
        db.commit()
        await ctx.send(f"{mcid}さんのuuid: {uuid}をシステムに登録しました。")
        
    @commands.command()
    async def cs(self, ctx, amount: str):
        # 数値かどうかで渡す関数を変更する
        if amount.isdecimal():
            await ctx.send(f"{amount}はスタック表記で{self.bot.stack_check_reverse(int(amount))}です。")
        else:
            if self.bot.stack_check(amount) is None:
                await ctx.send(f"入力した値が不正な値です。")
            else:
                await ctx.send(f"{amount}は整数値で{self.bot.stack_check(amount)}です。")

    @commands.command()
    async def dm_setting(self, ctx, dm_boolean: str):
        # 数値かどうかで渡す関数を変更する
        if dm_boolean.lower() in ["true", "false"]:

            cur.execute(f"select dm_flag from user_data where user_id = {ctx.author.id}")

            dm_flag, = cur.fetchone()
            if (dm_boolean.lower() == "true" and dm_flag) or (dm_boolean.lower() == "false" and (not dm_flag)):
                await ctx.send("既に設定された値に変更されています。")
                return

            cur.execute(f"update user_data set dm_flag = {dm_boolean} where user_id = {ctx.author.id}")
            db.commit()

            if dm_boolean.lower() == "true":
                await ctx.send("botからのDMを受け取る設定にしました。")
            else:
                await ctx.send("botからのDMを拒否する設定にしました。")

        else:
            await ctx.send("設定の値が違います。以下のように設定してください。 ``!dm_setting True/False``")
    
    def cog_check(self, ctx):
        # 「コマンド」または「bot-command」のみ
        return ctx.channel.id in (int(os.environ["COMMAND_CHANNEL_ID"]), int(os.environ["DEV_COMMAND_CHANNEL_ID"]))


async def setup(bot):
    await bot.add_cog(Message(bot))
