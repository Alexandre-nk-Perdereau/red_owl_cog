from redbot.core import Config, commands

from .seedream_commands import SeedreamCommands
from .dice_commands import DiceCommands
from .reminder_commands import ReminderCommands


class RedOwlCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {}
        self.config.register_guild(**default_guild)
        self.dice_commands = DiceCommands()
        self.seedream_commands = SeedreamCommands(bot)
        self.reminder_commands = ReminderCommands(bot, self.config)

    @commands.hybrid_command(aliases=["h"])
    async def hexa(self, ctx, num_dice: int, extra_success: int = 0):
        """Lance des d6 (succès sur 3+, relance sur 6)."""
        await self.dice_commands.hexa(ctx, num_dice, extra_success)

    @commands.hybrid_command()
    async def fate(self, ctx, bonus: int = 0):
        """Lance 4 dés FATE (-1, 0, +1) avec bonus optionnel."""
        await self.dice_commands.fate(ctx, bonus)

    @commands.hybrid_command(aliases=["reminder", "remindme"])
    async def remind(self, ctx, duration: str, *, message: str = "Votre rappel !"):
        """Crée un rappel (ex: 10m, 2h30m, 1d3h)."""
        await self.reminder_commands.remind(ctx, duration, message=message)

    @commands.hybrid_command()
    async def remind_repeat(self, ctx, interval: str, *, message: str = "Rappel récurrent"):
        """Crée un rappel récurrent (ex: 1h, 1d)."""
        await self.reminder_commands.remind_repeat(ctx, interval, message=message)

    @commands.hybrid_command(aliases=["reminders", "reminderlist"])
    async def remind_list(self, ctx):
        """Liste tous vos rappels actifs."""
        await self.reminder_commands.remind_list(ctx)

    @commands.hybrid_command(aliases=["remindercancel", "delreminder"])
    async def remind_cancel(self, ctx, reminder_index: int):
        """Annule un rappel spécifique."""
        await self.reminder_commands.remind_cancel(ctx, reminder_index)

    @commands.hybrid_command(aliases=["reminderclear", "clearreminders"])
    async def remind_clear(self, ctx):
        """Supprime tous vos rappels."""
        await self.reminder_commands.remind_clear(ctx)

    @commands.hybrid_command(name="gen")
    async def gen(self, ctx, *, query: str):
        """
        Génère ou édite une image avec Seedream v4 (FAL).
        Nouveaux usages:
        - !gen <prompt>                        -> taille auto
        - !gen <width> <height> <prompt>       -> taille explicite
        - Sans image -> txt2img ; Avec image(s) -> edit/img2img
        Contraintes auto: tailles ∈ [1024, 4096]
        """
        tokens = query.strip().split()
        width = height = None
        if len(tokens) >= 3 and all(t.isdigit() for t in tokens[:2]):
            try:
                width = int(tokens[0])
                height = int(tokens[1])
                prompt = " ".join(tokens[2:]).strip()
            except ValueError:
                prompt = query
        else:
            prompt = query

        await self.seedream_commands.gen(ctx, width, height, prompt=prompt)
