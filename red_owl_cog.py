from redbot.core import commands, Config
import random
import discord
import asyncio

class RedOwlCog(commands.Cog):
    """Red Owl Cog"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {"response_rules": {}}
        self.config.register_guild(**default_guild)

    @commands.hybrid_command(aliases=['h'])
    async def hexa(self, ctx, num_dice: int):
        """Rolls dice and counts successes"""
        if num_dice < 1:
            await ctx.send("Number of dices must be at least 1")
            return
        if num_dice > 100:
            await ctx.send("Number of dices must be at maximum 100")
            return

        rolls, success = self.roll_dices(num_dice)

        # Création de l'embed
        embed = discord.Embed(title=f"🎲 Résultat des lancers", color=0x4CAF50)
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar.url)
        embed.add_field(name="🏆 Succès", value=f"**{success}** succès", inline=False)

        # Formatage des résultats des lancers pour l'affichage
        detailed_rolls = ' \n '.join(f"🎲 Lancer {i+1}: " + ', '.join(self.format_roll(r) for r in roll) for i, roll in enumerate(rolls))
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
        guild_id = ctx.guild.id
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
        guild_responses = await self.config.guild(ctx.guild).response_rules.get_raw(str(user.id))

        if keyword in guild_responses:
            del guild_responses[keyword]
            await self.config.guild(ctx.guild).response_rules.set_raw(user.id, value=guild_responses)
            await ctx.send(f"Removed automated response for {user.display_name} for keyword '{keyword}'.")
        else:
            await ctx.send("No automated response found for that keyword and user.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        guild_id = message.guild.id
        response_rules = await self.config.guild(message.guild).response_rules.all()

        for user_id, keywords in response_rules.items():
            if message.author.id == int(user_id):
                for keyword, response in keywords.items():
                    if keyword in message.content:
                        # Attendre un certain temps avant de répondre
                        await asyncio.sleep(3)  # Attendre 1 secondes, par exemple

                        # Vérifier si le message existe toujours
                        try:
                            msg = await message.channel.fetch_message(message.id)
                            if msg:
                                await message.channel.send(response)
                        except discord.NotFound:
                            # Le message a été supprimé, ne pas répondre
                            pass
                        break

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    async def list_responses(self, ctx):
        """Lists all the automated responses set for users in the guild."""
        all_response_rules = await self.config.guild(ctx.guild).response_rules()
    
        if not all_response_rules:
            await ctx.send("No automated responses set.")
            return
    
        response_message = "Automated Responses:\n"
        for user_id, keywords in all_response_rules.items():
            member = ctx.guild.get_member(int(user_id))
            if member:
                response_message += f"\nResponses for {member.display_name}:\n"
                for keyword, response in keywords.items():
                    response_message += f" - Keyword: '{keyword}' -> Response: '{response}'\n"
            else:
                response_message += f"\nResponses for UserID {user_id} (member not found):\n"
                for keyword, response in keywords.items():
                    response_message += f" - Keyword: '{keyword}' -> Response: '{response}'\n"

        # Envoi du message en plusieurs parties si nécessaire (limite de 2000 caractères par message sur Discord)
        for chunk in [response_message[i:i+2000] for i in range(0, len(response_message), 2000)]:
            await ctx.send(chunk)

