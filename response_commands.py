import discord
import asyncio
from .utils import split_embed


class ResponseCommands:
    def __init__(self, config):
        self.config = config

    async def add_response(
        self, ctx, user: discord.Member, keyword: str, response: str
    ):
        user_id_str = str(user.id)
        all_response_rules = await self.config.guild(ctx.guild).response_rules()
        if user_id_str not in all_response_rules:
            all_response_rules[user_id_str] = {}
        all_response_rules[user_id_str][keyword] = response
        await self.config.guild(ctx.guild).response_rules.set(all_response_rules)
        await ctx.send(f"Response set for {user.display_name} when saying '{keyword}'.")

    async def remove_response(self, ctx, user: discord.Member, keyword: str):
        guild_responses = await self.config.guild(ctx.guild).response_rules.get_raw(
            str(user.id)
        )
        if keyword in guild_responses:
            del guild_responses[keyword]
            await self.config.guild(ctx.guild).response_rules.set_raw(
                user.id, value=guild_responses
            )
            await ctx.send(
                f"Removed automated response for {user.display_name} for keyword '{keyword}'."
            )
        else:
            await ctx.send("No automated response found for that keyword and user.")

    async def list_responses(self, ctx):
        all_response_rules = await self.config.guild(ctx.guild).response_rules()
        if not all_response_rules:
            await ctx.send("No automated responses set.")
            return

        for user_id, keywords in all_response_rules.items():
            member = ctx.guild.get_member(int(user_id))
            member_name = member.display_name if member else f"UserID {user_id}"
            embed = discord.Embed(
                title=f"Automated Responses for {member_name}", color=0x4CAF50
            )
            for keyword, response in keywords.items():
                embed.add_field(
                    name=f"Keyword: '{keyword}'",
                    value=f"Response: '{response}'",
                    inline=False,
                )
            if len(embed.fields) <= 25 and embed.fields:
                await ctx.send(embed=embed)
            else:
                split_embeds = split_embed(embed)
                for e in split_embeds:
                    if e.fields:
                        await ctx.send(embed=e)

    async def check_and_respond(self, message):
        user_id = str(message.author.id)
        response_rules = await self.config.guild(message.guild).response_rules()
        if user_id in response_rules:
            user_rules = response_rules[user_id]
            for keyword, response in user_rules.items():
                if keyword in message.content:
                    await asyncio.sleep(3)
                    try:
                        msg = await message.channel.fetch_message(message.id)
                        if msg:
                            await message.channel.send(response)
                    except discord.NotFound:
                        pass
                    break
