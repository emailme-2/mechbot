"""Visibility test: reply 'hello' when someone sends 43110.

43110 is 'hello' upside down on a calculator. If the bot replies, it proves it
can actually read message text, which means the Message Content intent is on.
Delete this cog once you've confirmed it works.
"""

import discord
from discord.ext import commands

TRIGGER = "43110"


class MessageTest(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:  # don't react to ourselves or other bots
            return
        if TRIGGER in message.content:
            await message.reply("hello", mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MessageTest(bot))
