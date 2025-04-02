from redbot.core.bot import Red
from .red_owl_cog import RedOwlCog
from dotenv import load_dotenv

async def setup(bot: Red):
    load_dotenv()
    await bot.add_cog(RedOwlCog(bot))