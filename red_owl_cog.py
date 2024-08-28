import discord
from redbot.core import Config, commands
from .dice_commands import DiceCommands
from .response_commands import ResponseCommands
import asyncio
from datetime import datetime, timedelta
from .archive_commands import ArchiveCommands


class RedOwlCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "response_rules": {},
            "deaf_channels": {},
            "deaf_threads": {},
        }
        self.config.register_guild(**default_guild)
        self.archive_commands = ArchiveCommands(bot)
        self.dice_commands = DiceCommands()
        self.response_commands = ResponseCommands(self.config)

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

    @commands.Cog.listener()
    async def on_message(self, message):
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
    async def archive_thread(self, ctx, thread_url: str):
        await self.archive_commands.archive_thread(ctx, thread_url)

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    async def archive_channel(self, ctx, channel: discord.TextChannel):
        await self.archive_commands.archive_channel(ctx, channel)
