
import discord
import asyncio
import re
from redbot.core import commands

class ArchiveCommands:
    def __init__(self, bot):
        self.bot = bot
        # Rate limit: Discord allows 5 operations per second per channel roughly.
        # Let's be conservative: 1 message every 1.5 seconds.
        self.MESSAGE_DELAY = 1.5 
        self.THREAD_DELAY = 3 # Extra delay when creating threads

    async def parse_channel_link(self, link: str):
        """Parses a Discord channel link and returns (guild_id, channel_id)."""
        match = re.match(r"https?://(?:ptb\.|canary\.)?discord\.com/channels/(\d+)/(\d+)/?$", link)
        if match:
            return int(match.group(1)), int(match.group(2))
        return None, None

    async def fetch_channel_safe(self, guild_id: int, channel_id: int):
        """Safely fetches a channel object, returning None if not found or accessible."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return None # Bot is not in the source guild

        channel = guild.get_channel(channel_id)
        if not channel or not isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.ForumChannel)):
             # Added Voice/ForumChannel as potential sources, though TextChannel is primary
            return None # Channel not found or not a text-based channel we can read history from

        # Check permissions
        perms = channel.permissions_for(guild.me)
        if not perms.read_message_history:
            return None # Cannot read history

        return channel

    async def transfer_message(self, message: discord.Message, target_channel: discord.TextChannel | discord.Thread):
        """Formats and sends a single message using an embed."""
        if not message.content and not message.attachments and not message.embeds:
            # Skip empty messages (e.g., system messages we might not want)
            return None # Return None to indicate nothing was sent (for potential thread creation later)

        embed = discord.Embed(
            description=message.content if message.content else None,
            timestamp=message.created_at,
            color=message.author.color if message.author.color.value != 0 else discord.Color.default()
        )
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        
        # Handle potential original embeds (take the first one if it exists)
        if message.embeds:
             original_embed = message.embeds[0]
             # We could try to replicate fields, but let's just link it for simplicity/fidelity
             embed.add_field(name="Embed Original", value=f"[Voir l'embed original]({message.jump_url})", inline=False)
             if original_embed.image:
                 embed.set_image(url=original_embed.image.url) # Try to capture the main image

        # Handle Attachments
        attached_files = []
        if message.attachments:
            # Try to display the first image directly if possible
            first_image = next((att for att in message.attachments if att.content_type and att.content_type.startswith('image/')), None)
            if first_image and not embed.image: # Only set if not already set by original embed
                 embed.set_image(url=first_image.url)
            
            # List other attachments or all if first wasn't image
            attachment_texts = []
            for i, att in enumerate(message.attachments):
                 # Don't list the first image if we already set it via set_image
                 if att == first_image and embed.image and embed.image.url == first_image.url:
                     continue
                 
                 # Prepare files for re-uploading (be mindful of Discord's size limits)
                 try:
                    # Limit file size to prevent errors (e.g., < 8MB)
                    if att.size < 8_000_000: 
                        attached_files.append(await att.to_file())
                    else:
                        attachment_texts.append(f"- {att.filename} (Fichier trop volumineux > 8MB)")
                 except Exception as e:
                     attachment_texts.append(f"- {att.filename} (Erreur téléchargement: {e})")

            if attachment_texts:
                 embed.add_field(name="Autres Pièces Jointes", value="\n".join(attachment_texts), inline=False)
        
        # Handle potential message length issues in description (though embed description limit is higher)
        if embed.description and len(embed.description) > 4000: # Embed description limit is 4096
            embed.description = embed.description[:4000] + "...\n(Message tronqué)"
            
        # Ensure the embed isn't entirely empty
        if not embed.description and not embed.fields and not embed.image:
             if attached_files: # If only files, send files without embed
                  sent_message = await target_channel.send(files=attached_files)
                  return sent_message
             else: # Truly empty, skip
                  return None
        
        try:
            sent_message = await target_channel.send(embed=embed, files=attached_files if attached_files else None)
            return sent_message
        except discord.HTTPException as e:
            # Handle potential errors like invalid embed data or file upload issues
            await target_channel.send(f"> :warning: Erreur lors du transfert du message {message.jump_url}: {e}")
            return None


    async def transfer(self, ctx: commands.Context, channel_link: str):
        """
        Transfère les messages d'un canal vers le canal actuel.

        Prend en argument un lien vers le canal source.
        Exemple: `!transfer https://discord.com/channels/123456789012345678/987654321098765432`

        Attention: Cette opération peut être longue et consommer beaucoup de ressources.
        Le bot doit être présent sur le serveur source et avoir les permissions de lecture.
        Les threads seront recréés dans le canal actuel.
        """
        await ctx.typing()

        guild_id, channel_id = await self.parse_channel_link(channel_link)

        if not guild_id or not channel_id:
            await ctx.send("Le lien fourni n'est pas un lien de canal Discord valide.")
            return

        source_channel = await self.fetch_channel_safe(guild_id, channel_id)

        if not source_channel:
            await ctx.send(
                "Impossible de trouver le canal source. Vérifiez le lien et assurez-vous que "
                "le bot est présent sur le serveur source et a la permission de lire l'historique de ce canal."
            )
            return

        destination_channel = ctx.channel
        if not isinstance(destination_channel, (discord.TextChannel, discord.Thread)):
            await ctx.send("Cette commande ne peut être utilisée que dans un canal textuel ou un fil de discussion.")
            return
        
        # Check destination permissions
        dest_perms = destination_channel.permissions_for(ctx.guild.me)
        missing_perms = []
        if not dest_perms.send_messages:
            missing_perms.append("Envoyer des messages")
        if isinstance(destination_channel, discord.TextChannel) and not dest_perms.create_public_threads:
             # Assuming public threads for simplicity. Add check for private if needed.
            missing_perms.append("Créer des fils publics")
        if not dest_perms.send_messages_in_threads:
             missing_perms.append("Envoyer des messages dans les fils")
        if not dest_perms.embed_links:
             missing_perms.append("Intégrer des liens (pour les embeds)")
        if not dest_perms.attach_files:
             missing_perms.append("Joindre des fichiers")

        if missing_perms:
            await ctx.send(f"Le bot n'a pas les permissions nécessaires dans le canal de destination **{destination_channel.name}**: "
                         f"{', '.join(missing_perms)}.")
            return

        # Confirmation
        confirm_message = await ctx.send(
            f"Vous êtes sur le point de transférer **tous** les messages de {source_channel.mention} "
            f"(Serveur: `{source_channel.guild.name}`) vers {destination_channel.mention}.\n"
            f"Cela peut prendre beaucoup de temps et ne peut pas être annulé facilement.\n"
            f"Réagissez avec ✅ pour confirmer dans les 30 secondes."
        )
        await confirm_message.add_reaction("✅")
        await confirm_message.add_reaction("❌")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == confirm_message.id

        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await confirm_message.edit(content="Confirmation expirée.", delete_after=10)
            return
        else:
            if str(reaction.emoji) == "❌":
                await confirm_message.edit(content="Transfert annulé.", delete_after=10)
                return
            await confirm_message.delete() # Remove confirmation message

        # Start transfer
        status_message = await ctx.send(f"⏳ Début du transfert depuis {source_channel.mention}...")
        count = 0
        thread_count = 0
        error_count = 0

        try:
            async for message in source_channel.history(limit=None, oldest_first=True):
                count += 1
                sent_bot_message = None # Keep track of the message the bot sent
                try:
                    sent_bot_message = await self.transfer_message(message, destination_channel)
                    await asyncio.sleep(self.MESSAGE_DELAY) # RATE LIMIT

                    # --- Thread Handling ---
                    if message.thread:
                        source_thread = message.thread
                        # Check permissions for the source thread too
                        thread_perms = source_thread.permissions_for(source_thread.guild.me)
                        if thread_perms.read_message_history:
                            
                            target_thread = None
                            if sent_bot_message: # Only create thread if the parent message was successfully sent
                                try:
                                    # Use the name of the original thread
                                    target_thread = await sent_bot_message.create_thread(name=source_thread.name)
                                    thread_count += 1
                                    await status_message.edit(content=f"⏳ Transfert en cours... Message {count}, Fil {thread_count} créé: {target_thread.name}")
                                    await asyncio.sleep(self.THREAD_DELAY) # Extra delay for thread creation
                                except discord.HTTPException as thread_e:
                                     await ctx.send(f"> :warning: Impossible de créer le fil pour le message {message.jump_url}: {thread_e}")
                                     error_count +=1
                            else:
                                 await ctx.send(f"> :information_source: Le message original {message.jump_url} a été sauté ou a échoué, impossible de créer le fil correspondant.")


                            if target_thread:
                                thread_msg_count = 0
                                async for thread_message in source_thread.history(limit=None, oldest_first=True):
                                    thread_msg_count +=1
                                    try:
                                        await self.transfer_message(thread_message, target_thread)
                                        await asyncio.sleep(self.MESSAGE_DELAY) # RATE LIMIT within thread
                                    except Exception as e_thread:
                                        error_count += 1
                                        await target_thread.send(f"> :warning: Erreur transfert message de fil {thread_message.jump_url}: {e_thread}")
                                    if thread_msg_count % 20 == 0: # Update status less frequently for threads
                                        await status_message.edit(content=f"⏳ Transfert en cours... Message {count}, Fil {target_thread.name} ({thread_msg_count} messages)")
                        else:
                            await ctx.send(f"> :warning: Le bot n'a pas la permission de lire l'historique du fil {source_thread.mention} ({source_thread.name}). Il sera ignoré.")
                            error_count +=1

                except Exception as e_msg:
                    error_count += 1
                    await ctx.send(f"> :warning: Erreur lors du traitement du message {message.jump_url}: {e_msg}")
                
                if count % 20 == 0: # Update status every 20 messages
                     await status_message.edit(content=f"⏳ Transfert en cours... {count} messages traités.")

            await status_message.edit(content=f"✅ Transfert terminé ! {count} messages et {thread_count} fils transférés depuis {source_channel.mention} vers {destination_channel.mention}. {error_count} erreurs rencontrées.")

        except discord.Forbidden:
            await status_message.edit(content=f"❌ Erreur: Le bot n'a pas les permissions suffisantes sur le canal source ({source_channel.mention}) ou destination ({destination_channel.mention}).")
            error_count +=1
        except discord.HTTPException as http_e:
             await status_message.edit(content=f"❌ Erreur HTTP majeure: {http_e}. Le transfert a peut-être été interrompu.")
             error_count +=1
        except Exception as e:
            await status_message.edit(content=f"❌ Une erreur inattendue est survenue: {e}")
            error_count +=1
        finally:
             # Send a final summary if errors occurred
             if error_count > 0:
                 await ctx.send(f"⚠️ Le transfert s'est terminé avec {error_count} erreurs. Certains messages ou fils ont pu être manqués.")
