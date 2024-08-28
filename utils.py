import discord


def split_embed(embed):
    embeds = []
    current_embed = discord.Embed(title=embed.title, color=embed.color)
    for index, field in enumerate(embed.fields):
        if index % 25 == 0 and index != 0:
            embeds.append(current_embed)
            current_embed = discord.Embed(title=embed.title, color=embed.color)
        current_embed.add_field(name=field.name, value=field.value, inline=field.inline)
    embeds.append(current_embed)
    return embeds


async def get_message_from_link(ctx, link):
    """Récupère un message à partir d'un lien."""
    try:
        message_id = int(link.split("/")[-1])
        channel_id = int(link.split("/")[-2])
        guild = ctx.guild
        channel = guild.get_channel(channel_id)
        if channel:
            try:
                message = await channel.fetch_message(message_id)
                return message
            except discord.NotFound:
                await ctx.send("Message introuvable.")
        else:
            await ctx.send("Canal introuvable.")
    except (IndexError, ValueError):
        await ctx.send("Lien de message invalide.")
    return None
