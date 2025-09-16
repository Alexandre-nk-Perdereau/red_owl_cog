import discord
import dotenv
from redbot.core import Config, commands

from .seedream_commands import SeedreamCommands
from .dice_commands import DiceCommands
import asyncio
from datetime import datetime, timedelta
from .alt_text_commands import AltTextCommands


class RedOwlCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        dotenv.load_dotenv(
            "/home/alexa/cogs/red_owl_cog/.env", override=True
        )  # TODO: improve this part to not be that specific
        default_guild = {
            "alt_text_channels": [],
        }
        self.config.register_guild(**default_guild)
        self.dice_commands = DiceCommands()
        self.alt_text_commands = AltTextCommands(bot, self.config)
        self.seedream_commands = SeedreamCommands(bot)

    @commands.hybrid_command(aliases=["h"])
    async def hexa(self, ctx, num_dice: int, extra_success: int = 0):
        await self.dice_commands.hexa(ctx, num_dice, extra_success)

    @commands.hybrid_command()
    async def fate(self, ctx, bonus: int = 0):
        await self.dice_commands.fate(ctx, bonus)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handler unique pour tous les messages."""

        if message.author.bot or not message.guild:
            return

        channel_id = str(message.channel.id)

        alt_text_channels = await self.config.guild(message.guild).alt_text_channels()
        if channel_id in alt_text_channels and message.attachments:
            await self.alt_text_commands.generate_alt_text_for_images(message)

    @commands.hybrid_command()
    async def remind_me(self, ctx, duration: str, *, message: str = None):
        time_units = {"m": "minutes", "h": "hours", "d": "days"}

        try:
            amount = int(duration[:-1])
            unit = duration[-1].lower()
            if unit not in time_units:
                raise ValueError
        except (ValueError, IndexError):
            await ctx.send(
                "Format de durée invalide. Utilisez un nombre suivi de 'm' (minutes), 'h' (heures) ou 'd' (jours)."
            )
            return

        reminder_time = datetime.now() + timedelta(**{time_units[unit]: amount})
        human_readable_time = reminder_time.strftime("%d/%m/%Y à %H:%M:%S")

        reminder_text = message or "Pas de message de rappel spécifié."

        await ctx.send(f"Rappel défini pour le {human_readable_time}.")

        async def send_reminder():
            await asyncio.sleep((reminder_time - datetime.now()).total_seconds())

            if isinstance(ctx.interaction, discord.Interaction):
                await ctx.send(
                    f"{ctx.author.mention}, voici votre rappel : {reminder_text}"
                )
            else:
                reminder_message = await ctx.channel.fetch_message(ctx.message.id)
                await ctx.send(
                    f"{ctx.author.mention}, voici votre rappel : {reminder_message.jump_url}"
                )

        self.bot.loop.create_task(send_reminder())

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    async def activate_image_alt_text(self, ctx):
        """Active/désactive la génération de texte alternatif pour les images dans ce canal."""
        await self.alt_text_commands.activate_image_alt_text(ctx)

    @commands.hybrid_command(name="gen")
    async def gen(self, ctx, width: int, height: int, *, prompt: str):
        """
        Génère ou édite une image avec Seedream v4 (FAL).
        Usage: !gen <width> <height> <prompt>
        - Sans image jointe : génération (txt2img)
        - Avec images jointes : édition (img2img) sur les pièces jointes (max 10)
        Contraintes: width/height ∈ [1024, 4096]. Safety désactivée.
        """
        await self.seedream_commands.gen(ctx, width, height, prompt=prompt)
