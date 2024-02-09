import asyncio
import random

import discord
from redbot.core import Config, commands


class RedOwlCog(commands.Cog):
    """Red Owl Cog"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {"response_rules": {}}
        self.config.register_guild(**default_guild)

    @commands.hybrid_command(aliases=["h"])
    async def hexa(self, ctx, num_dice: int, extra_success: int = 0):
        """Rolls dice and counts successes, with optional extra successes"""
        if num_dice < 1:
            await ctx.send("Number of dices must be at least 1")
            return
        if num_dice > 100:
            await ctx.send("Number of dices must be at maximum 100")
            return

        rolls, success = self.roll_dices(num_dice)
        initial_success = success
        success += extra_success

        # Création de l'embed
        embed = discord.Embed(title="🎲 Résultat des lancers", color=0x4CAF50)
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar.url)

        success_text = f"**{initial_success}** succès"
        if extra_success != 0:
            success_text += (
                f" + **{extra_success}** succès supplémentaires = **{success}** total"
            )
        embed.add_field(name="🏆 Succès", value=success_text, inline=False)

        # Formatage des résultats des lancers pour l'affichage
        detailed_rolls = " \n ".join(
            f"🎲 Lancer {i+1}: " + ", ".join(self.format_roll(r) for r in roll)
            for i, roll in enumerate(rolls)
        )
        embed.add_field(name="Détail des lancers", value=detailed_rolls, inline=False)
        embed.set_footer(text=f"Demandé par {ctx.author.display_name}")

        # Envoi de l'embed
        await ctx.send(embed=embed)

    def roll_dices(self, num_dice: int):
        num_faces = 6
        rolls = []
        success = 0

        while num_dice > 0:
            roll = [random.randint(1, num_faces) for _ in range(num_dice)]
            roll.sort(reverse=True)
            rolls.append(roll)
            num_dice = roll.count(6)
            success += sum(r >= 3 for r in roll)

        return rolls, success

    def format_roll(self, roll):
        if roll == 6:
            return f"**{roll}**"
        return str(roll)

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    async def response(self, ctx, user: discord.Member, keyword: str, *, response: str):
        """Sets a response for a specific keyword for a specific user"""
        user_id_str = str(user.id)

        # Récupérer le dictionnaire de configuration actuel pour les règles de réponse
        all_response_rules = await self.config.guild(ctx.guild).response_rules()

        # Vérifier si l'utilisateur existe déjà dans les règles, sinon l'ajouter
        if user_id_str not in all_response_rules:
            all_response_rules[user_id_str] = {}

        # Mettre à jour la réponse pour le mot-clé spécifique
        all_response_rules[user_id_str][keyword] = response

        # Sauvegarder les modifications dans la configuration
        await self.config.guild(ctx.guild).response_rules.set(all_response_rules)

        await ctx.send(f"Response set for {user.display_name} when saying '{keyword}'.")

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    async def remove_response(self, ctx, user: discord.Member, keyword: str):
        """Removes a specific automated response for a user"""
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

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        user_id = str(message.author.id)
        response_rules = await self.config.guild(message.guild).response_rules()

        # Vérifiez si des règles de réponse existent pour cet utilisateur
        if user_id in response_rules:
            user_rules = response_rules[user_id]
            for keyword, response in user_rules.items():
                if keyword in message.content:
                    # Attendre un certain temps avant de répondre
                    await asyncio.sleep(3)

                    # Vérifier si le message existe toujours
                    try:
                        msg = await message.channel.fetch_message(message.id)
                        if msg:
                            await message.channel.send(response)
                    except discord.NotFound:
                        pass
                    break

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    async def list_responses(self, ctx):
        """Lists all the automated responses set for users in the guild using embeds."""
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

            # Vérifier si l'embed ne dépasse pas la limite de champs
            if len(embed.fields) <= 25 and embed.fields:
                await ctx.send(embed=embed)
            else:
                # Si l'embed a trop de champs, le diviser et envoyer en plusieurs messages
                split_embeds = self.split_embed(embed)
                for e in split_embeds:
                    if e.fields:
                        await ctx.send(embed=e)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        """Delete the bot messages on a specific emote reaction"""
        specific_emote = "TG"
        if reaction.emoji.name == specific_emote and not user.bot:
            if reaction.message.author == self.bot.user:
                try:
                    await reaction.message.delete()
                except discord.Forbidden:
                    print("Je n'ai pas les permissions pour supprimer ce message.")
                except discord.HTTPException as e:
                    print(f"Erreur lors de la suppression du message : {e}")


    def split_embed(self, embed):
        """Divide a large embed into smaller embeds if it exceeds field limits."""
        embeds = []
        current_embed = discord.Embed(title=embed.title, color=embed.color)
        for index, field in enumerate(embed.fields):
            if index % 25 == 0 and index != 0:
                embeds.append(current_embed)
                current_embed = discord.Embed(title=embed.title, color=embed.color)
            current_embed.add_field(
                name=field.name, value=field.value, inline=field.inline
            )
        embeds.append(current_embed)
        return embeds
