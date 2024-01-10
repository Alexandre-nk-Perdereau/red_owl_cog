from redbot.core.bot import Red
from .red_owl_cog import RedOwlCog

async def setup(bot: Red) -> None:
    """Load hexadice cog."""
    cog = RedOwlCog(bot)
    await bot.add_cog(cog)