import discord
import dotenv
from redbot.core import Config, commands, checks

from .seedream_commands import SeedreamCommands
from .archive_commands import ArchiveCommands
from .dice_commands import DiceCommands
from .response_commands import ResponseCommands
import asyncio
from datetime import datetime, timedelta
from .alt_text_commands import AltTextCommands
from .tournoi_commands import TournoiCommands
import re
import os


class RedOwlCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        dotenv.load_dotenv("/home/alexa/cogs/red_owl_cog/.env", override=True)
        default_guild = {
            "response_rules": {},
            "deaf_channels": {},
            "deaf_threads": {},
            "feur_channels": [],
            "alt_text_channels": [],
            "active_tournaments": {},
        }
        self.config.register_guild(**default_guild)
        self.archive_commands = ArchiveCommands(bot)
        self.dice_commands = DiceCommands()
        self.response_commands = ResponseCommands(self.config)
        self.alt_text_commands = AltTextCommands(bot, self.config)
        self.tournoi_commands = TournoiCommands(bot, self.config)
        self.seedream_commands = SeedreamCommands(bot)

    @commands.hybrid_command(aliases=["h"])
    async def hexa(self, ctx, num_dice: int, extra_success: int = 0):
        await self.dice_commands.hexa(ctx, num_dice, extra_success)

    @commands.hybrid_command()
    async def fate(self, ctx, bonus: int = 0):
        await self.dice_commands.fate(ctx, bonus)

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    async def response(self, ctx, user: discord.Member, keyword: str, *, response: str):
        await self.response_commands.add_response(ctx, user, keyword, response)

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    async def remove_response(self, ctx, user: discord.Member, keyword: str):
        await self.response_commands.remove_response(ctx, user, keyword)

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    async def list_responses(self, ctx):
        await self.response_commands.list_responses(ctx)

    @commands.command()
    async def feur(self, ctx):
        """Active/désactive la réponse 'feur' dans le canal actuel."""
        channel_id = str(ctx.channel.id)
        feur_channels = await self.config.guild(ctx.guild).feur_channels()

        if channel_id in feur_channels:
            feur_channels.remove(channel_id)
            await ctx.send("Réponse 'feur' désactivée dans ce canal.")
        else:
            feur_channels.append(channel_id)
            await ctx.send("Réponse 'feur' activée dans ce canal.")

        await self.config.guild(ctx.guild).feur_channels.set(feur_channels)

    async def check_quoi(self, message):
        """Vérifie si le message se termine par un son 'quoi' et répond 'feur'."""
        patterns = ["kw[ao]", "qu?[ao][yi]", "k[ao][yi]", "qu?[oô]"]

        combined_pattern = f"(?:{'|'.join(patterns)})\\s*[!?.,;]*\\s*$"

        if re.search(combined_pattern, message.content, re.IGNORECASE):
            await asyncio.sleep(1)
            try:
                msg = await message.channel.fetch_message(message.id)
                if msg:
                    await message.channel.send("feur !")
            except discord.NotFound:
                pass

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handler unique pour tous les messages."""

        if isinstance(message.channel, discord.DMChannel) and not message.author.bot:
            if await self.tournoi_commands.handle_setup_dm(message):
                return

        if message.author.bot or not message.guild:
            return

        channel_id = str(message.channel.id)
        thread_id = str(
            message.channel.id if isinstance(message.channel, discord.Thread) else ""
        )

        deaf_channels = await self.config.guild(message.guild).deaf_channels()
        deaf_threads = await self.config.guild(message.guild).deaf_threads()
        if (deaf_channels is not None and channel_id in deaf_channels) or (
            deaf_threads is not None and thread_id in deaf_threads
        ):
            return

        await self.response_commands.check_and_respond(message)

        feur_channels = await self.config.guild(message.guild).feur_channels()
        if channel_id in feur_channels:
            await self.check_quoi(message)

        alt_text_channels = await self.config.guild(message.guild).alt_text_channels()
        if channel_id in alt_text_channels and message.attachments:
            await self.alt_text_commands.generate_alt_text_for_images(message)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if reaction.message.author == self.bot.user:
            specific_emote = "TG"

            emoji_matches = False
            if isinstance(reaction.emoji, discord.Emoji):
                emoji_matches = reaction.emoji.name == specific_emote
            elif isinstance(reaction.emoji, str):
                emoji_matches = reaction.emoji == specific_emote

            if emoji_matches:
                try:
                    await reaction.message.delete()
                except discord.Forbidden:
                    print("Je n'ai pas les permissions pour supprimer ce message.")
                except discord.HTTPException as e:
                    print(f"Erreur lors de la suppression du message : {e}")

    @commands.hybrid_command()
    async def deaf(self, ctx, *, channel_or_thread=None):
        target = channel_or_thread or ctx.channel
        if isinstance(target, discord.Thread):
            deaf_targets = await self.config.guild(ctx.guild).deaf_threads()
            deaf_targets[str(target.id)] = True
            await self.config.guild(ctx.guild).deaf_threads.set(deaf_targets)
            response = f"Le bot est maintenant sourd dans le fil {target.name}."
        else:
            deaf_targets = await self.config.guild(ctx.guild).deaf_channels()
            deaf_targets[str(target.id)] = True
            await self.config.guild(ctx.guild).deaf_channels.set(deaf_targets)
            response = f"Le bot est maintenant sourd dans {target.mention}."
        await ctx.send(response)

    @commands.hybrid_command()
    async def undeaf(self, ctx, *, channel_or_thread=None):
        target = channel_or_thread or ctx.channel
        if isinstance(target, discord.Thread):
            deaf_targets = await self.config.guild(ctx.guild).deaf_threads()
            response = f"Le bot écoute maintenant à nouveau dans le fil {target.name}."
        else:
            deaf_targets = await self.config.guild(ctx.guild).deaf_channels()
            response = f"Le bot écoute maintenant à nouveau dans {target.mention}."

        if str(target.id) in deaf_targets:
            del deaf_targets[str(target.id)]
            if isinstance(target, discord.Thread):
                await self.config.guild(ctx.guild).deaf_threads.set(deaf_targets)
            else:
                await self.config.guild(ctx.guild).deaf_channels.set(deaf_targets)
            await ctx.send(response)
        else:
            await ctx.send("Ce canal ou fil n'était pas marqué comme sourd.")

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

    @commands.hybrid_command(name="transfer")
    @checks.admin_or_permissions(manage_guild=True)
    async def transfer(self, ctx: commands.Context, *, channel_link: str):
        """
        Transfère les messages d'un canal (via son lien) vers le canal actuel.

        Recrée les fils de discussion si possible. Utilisation réservée aux admins.
        Exemple: [p]transfer https://discord.com/channels/GUILD_ID/CHANNEL_ID
        """
        await self.archive_commands.transfer(ctx, channel_link)

    @commands.command(name="retranscrit_fil_txt", aliases=["transcript"])
    async def retranscrit_fil_txt(self, ctx: commands.Context, *, thread_link: str):
        """
        Retranscrit le contenu d'un fil Discord dans un fichier .txt.

        Prend en paramètre un lien direct vers le fil Discord.
        Exemple: !retranscrit_fil_txt https://discord.com/channels/123456789/987654321
        Fonctionne aussi en message privé avec le bot si le lien contient l'ID du serveur.
        """
        await ctx.typing()

        (
            file_path,
            discord_filename_or_error,
        ) = await self.archive_commands.generate_transcript_from_link(thread_link)

        if not file_path:
            await ctx.send(f":warning: Erreur : {discord_filename_or_error}")
            return

        discord_filename = discord_filename_or_error

        try:
            discord_file = discord.File(file_path, filename=discord_filename)
            await ctx.send("Voici la transcription du fil demandé :", file=discord_file)
        except discord.HTTPException as e:
            await ctx.send(
                f":warning: Erreur lors de l'envoi du fichier de transcription : {e}"
            )
        except FileNotFoundError:
            await ctx.send(
                ":warning: Erreur critique : Le fichier de transcription temporaire n'a pas pu être trouvé pour l'envoi."
            )
        except Exception as e:
            await ctx.send(
                f":warning: Une erreur inattendue est survenue lors de l'envoi du fichier : {e}"
            )
        finally:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"Temporary transcript file removed: {file_path}")
                except OSError as e:
                    print(f"Error removing temporary transcript file {file_path}: {e}")

    @commands.hybrid_command(name="tournoi")
    @commands.has_permissions(administrator=True)
    async def tournoi(self, ctx):
        """Lance la configuration d'un nouveau tournoi."""
        await self.tournoi_commands.start_tournament_setup(ctx)

    @commands.hybrid_command(name="tournoi_stop")
    @commands.has_permissions(administrator=True)
    async def tournoi_stop(self, ctx):
        """Arrête le tournoi en cours."""
        await self.tournoi_commands.stop_tournament(ctx)

    @commands.hybrid_command(name="tournoi_status")
    async def tournoi_status(self, ctx):
        """Affiche le statut du tournoi en cours."""
        await self.tournoi_commands.tournament_status(ctx)

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
