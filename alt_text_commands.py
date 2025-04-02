      
import discord
import google.generativeai as genai
import os
from redbot.core import commands, Config
import asyncio
import tempfile

class AltTextCommands:
    """Commandes pour générer du texte alternatif pour les images."""

    def __init__(self, bot, config):
        self.bot = bot
        self.config = config
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.alt_default_model = os.getenv("ALT_DEFAULT_MODEL", "gemini-2.0-flash-exp")
        genai.configure(api_key=self.gemini_api_key)

    async def activate_image_alt_text(self, ctx):
        """Active/désactive la génération de texte alternatif pour les images dans ce canal."""
        channel_id = str(ctx.channel.id)
        alt_text_channels = await self.config.guild(ctx.guild).alt_text_channels()

        if channel_id in alt_text_channels:
            alt_text_channels.remove(channel_id)
            await ctx.send("Génération de texte alternatif désactivée pour ce canal.")
        else:
            alt_text_channels.append(channel_id)
            await ctx.send("Génération de texte alternatif activée pour ce canal.")

        await self.config.guild(ctx.guild).alt_text_channels.set(alt_text_channels)

    async def generate_alt_text_for_images(self, message):
        """Génère du texte alternatif pour les images dans un message."""
        model = genai.GenerativeModel(self.alt_default_model)

        for attachment in message.attachments:
            if attachment.content_type.startswith('image/'):
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{attachment.filename.split('.')[-1]}") as temp_image:
                    await attachment.save(temp_image.name)

                image = genai.upload_file(temp_image.name)

                try:
                    response = model.generate_content(["Décrivez cette image:", image])
                    alt_text = response.text
                    await message.channel.send(f"Texte alternatif pour {attachment.filename}: {alt_text}")
                except Exception as e:
                    await message.channel.send(f"Erreur lors de la génération du texte alternatif pour {attachment.filename}: {e}")
                finally:
                    os.unlink(temp_image.name)