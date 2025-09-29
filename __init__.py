from redbot.core.bot import Red
from .red_owl_cog import RedOwlCog


async def setup(bot: Red):
    await bot.add_cog(RedOwlCog(bot))
