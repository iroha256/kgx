import random
import re

import bs4
import requests
from discord.ext import commands
import discord
from datetime import datetime
import traceback
import asyncio
from discord import Embed
import os
import redis

# Redisに接続
pool = redis.ConnectionPool.from_url(
    url=os.environ['REDIS_URL'],
    db=0,
    decode_responses=True
)

rc = redis.StrictRedis(connection_pool=pool)

# Redisに接続
pool2 = redis.ConnectionPool.from_url(
    url=os.environ['HEROKU_REDIS_ORANGE_URL'],
    db=0,
    decode_responses=True
)

rc2 = redis.StrictRedis(connection_pool=pool2)


def is_auction_category(ctx):
    """チャンネルがオークションカテゴリに入っているかの真偽値を返す関数"""
    auction_category_ids = {c.id for c in ctx.guild.categories if c.name.startswith('>')}
    return ctx.channel.category_id in auction_category_ids


def is_normal_category(ctx):
    """チャンネルがノーマルカテゴリに入っているかの真偽値を返す関数"""
    normal_category_ids = {this.id for this in ctx.guild.categories if this.name.startswith('*')}
    return ctx.channel.category_id in normal_category_ids


def is_siina_category(ctx):
    """チャンネルが椎名カテゴリに入っているかの真偽値を返す関数"""
    siina_category_ids = {siina.id for siina in ctx.guild.categories if "椎名" in siina.name}
    return ctx.channel.category_id in siina_category_ids


class Message(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        # メッセージ送信者がBotだった場合は無視する
        if message.author.bot:
            return
        try:
            # MCID_check
            if message.channel.id == 558278443440275461:
                mcid = f'{message.content}'.replace('\\', '')
                p = re.compile(r'^[a-zA-Z0-9_]+$')
                if p.fullmatch(message.content):
                    mcid = str.lower(mcid)
                    url = f"https://w4.minecraftserver.jp/player/{mcid}"
                    try:
                        res = requests.get(url)
                        res.raise_for_status()
                        soup = bs4.BeautifulSoup(res.text, "html.parser")
                        td = soup.td
                        if f'{mcid}' in f'{td}':
                            # 存在した場合の処理
                            role1 = discord.utils.get(message.guild.roles, name="新人")
                            role2 = discord.utils.get(message.guild.roles, name="MCID報告済み")
                            emoji = ['👍', '🙆']
                            await message.author.remove_roles(role1)
                            await message.author.add_roles(role2)
                            await message.add_reaction(random.choice(emoji))
                            CHANNEL_ID = 591244559019802650
                            channel = self.bot.get_channel(CHANNEL_ID)
                            color = [0x3efd73, 0xfb407c, 0xf3f915, 0xc60000, 0xed8f10, 0xeacf13, 0x9d9d9d, 0xebb652,
                                     0x4259fb,
                                     0x1e90ff]
                            embed = discord.Embed(description=f'{message.author.display_name}のMCIDの報告を確認したよ！',
                                                  color=random.choice(color))
                            embed.set_author(name=message.author,
                                             icon_url=message.author.avatar_url, )  # ユーザー名+ID,アバターをセット
                            await channel.send(embed=embed)
                        else:
                            embed = discord.Embed(
                                description=f'{message.author} さん。\n入力されたMCIDは実在しないか、又はまだ一度も整地鯖にログインしていません。\n'
                                            f'続けて間違った入力を行うと規定によりBANの対象になることがあります。',
                                color=0xff0000)
                            await message.channel.send(embed=embed)
                    except requests.exceptions.HTTPError:
                        await message.channel.send(f'requests.exceptions.HTTPError')
                else:
                    embed = discord.Embed(description="MCIDに使用できない文字が含まれています'\n続けて間違った入力を行うと規定によりBANの対象になることがあります。",
                                          color=0xff0000)
                    await message.channel.send(embed=embed)

            # 引用機能
            if "https://discordapp.com/channels/558125111081697300/" in message.content:
                for url in message.content.split('https://discordapp.com/channels/558125111081697300/')[1:]:
                    try:
                        channel_id = int(url[0:18])
                        message_id = int(url[19:37])
                        ch = message.guild.get_channel(int(channel_id))
                        msg = await ch.fetch_message(int(message_id))

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
                            embed.set_author(name=msg.author, icon_url=msg.author.avatar_url)
                            embed.set_footer(text=msg.channel.name, icon_url=msg.guild.icon_url)
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
            error_message = f'```{traceback.format_exc()}```'
            ch = message.guild.get_channel(628807266753183754)
            d = datetime.now()  # 現在時刻の取得
            time = d.strftime("%Y/%m/%d %H:%M:%S")
            embed = Embed(title='Error_log', description=error_message, color=0xf04747)
            embed.set_footer(text=f'channel:{message.channel}\ntime:{time}\nuser:{message.author.display_name}')
            await ch.send(embed=embed)

    @commands.command()
    async def version(self, ctx):
        if not is_normal_category(ctx) and not is_auction_category(ctx):
            embed = discord.Embed(description="現在のバージョンは**5.0.0**です\nNow version **5.0.0** working.", color=0x4259fb)
            await ctx.send(embed=embed)

    @commands.command()
    async def invite(self, ctx):
        if not is_normal_category(ctx) and not is_auction_category(ctx):
            await ctx.send('招待用URL:https://discord.gg/Syp85R4')

    @commands.command()
    async def check_role(self, ctx):  # 更新
        for member in range(self.bot.get_guild(558125111081697300).member_count):
            if self.bot.get_guild(558125111081697300).members[member].bot:
                pass
            r = redis.from_url(os.environ['REDIS_URL'])  # os.environで格納された環境変数を引っ張ってくる
            key = f"score-{self.bot.get_guild(558125111081697300).members[member].id}"
            score = int(r.get(key) or "0")
            await ctx.channel.send(self.bot.get_guild(558125111081697300).members[member])
            before, after, embed = self.bot.checkRole(score, self.bot.get_guild(558125111081697300).members[member])
            await self.bot.get_guild(558125111081697300).members[member].remove_roles(before)
            await self.bot.get_guild(558125111081697300).members[member].add_roles(after)
        await ctx.channel.send("照会終了")

    @commands.command()
    async def bidscore(self, ctx, pt):  # カウントしてその数字に対応する役職を付与する
        if not ctx.channel.id == 558265536430211083:
            return

        CHANNEL_ID = 602197766218973185
        channel = self.bot.get_channel(CHANNEL_ID)
        p = re.compile(r'^[0-9]+$')
        if p.fullmatch(pt):
            kazu = int(pt)
            r = redis.from_url(os.environ['REDIS_URL'])  # os.environで格納された環境変数を引っ張ってくる
            key = f"score-{ctx.author.id}"
            oldscore = int(r.get(key) or "0")
            newscore = oldscore + kazu
            r.set(key, str(newscore))
            embed = discord.Embed(description=f'**{ctx.author.display_name}**の現在の落札ポイントは**{newscore}**です。',
                                  color=0x9d9d9d)
            embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url, )  # ユーザー名+ID,アバターをセット
            await channel.send(embed=embed)
            before, after, embed = self.bot.checkRole(newscore, ctx.author)
            await ctx.author.remove_roles(before)
            await ctx.author.add_roles(after)
            if embed is not None:
                await ctx.channel.send(embed=embed)
            embed = discord.Embed(description=f'**{ctx.author.display_name}**に落札ポイントを付与しました。', color=0x9d9d9d)
            embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url, )  # ユーザー名+ID,アバターをセット
            await ctx.channel.send(embed=embed)
            await asyncio.sleep(0.5)
            # ランキングを出力する
            CHANNEL_ID = 677905288665235475
            channel = self.bot.get_channel(CHANNEL_ID)
            # とりあえず、ランキングチャンネルの中身を消す
            await channel.purge(limit=1)
            await channel.send(embed=self.bot.createRankingEmbed())

    # todo 未完成。
    @commands.command()
    async def tend(self, ctx):
        # todo ここでは a st + bの形式で来ることを想定している
        msg = f'{ctx.content}'.replace('!tend ', '')
        tend_price = self.bot.siina_check(msg)
        if not tend_price == 0:
            r = redis.from_url(os.environ['HEROKU_REDIS_YELLOW_URL'])
            # todo チャンネルIDと入札額を紐づけする。また、bid操作で個々の値に0をセットする。
            # todo startの初期価格未満は弾く。同一人物の2回入札も弾く。
            key = ctx.channel.id
            before_tend_price = int(r.get(key) or 0)
            if tend_price > before_tend_price:
                await ctx.channel.send(f"この入札は以前の入札額より低いです。やり直してください。")
                return
        else:
            await ctx.channel.send(f"Error.有効な入札ではありません。\n{ctx.author.display_name}の入札:{ctx.content}")

    @commands.command()
    async def set_user_auction_count(self, ctx, user_id: int, n: int):
        # その人が取り扱ってるオークションの個数を指定
        r = redis.from_url(os.environ['HEROKU_REDIS_BLACK_URL'])
        key = user_id
        auction_now = n
        r.set(key, auction_now)
        await ctx.channel.send(
            f"{self.bot.get_user(user_id).display_name}さんのオークションの開催個数を**{auction_now}**個にセットしました。")

    @commands.command()
    async def start(self, ctx):
        if is_auction_category(ctx):
            # 2つ行ってる場合はreturn
            user = ctx.author.id
            if self.bot.operate_user_auction_count("g", user) >= 2:
                description = "貴方はすでにオークションを2つ以上行っているためこれ以上オークションを始められません。\n" \
                              "行っているオークションが2つ未満になってから再度行ってください。"
                await ctx.channel.send(embed=discord.Embed(description=description, color=0xf04747))
                await ctx.channel.send("--------ｷﾘﾄﾘ線--------")
                return

            tmprole = discord.utils.get(ctx.guild.roles, name="現在商品登録中")
            await ctx.author.add_roles(tmprole)
            auction_registration_user_id = ctx.author.id
            await asyncio.sleep(0.3)
            if discord.utils.get(ctx.author.roles, name="現在商品登録中"):

                def check(m):
                    if m.author.bot:
                        return
                    elif m.author.id == auction_registration_user_id:
                        return m.channel == ctx.channel

                def check2(forthUserInput):
                    return forthUserInput.channel == ctx.channel and re.match(
                        r'[0-9]{2}/[0-9]{2}-[0-9]{2}:[0-9]{2}',
                        forthUserInput.content)

                embed = discord.Embed(
                    description="出品するものを入力してください。",
                    color=0xffaf60)
                await ctx.channel.send(embed=embed)
                userInput1 = await self.bot.wait_for('message', check=check)
                embed = discord.Embed(description="開始価格を入力してください。(椎名か、ガチャ券かなどを明記して書くこと)", color=0xffaf60)
                await ctx.channel.send(embed=embed)
                userInput2 = await self.bot.wait_for('message', check=check)
                embed = discord.Embed(description="即決価格を入力してください。", color=0xffaf60)
                await ctx.channel.send(embed=embed)
                userInput3 = await self.bot.wait_for('message', check=check)
                embed = discord.Embed(
                    description="オークション終了日時を入力してください。\n**注意！**時間の書式に注意してください！\n"
                                "例　5月14日の午後8時に終了したい場合：\n**05/14-20:00**と入力してください。\n"
                                "この形でない場合認識されません！\n**間違えて打ってしまった場合その部分は必ず削除してください。**",
                    color=0xffaf60)
                await ctx.channel.send(embed=embed)
                userInput4 = await self.bot.wait_for('message', check=check2)
                embed = discord.Embed(
                    description="その他、即決特典などありましたらお書きください。\n長い場合、改行などをして**１回の送信**で書いてください。\n"
                                "何も無ければ「なし」で構いません。",
                    color=0xffaf60)
                await ctx.channel.send(embed=embed)
                userInput5 = await self.bot.wait_for('message', check=check)
                kazu = 11
                await ctx.channel.purge(limit=kazu)
                embed = discord.Embed(title="これで始めます。よろしいですか？YES/NOで答えてください。(小文字でもOK。NOの場合初めからやり直してください。)",
                                      color=0xffaf60)
                embed.add_field(name="出品者", value=f'\n\n{ctx.author.display_name}', inline=True)
                embed.add_field(name="出品物", value=f'\n\n{userInput1.content}', inline=True)
                embed.add_field(name="開始価格", value=f'\n\n{userInput2.content}', inline=False)
                embed.add_field(name="即決価格", value=f'\n\n{userInput3.content}', inline=False)
                embed.add_field(name="終了日時", value=f'\n\n{userInput4.content}', inline=True)
                embed.add_field(name="特記事項", value=f'\n\n{userInput5.content}', inline=True)
                await ctx.channel.send(embed=embed)
                userInput6 = await self.bot.wait_for('message', check=check)
                if userInput6.content == "YES" or userInput6.content == "yes" or userInput6.content == "いぇｓ" or userInput6.content == "いぇs":
                    kazu = 2
                    await ctx.channel.purge(limit=kazu)
                    await asyncio.sleep(0.3)
                    embed = discord.Embed(title="オークション内容", color=0xffaf60)
                    embed.add_field(name="出品者", value=f'\n\n{ctx.author.display_name}', inline=True)
                    embed.add_field(name="出品物", value=f'\n\n{userInput1.content}', inline=True)
                    embed.add_field(name="開始価格", value=f'\n\n{userInput2.content}', inline=False)
                    embed.add_field(name="即決価格", value=f'\n\n{userInput3.content}', inline=False)
                    embed.add_field(name="終了日時", value=f'\n\n{userInput4.content}', inline=True)
                    embed.add_field(name="特記事項", value=f'\n\n{userInput5.content}', inline=True)
                    await ctx.channel.send(embed=embed)
                    await ctx.channel.send("<:siina:558251559394213888>オークションを開始します<:siina:558251559394213888>")
                    Channel = ctx.channel
                    await Channel.edit(name=Channel.name.split('☆')[0])
                    await ctx.author.remove_roles(tmprole)
                    # ここで、その人が行っているオークションの個数を増やす
                    user = ctx.author.id
                    r = redis.from_url(os.environ['HEROKU_REDIS_BLACK_URL'])
                    r.set(int(ctx.author.id), self.bot.operate_user_auction_count("s+", user))
                else:
                    kazu = 2
                    await ctx.channel.purge(limit=kazu)
                    await ctx.channel.send("初めからやり直してください。\n--------ｷﾘﾄﾘ線--------")
                    await ctx.author.remove_roles(tmprole)
            else:
                await ctx.channel.send("RoleError.運営を呼んでください")
        elif is_normal_category(ctx):
            # 2つ行ってる場合はreturn
            user = ctx.author.id
            if self.bot.operate_user_auction_count("g", user) >= 2:
                description = "貴方はすでにオークションを2つ以上行っているためこれ以上オークションを始められません。\n" \
                              "行っているオークションが2つ未満になってから再度行ってください。"
                await ctx.channel.send(embed=discord.Embed(description=description, color=0xf04747))
                await ctx.channel.send("--------ｷﾘﾄﾘ線--------")
                return

            tmprole = discord.utils.get(ctx.guild.roles, name="現在商品登録中")
            await ctx.author.add_roles(tmprole)
            await asyncio.sleep(0.3)
            if discord.utils.get(ctx.author.roles, name="現在商品登録中"):

                def check(m):
                    if m.author.bot:
                        return
                    else:
                        return m.channel == ctx.channel

                def check2(forthUserInput):
                    return forthUserInput.channel == ctx.channel and re.match(
                        r'[0-9]{2}/[0-9]{2}-[0-9]{2}:[0-9]{2}',
                        forthUserInput.content)

                embed = discord.Embed(
                    description="出品するものを入力してください。",
                    color=0xffaf60)
                await ctx.channel.send(embed=embed)

                userInput1 = await self.bot.wait_for('message', check=check)
                embed = discord.Embed(description="希望価格を入力してください。(椎名か、ガチャ券かなどを明記して書くこと)", color=0xffaf60)
                await ctx.channel.send(embed=embed)

                userInput2 = await self.bot.wait_for('message', check=check)
                embed = discord.Embed(
                    description="オークション終了日時を入力してください。\n**注意！**時間の書式に注意してください！\n"
                                "例　5月14日の午後8時に終了したい場合：\n**05/14-20:00**と入力してください。\nこの形でない場合認識されません！\n"
                                "**間違えて打ってしまった場合その部分は必ず削除してください。**",
                    color=0xffaf60)
                await ctx.channel.send(embed=embed)

                userInput3 = await self.bot.wait_for('message', check=check2)
                embed = discord.Embed(
                    description="その他、即決特典などありましたらお書きください。\n長い場合、改行などをして**１回の送信**で書いてください。\n"
                                "何も無ければ「なし」で構いません。",
                    color=0xffaf60)
                await ctx.channel.send(embed=embed)

                userInput4 = await self.bot.wait_for('message', check=check)
                kazu = 11
                await ctx.channel.purge(limit=kazu)

                embed = discord.Embed(title="これで始めます。よろしいですか？YES/NOで答えてください。(小文字でもOK。NOの場合初めからやり直してください。)",
                                      color=0xffaf60)
                embed.add_field(name="出品者", value=f'\n\n{ctx.author.display_name}', inline=True)
                embed.add_field(name="出品物", value=f'\n\n{userInput1.content}', inline=False)
                embed.add_field(name="希望価格", value=f'\n\n{userInput2.content}', inline=True)
                embed.add_field(name="終了日時", value=f'\n\n{userInput3.content}', inline=True)
                embed.add_field(name="特記事項", value=f'\n\n{userInput4.content}', inline=False)
                await ctx.channel.send(embed=embed)
                userInput6 = await self.bot.wait_for('message', check=check)
                # 出来ればYESとyesはlowerにするべきでは
                if userInput6.content == "YES" or userInput6.content == "yes" or userInput6.content == "いぇｓ" or userInput6.content == "いぇs":
                    kazu = 2
                    await ctx.channel.purge(limit=kazu)
                    await asyncio.sleep(0.3)
                    embed = discord.Embed(title="オークション内容", color=0xffaf60)
                    embed.add_field(name="出品者", value=f'\n\n{ctx.author.display_name}', inline=True)
                    embed.add_field(name="出品物", value=f'\n\n{userInput1.content}', inline=False)
                    embed.add_field(name="希望価格", value=f'\n\n{userInput2.content}', inline=True)
                    embed.add_field(name="終了日時", value=f'\n\n{userInput3.content}', inline=True)
                    embed.add_field(name="特記事項", value=f'\n\n{userInput4.content}', inline=False)
                    await ctx.channel.send(embed=embed)
                    await ctx.channel.send(
                        "<:shiina_balance:558175954686705664>取引を開始します<:shiina_balance:558175954686705664>")
                    Channel = ctx.channel
                    await Channel.edit(name=Channel.name.split('☆')[0])
                    await ctx.author.remove_roles(tmprole)
                    # ここで、その人が行っているオークションの個数を増やす
                    user = ctx.author.id
                    r = redis.from_url(os.environ['HEROKU_REDIS_BLACK_URL'])
                    r.set(int(ctx.author.id), self.bot.operate_user_auction_count("s+", user))
                else:
                    kazu = 2
                    await ctx.channel.purge(limit=kazu)
                    await ctx.channel.send("初めからやり直してください。\n--------ｷﾘﾄﾘ線--------")
                    await ctx.author.remove_roles(tmprole)

    @commands.command()
    async def bid(self, ctx):
        if is_auction_category(ctx):
            tmprole = discord.utils.get(ctx.guild.roles, name="現在商品登録中")
            await ctx.author.add_roles(tmprole)
            await asyncio.sleep(0.3)
            if discord.utils.get(ctx.author.roles, name="現在商品登録中"):
                if '☆' in ctx.channel.name:
                    embed = discord.Embed(
                        description=f'{ctx.author.display_name}さん。このチャンネルではオークションは行われていません',
                        color=0xff0000)
                    await ctx.channel.send(embed=embed)
                else:
                    auction_finish_user_id = ctx.author.id

                    def check(m):
                        if m.author.bot:
                            return
                        elif m.author.id == auction_finish_user_id:
                            return m.channel == ctx.channel and "," not in m.content

                    def check_siina_style(m):
                        if m.author.bot:
                            return
                        elif "椎名" in m.content and "sT" not in m.content and "St" not in m.content:
                            return m.channel == ctx.channel

                    kazu = 6
                    embed = discord.Embed(
                        description="注:**全体の入力を通して[,]の記号は使用できません。何か代替の記号をお使いください。**\n\n"
                                    "出品した品物名を書いてください。",
                        color=0xffaf60)
                    await ctx.channel.send(embed=embed)
                    userInput1 = await self.bot.wait_for('message', check=check)
                    embed = discord.Embed(description="落札者のユーザーネームを書いてください。", color=0xffaf60)
                    await ctx.channel.send(embed=embed)
                    userInput2 = await self.bot.wait_for('message', check=check)
                    description = "落札価格を入力してください。\n"
                    if is_siina_category(ctx):
                        description += "以下のような形式以外は認識されません。(個はなくてもOK): **椎名○○st+△(個)(椎名○○(個)も可)\n" \
                                       "ex: 椎名5st+16個 椎名336個"
                    embed = discord.Embed(description=description, color=0xffaf60)
                    await ctx.channel.send(embed=embed)
                    siina_amount = -1
                    userInput3 = ""
                    if ctx.channel.category_id in self.bot.siina_category_ids:
                        frag = True
                        while frag:
                            userInput3 = await self.bot.wait_for('message', check=check_siina_style)
                            siina_amount = self.bot.siina_check(userInput3.content)
                            if siina_amount == 0:
                                await ctx.channel.send("値が不正です。椎名○○st+△(個)の○と△には整数以外は入りません。再度入力してください。")
                                kazu += 2
                            else:
                                frag = False
                    else:
                        userInput3 = await self.bot.wait_for('message', check=check)
                    await ctx.channel.purge(limit=kazu)
                    embed = discord.Embed(description="オークション終了報告を受け付けました。", color=0xffaf60)
                    await ctx.channel.send(embed=embed)

                    # ランキング送信
                    if is_siina_category(ctx):
                        r = redis.from_url(os.environ['HEROKU_REDIS_ORANGE_URL'])  # os.environで格納された環境変数を引っ張ってくる
                        # 設計図: unique_idの初めは1,無ければそこに値を代入
                        i = 0
                        while True:
                            # keyに値がない部分まで管理IDを+
                            if r.get(i):
                                i += 1
                            else:
                                key = i
                                break
                        # 管理IDに紐づけて記録するデータの内容は[落札者,落札したもの,落札額,userid]がString型で入る.splitでlistにすること
                        redis_set_str = f"{userInput2.content},{userInput1.content},{siina_amount},{ctx.author.id}"
                        r.set(int(key), str(redis_set_str))
                        await self.bot.get_channel(705040893593387039).purge(limit=10)
                        await asyncio.sleep(0.1)
                        embed = self.bot.createHighBidRanking()
                        for i in range(len(embed)):
                            await self.bot.get_channel(705040893593387039).send(embed=embed[i])

                    # 記録送信
                    CHANNEL_ID = 558132754953273355
                    channel = self.bot.get_channel(CHANNEL_ID)
                    d = datetime.now()  # 現在時刻の取得
                    time = d.strftime("%Y/%m/%d")
                    embed = discord.Embed(title="オークション取引結果", color=0x36a64f)
                    embed.add_field(name="落札日", value=f'\n\n{time}', inline=False)
                    embed.add_field(name="出品者", value=f'\n\n{ctx.author.display_name}', inline=False)
                    embed.add_field(name="品物", value=f'\n\n{userInput1.content}', inline=False)
                    embed.add_field(name="落札者", value=f'\n\n{userInput2.content}', inline=False)
                    embed.add_field(name="落札価格", value=f'\n\n{userInput3.content}', inline=False)
                    embed.add_field(name="チャンネル名", value=f'\n\n{ctx.channel}', inline=False)
                    await channel.send(embed=embed)
                    await ctx.channel.send('--------ｷﾘﾄﾘ線--------')
                    await asyncio.sleep(0.3)
                    await ctx.channel.edit(name=ctx.channel.name + '☆')
                    await ctx.author.remove_roles(tmprole)
                    # ここで、その人が行っているオークションの個数を減らす
                    user = ctx.author.id
                    r = redis.from_url(os.environ['HEROKU_REDIS_BLACK_URL'])
                    r.set(int(ctx.author.id), self.bot.operate_user_auction_count("s-", user))

            else:
                await ctx.channel.send("RoleError.運営を呼んでください")
                await ctx.author.remove_roles(tmprole)

        elif is_normal_category(ctx):
            description = "ここは通常取引チャンネルです。終了報告は``!end``をお使いください。"
            embed = discord.Embed(description=description, color=0x4259fb)
            await ctx.channel.send(embed=embed)

    @commands.command()
    @commands.check(is_normal_category)
    async def end(self, ctx):
        await ctx.channel.send('--------ｷﾘﾄﾘ線--------')
        Channel = ctx.channel
        await Channel.edit(name=Channel.name + '☆')
        # ここで、その人が行っているオークションの個数を減らす
        user = ctx.author.id
        r = redis.from_url(os.environ['HEROKU_REDIS_BLACK_URL'])
        r.set(int(ctx.author.id), self.bot.operate_user_auction_count("s-", user))

    @commands.command()
    async def help(self, ctx):
        description = "<:shiina_balance:558175954686705664>!start\n\n" \
                      "オークションを始めるためのコマンドです。オークションチャンネルでのみ使用可能です。\n" \
                      "-------\n" \
                      "<:siina:558251559394213888>!bid\n\n" \
                      "オークションが終わったときにオークション内容を報告するためのコマンドです。\n" \
                      "ここで報告した内容は <#558132754953273355> に表示されます\n" \
                      "-------\n" \
                      "<:shiina_balance:558175954686705664>!end\n\n" \
                      "取引を終了するためのコマンドです。\n" \
                      "-------\n" \
                      "<:siina:558251559394213888>!bidscore 申請する落札ポイント\n\n" \
                      "落札ポイントを申請します。 <#558265536430211083> に入力すると申請できます。\n" \
                      "<#602197766218973185> に現在の落札ポイントが通知されます。\n" \
                      "<#677905288665235475> に現在の落札ポイントのランキングが表示されます。\n\n" \
                      "(例)!bidscore 2 {これで、自分の落札ポイントが2ポイント加算される。}\n" \
                      "-------\n" \
                      "<:shiina_balance:558175954686705664>!version\n\n" \
                      "現在のBotのバージョンを表示します。\n" \
                      "-------\n" \
                      "<:siina:558251559394213888>!help\n" \
                      "このBotのヘルプを表示します。\n" \
                      "-------\n"
        embed = discord.Embed(description=description, color=0x66cdaa)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Message(bot))