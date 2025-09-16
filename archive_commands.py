import discord
import asyncio
import re
from redbot.core import commands
import tempfile


class ArchiveCommands:
    def __init__(self, bot):
        self.bot = bot
        self.MESSAGE_DELAY = 1.5
        self.THREAD_DELAY = 3

    async def parse_channel_link(self, link: str):
        """Parses a Discord channel link and returns (guild_id, channel_id)."""
        match = re.match(
            r"https?://(?:ptb\.|canary\.)?discord\.com/channels/(\d+)/(\d+)/?$", link
        )
        if match:
            return int(match.group(1)), int(match.group(2))
        return None, None

    async def fetch_channel_safe(self, guild_id: int, channel_id: int):
        """Safely fetches a channel object, returning None if not found or accessible."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return None  # Bot is not in the source guild

        try:
            channel = await guild.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden):
            channel = guild.get_channel(channel_id)
            if not channel:
                return None

        if not isinstance(
            channel, (discord.TextChannel, discord.VoiceChannel, discord.ForumChannel)
        ):
            return None

        perms = channel.permissions_for(guild.me)
        if not perms.read_message_history:
            return None  # Cannot read history

        return channel

    async def transfer_message(
        self,
        message: discord.Message,
        target_channel: discord.TextChannel | discord.Thread,
    ):
        """Formats and sends a single message using an embed."""
        if not message.content and not message.attachments and not message.embeds:
            if not message.stickers:
                return None

        embed = discord.Embed(
            description=message.content if message.content else None,
            timestamp=message.created_at,
            color=message.author.color
            if message.author.color.value != 0
            else discord.Color.default(),
        )
        embed.set_author(
            name=message.author.display_name, icon_url=message.author.display_avatar.url
        )

        if message.reference and isinstance(
            message.reference.resolved, discord.Message
        ):
            reply_msg = message.reference.resolved
            reply_content = reply_msg.content[:100] + (
                "..." if len(reply_msg.content) > 100 else ""
            )
            embed.add_field(
                name=f"↪️ Répond à {reply_msg.author.display_name}",
                value=f"> {reply_content}\n> [Voir l'original]({reply_msg.jump_url})",
                inline=False,
            )
        elif message.reference:
            embed.add_field(
                name="↪️ Répond à un message",
                value="_(Message original inaccessible ou supprimé)_",
                inline=False,
            )

        if message.embeds:
            original_embed = message.embeds[0]
            embed_info = f"**Embed d'origine**"
            has_content = False
            if original_embed.title:
                embed_info += f"\n**Titre:** {original_embed.title}"
                has_content = True
            if original_embed.description:
                embed_info += f"\n**Description:** {original_embed.description[:200] + ('...' if len(original_embed.description) > 200 else '')}"
                has_content = True
            if original_embed.url:
                embed_info += f"\n**URL:** {original_embed.url}"
                has_content = True

            embed_info += f"\n[Voir l'embed complet]({message.jump_url})"
            embed.add_field(name="📊 Contenu Embarqué", value=embed_info, inline=False)

            if original_embed.image:
                embed.set_image(url=original_embed.image.url)

        attached_files = []
        if message.attachments:
            first_image = next(
                (
                    att
                    for att in message.attachments
                    if att.content_type and att.content_type.startswith("image/")
                ),
                None,
            )
            if first_image and not embed.image:
                embed.set_image(url=first_image.url)

            attachment_texts = []
            for i, att in enumerate(message.attachments):
                if (
                    att == first_image
                    and embed.image
                    and embed.image.url == first_image.url
                ):
                    continue

                try:
                    if att.size < 8 * 1024 * 1024:  # 8 MiB
                        attached_files.append(await att.to_file())
                    else:
                        attachment_texts.append(
                            f"- [{att.filename}]({att.url}) (Fichier trop volumineux > 8MB)"
                        )
                except discord.HTTPException as e:
                    attachment_texts.append(
                        f"- {att.filename} (Erreur téléchargement: {e})"
                    )
                except Exception as e:
                    attachment_texts.append(f"- {att.filename} (Erreur inconnue: {e})")

            if attachment_texts:
                embed.add_field(
                    name="📎 Autres Pièces Jointes",
                    value="\n".join(attachment_texts),
                    inline=False,
                )

        if message.stickers:
            sticker_names = [sticker.name for sticker in message.stickers]
            embed.add_field(
                name="✨ Stickers", value=", ".join(sticker_names), inline=False
            )
            if not embed.image and message.stickers[0].url:
                embed.set_image(url=message.stickers[0].url)

        if embed.description and len(embed.description) > 4000:
            embed.description = embed.description[:4000] + "...\n*(Message tronqué)*"

        if (
            not embed.description
            and not embed.fields
            and not embed.image
            and not message.stickers
        ):
            if attached_files:
                sent_message = await target_channel.send(files=attached_files)
                return sent_message
            else:
                return None

        try:
            sent_message = await target_channel.send(
                embed=embed, files=attached_files if attached_files else None
            )
            return sent_message
        except discord.HTTPException as e:
            await target_channel.send(
                f"> :warning: Échec du transfert du message {message.jump_url}. Erreur: {e}"
            )
            return None

    async def transfer(self, ctx: commands.Context, channel_link: str):
        """
        Transfère les messages d'un canal vers le canal actuel.

        Prend en argument un lien vers le canal source.
        Exemple: `!transfer https://discord.com/channels/123456789012345678/987654321098765432`

        Attention: Cette opération peut être longue.
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
                "Impossible de trouver ou d'accéder au canal source. Vérifiez le lien et assurez-vous que :\n"
                "- Le bot est présent sur le serveur source.\n"
                "- Le bot a la permission de 'Voir le canal' et 'Lire l'historique des messages' dans le canal source."
            )
            return

        destination_channel = ctx.channel
        if not isinstance(destination_channel, (discord.TextChannel, discord.Thread)):
            await ctx.send(
                "Cette commande ne peut être utilisée que dans un canal textuel ou un fil de discussion."
            )
            return

        dest_perms = destination_channel.permissions_for(ctx.guild.me)
        missing_perms = []
        if not dest_perms.send_messages:
            missing_perms.append("Envoyer des messages")
        if (
            isinstance(destination_channel, discord.TextChannel)
            and not dest_perms.create_public_threads
        ):
            missing_perms.append(
                "Créer des fils publics"
            )  # Even private source threads become public
        if not dest_perms.send_messages_in_threads:
            missing_perms.append("Envoyer des messages dans les fils")
        if not dest_perms.embed_links:
            missing_perms.append("Intégrer des liens (pour les embeds)")
        if not dest_perms.attach_files:
            missing_perms.append("Joindre des fichiers")

        if missing_perms:
            await ctx.send(
                f"Le bot n'a pas les permissions nécessaires dans le canal de destination **{destination_channel.name}**: "
                f"{', '.join(missing_perms)}."
            )
            return

        confirm_message = await ctx.send(
            f"Vous êtes sur le point de transférer **tous** les messages et fils accessibles par le bot depuis {source_channel.mention} "
            f"(Serveur: `{source_channel.guild.name}`) vers {destination_channel.mention}.\n"
            f"Les fils privés source deviendront **publics** dans la destination.\n"
            f"Cela peut prendre beaucoup de temps et ne peut pas être annulé facilement.\n"
            f"Réagissez avec ✅ pour confirmer dans les 30 secondes."
        )
        await confirm_message.add_reaction("✅")
        await confirm_message.add_reaction("❌")

        def check(reaction, user):
            return (
                user == ctx.author
                and str(reaction.emoji) in ["✅", "❌"]
                and reaction.message.id == confirm_message.id
            )

        try:
            reaction, user = await self.bot.wait_for(
                "reaction_add", timeout=30.0, check=check
            )
        except asyncio.TimeoutError:
            await confirm_message.edit(content="Confirmation expirée.", delete_after=10)
            return
        else:
            if str(reaction.emoji) == "❌":
                await confirm_message.edit(content="Transfert annulé.", delete_after=10)
                return
            try:
                await confirm_message.delete()
            except discord.HTTPException:
                pass

        status_message = await ctx.send(
            f"⏳ Début du transfert depuis {source_channel.mention}..."
        )
        msg_count = 0
        thread_base_count = 0
        thread_extra_count = 0
        error_count = 0
        processed_thread_ids = set()

        try:
            async for message in source_channel.history(limit=None, oldest_first=True):
                msg_count += 1
                sent_bot_message = None
                try:
                    sent_bot_message = await self.transfer_message(
                        message, destination_channel
                    )
                    await asyncio.sleep(self.MESSAGE_DELAY)

                    if message.thread:
                        source_thread = message.thread
                        processed_thread_ids.add(source_thread.id)

                        source_thread_perms = source_thread.permissions_for(
                            source_thread.guild.me
                        )
                        if not source_thread_perms.read_message_history:
                            await ctx.send(
                                f"> :warning: Impossible de lire l'historique du fil public {source_thread.mention} ({source_thread.name}). Il sera ignoré."
                            )
                            error_count += 1
                            continue

                        target_thread = None
                        if sent_bot_message:
                            try:
                                target_thread = await sent_bot_message.create_thread(
                                    name=f"{source_thread.name}"
                                )
                                thread_base_count += 1
                                await status_message.edit(
                                    content=f"⏳ Transfert principal... Message {msg_count}, Fil {thread_base_count} créé: {target_thread.name}"
                                )
                                await asyncio.sleep(self.THREAD_DELAY)
                            except discord.HTTPException as thread_e:
                                await ctx.send(
                                    f"> :warning: Impossible de créer le fil pour le message {message.jump_url}: {thread_e}"
                                )
                                error_count += 1
                            except discord.Forbidden:
                                await ctx.send(
                                    f"> :warning: Permission refusée pour créer un fil pour le message {message.jump_url}."
                                )
                                error_count += 1
                        else:
                            await ctx.send(
                                f"> :information_source: Le message original {message.jump_url} (qui avait un fil) a été sauté ou a échoué, impossible de créer le fil correspondant lié."
                            )
                            error_count += 1

                        if target_thread:
                            thread_msg_count = 0
                            async for thread_message in source_thread.history(
                                limit=None, oldest_first=True
                            ):
                                thread_msg_count += 1
                                try:
                                    await self.transfer_message(
                                        thread_message, target_thread
                                    )
                                    await asyncio.sleep(self.MESSAGE_DELAY)
                                except Exception as e_thread:
                                    error_count += 1
                                    try:
                                        await target_thread.send(
                                            f"> :warning: Erreur transfert message de fil {thread_message.jump_url}: {e_thread}"
                                        )
                                    except discord.HTTPException:
                                        pass
                                if thread_msg_count % 20 == 0:
                                    await status_message.edit(
                                        content=f"⏳ Transfert principal... Message {msg_count}, Fil {target_thread.name} ({thread_msg_count} messages)"
                                    )

                except Exception as e_msg:
                    error_count += 1
                    await ctx.send(
                        f"> :warning: Erreur lors du traitement du message principal {message.jump_url}: {e_msg}"
                    )

                if msg_count % 20 == 0:
                    await status_message.edit(
                        content=f"⏳ Transfert principal... {msg_count} messages traités."
                    )

            await status_message.edit(
                content=f"✅ Transfert principal terminé ({msg_count} messages). Recherche d'autres fils..."
            )

        except discord.Forbidden:
            await status_message.edit(
                content=f"❌ Erreur: Le bot n'a pas les permissions suffisantes pour lire l'historique du canal source ({source_channel.mention})."
            )
            return
        except discord.HTTPException as http_e:
            await status_message.edit(
                content=f"❌ Erreur HTTP majeure pendant le transfert principal: {http_e}. Le transfert est interrompu."
            )
            return
        except Exception as e:
            await status_message.edit(
                content=f"❌ Une erreur inattendue est survenue pendant le transfert principal: {e}. Tentative de transfert des fils restants..."
            )
            error_count += 1

        await status_message.edit(
            content=f"⏳ Recherche des fils actifs et archivés dans {source_channel.mention}..."
        )

        all_source_threads = []
        all_source_threads.extend(source_channel.threads)

        try:
            async for thread in source_channel.archived_threads(limit=None):
                all_source_threads.append(thread)
        except discord.Forbidden:
            await ctx.send(
                f"> :warning: Le bot n'a pas la permission de voir les fils archivés dans {source_channel.mention}."
            )
        except discord.HTTPException as e:
            await ctx.send(
                f"> :warning: Erreur HTTP lors de la récupération des fils archivés: {e}"
            )
        except AttributeError:
            await ctx.send(
                f"> :information_source: Le type de canal {type(source_channel).__name__} ne supporte pas la récupération de fils archivés."
            )
        except Exception as e:
            await ctx.send(
                f"> :warning: Erreur inattendue lors de la récupération des fils archivés: {e}"
            )

        await status_message.edit(
            content=f"⏳ Transfert des {len(all_source_threads)} fils trouvés (actifs et archivés)..."
        )
        processed_in_phase2 = 0

        for source_thread in all_source_threads:
            if source_thread.id in processed_thread_ids:
                continue

            processed_in_phase2 += 1
            processed_thread_ids.add(source_thread.id)

            try:
                perms = source_thread.permissions_for(source_channel.guild.me)
                if not perms.read_message_history:
                    await ctx.send(
                        f"> :warning: Ne peut pas lire l'historique du fil '{source_thread.name}' ({source_thread.mention}). Il sera ignoré."
                    )
                    error_count += 1
                    continue
            except Exception as e:
                await ctx.send(
                    f"> :warning: Erreur de vérification des permissions pour le fil '{source_thread.name}': {e}. Il sera ignoré."
                )
                error_count += 1
                continue

            target_thread = None
            try:
                placeholder_msg = await destination_channel.send(
                    f"🧵 Transfert du fil: **{source_thread.name}** (Original: {source_thread.mention})"
                )
                target_thread = await destination_channel.create_thread(
                    name=f"{source_thread.name}", message=placeholder_msg
                )
                thread_extra_count += 1
                await status_message.edit(
                    content=f"⏳ Transfert des fils... Fil {thread_extra_count}/{processed_in_phase2} créé: {target_thread.name}"
                )
                await asyncio.sleep(self.THREAD_DELAY)
            except discord.HTTPException as thread_e:
                await ctx.send(
                    f"> :warning: Impossible de créer le fil de destination pour '{source_thread.name}': {thread_e}"
                )
                error_count += 1
                continue
            except discord.Forbidden:
                await ctx.send(
                    f"> :warning: Permission refusée pour créer des fils dans {destination_channel.mention}. Arrêt du transfert des fils restants."
                )
                error_count += 1
                break
            except Exception as e:
                await ctx.send(
                    f"> :warning: Erreur inattendue lors de la création du fil pour '{source_thread.name}': {e}"
                )
                error_count += 1
                continue
            if target_thread:
                thread_msg_count = 0
                async for thread_message in source_thread.history(
                    limit=None, oldest_first=True
                ):
                    thread_msg_count += 1
                    try:
                        await self.transfer_message(thread_message, target_thread)
                        await asyncio.sleep(self.MESSAGE_DELAY)
                    except Exception as e_thread:
                        error_count += 1
                        try:
                            await target_thread.send(
                                f"> :warning: Erreur transfert message de fil {thread_message.jump_url}: {e_thread}"
                            )
                        except discord.HTTPException:
                            pass
                    if thread_msg_count % 20 == 0:
                        await status_message.edit(
                            content=f"⏳ Transfert des fils... Fil {target_thread.name} ({thread_msg_count} messages)"
                        )

        final_message = (
            f"✅ Transfert terminé !\n"
            f"- **{msg_count}** messages principaux transférés.\n"
            f"- **{thread_base_count}** fils liés aux messages transférés.\n"
            f"- **{thread_extra_count}** autres fils (actifs/archivés, publics/privés) transférés.\n"
            f"- Source: {source_channel.mention} (Serveur: `{source_channel.guild.name}`)\n"
            f"- Destination: {destination_channel.mention}\n"
        )
        if error_count > 0:
            final_message += f"\n⚠️ **{error_count}** erreurs rencontrées pendant le processus. Certains messages ou fils ont pu être manqués ou incomplets."
        else:
            final_message += f"\n✨ Transfert complété sans erreurs apparentes."

        await status_message.edit(content=final_message)

    async def parse_thread_link(self, link: str):
        """Tente d'extraire l'ID du serveur et l'ID du fil d'un lien Discord."""
        # Format: https://discord.com/channels/GUILD_ID/THREAD_ID
        # Ou     https://discord.com/channels/GUILD_ID/CHANNEL_ID/THREAD_ID
        match = re.match(
            r"https?://(?:ptb\.|canary\.)?discord\.com/channels/(\d+)/(\d+)(?:/\d+)?/?$",
            link,
        )
        if match:
            # Si 3 groupes, le dernier est le thread ID, l'avant-dernier le channel ID
            # Si 2 groupes, le dernier est le thread ID, l'avant-dernier le guild ID
            # On suppose que le lien pointe directement vers le fil (format le plus courant)
            # Donc, le premier groupe est GUILD_ID, le second est THREAD_ID
            # NOTE: Cette heuristique peut échouer si le lien est un lien de *message* dans un fil.
            # Une approche plus robuste nécessiterait de vérifier le type d'objet retourné par fetch.
            # Pour la transcription, nous avons besoin de Guild ID et Thread ID.
            guild_id = int(match.group(1))
            thread_id = int(match.group(2))
            # Tentative de vérification : Si le deuxième ID semble être un canal plutôt qu'un fil...
            # (Cette partie est complexe et potentiellement peu fiable sans accès à l'API Discord pour vérifier le type)
            # On va partir du principe que le lien est /GUILD_ID/THREAD_ID
            return guild_id, thread_id
        return None, None

    async def fetch_thread_safe(self, guild_id: int, thread_id: int):
        """Récupère un objet Thread de manière sécurisée."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            print(f"Fetch Thread: Bot not in guild {guild_id}")
            return (
                None,
                f"Le bot n'est pas membre du serveur (ID: {guild_id}) contenant ce fil.",
            )

        try:
            # Tenter de récupérer le fil via l'API (plus fiable)
            thread = await guild.fetch_channel(
                thread_id
            )  # fetch_channel peut aussi récupérer des fils
            if not isinstance(thread, discord.Thread):
                # Si ce n'est pas un fil, peut-être que le lien était mal interprété (channel/thread)
                # Essayons de le trouver dans le cache du guild
                thread = guild.get_thread(thread_id)
                if not thread:
                    return (
                        None,
                        f"Impossible de trouver un fil avec l'ID {thread_id} sur le serveur '{guild.name}'. Le lien est-il correct ?",
                    )

        except discord.NotFound:
            # Essayer de le trouver dans le cache du guild s'il n'est pas trouvé via fetch
            thread = guild.get_thread(thread_id)
            if not thread:
                print(
                    f"Fetch Thread: Thread {thread_id} not found in guild {guild.name}"
                )
                return (
                    None,
                    f"Impossible de trouver le fil (ID: {thread_id}) sur le serveur '{guild.name}'. Vérifiez le lien.",
                )
        except discord.Forbidden:
            print(
                f"Fetch Thread: Forbidden to fetch thread {thread_id} in guild {guild.name}"
            )
            return (
                None,
                f"Le bot n'a pas la permission de voir le fil (ID: {thread_id}) sur le serveur '{guild.name}'.",
            )
        except Exception as e:
            print(
                f"Fetch Thread: Unexpected error fetching thread {thread_id} in guild {guild.name}: {e}"
            )
            return (
                None,
                f"Une erreur inattendue est survenue lors de la récupération du fil : {e}",
            )

        # Vérifier les permissions de lecture dans le fil
        perms = thread.permissions_for(guild.me)
        if not perms.read_message_history:
            print(
                f"Fetch Thread: Missing read_message_history for thread {thread.name} ({thread_id})"
            )
            return (
                None,
                f"Le bot n'a pas la permission de 'Lire l'historique des messages' dans le fil '{thread.name}'.",
            )

        return thread, None  # Retourne le fil et pas de message d'erreur

    async def create_thread_transcript(self, thread: discord.Thread):
        """Génère une chaîne de caractères formatée à partir de l'historique d'un fil."""
        transcript_lines = []
        transcript_lines.append(
            f"--- Début de la transcription du fil: {thread.name} ({thread.id}) ---"
        )
        transcript_lines.append(
            f"--- Serveur: {thread.guild.name} ({thread.guild.id}) ---"
        )
        transcript_lines.append(
            f"--- Créé le: {thread.created_at.strftime('%d/%m/%Y %H:%M:%S UTC')} ---"
        )
        transcript_lines.append("\n" + "=" * 30 + "\n")

        message_count = 0
        try:
            async for message in thread.history(limit=None, oldest_first=True):
                message_count += 1
                author_name = message.author.display_name
                timestamp = message.created_at.strftime("%d/%m/%Y %H:%M")
                content = message.content if message.content else ""

                # line = f"[{timestamp}] {author_name}: {content}"
                line = f"{author_name}: {content}"
                transcript_lines.append(line)

                if message.attachments:
                    attachment_info = f"  ({len(message.attachments)} fichier(s) joint(s): {', '.join(a.filename for a in message.attachments)})"
                    transcript_lines.append(attachment_info)

                if message.embeds:
                    # Simple indication qu'il y a des embeds, le contenu est trop complexe pour le txt
                    transcript_lines.append("  (Contenu embarqué présent)")

                if message.stickers:
                    sticker_info = (
                        f"  (Sticker(s): {', '.join(s.name for s in message.stickers)})"
                    )
                    transcript_lines.append(sticker_info)

                # Ajouter un petit séparateur entre les messages pour la lisibilité
                transcript_lines.append("")  # Ligne vide

                # Petite pause pour éviter le rate limiting sur de très longs fils
                if message_count % 50 == 0:
                    await asyncio.sleep(0.1)

        except discord.Forbidden:
            transcript_lines.append(
                "\nERREUR: Le bot a perdu la permission de lire l'historique pendant la transcription."
            )
            return "\n".join(transcript_lines)  # Retourne ce qu'on a pu obtenir
        except Exception as e:
            transcript_lines.append(
                f"\nERREUR inattendue pendant la lecture de l'historique: {e}"
            )
            return "\n".join(transcript_lines)

        transcript_lines.append("=" * 30)
        transcript_lines.append(
            f"--- Fin de la transcription ({message_count} message(s)) ---"
        )
        return "\n".join(transcript_lines)

    async def generate_transcript_from_link(self, thread_link: str):
        """Orchestre la création d'un fichier de transcription à partir d'un lien de fil."""
        guild_id, thread_id = await self.parse_thread_link(thread_link)
        if not guild_id or not thread_id:
            return (
                None,
                "Le lien fourni n'est pas un lien de fil Discord valide ou reconnaissable (format attendu: .../channels/SERVEUR_ID/FIL_ID).",
            )

        thread, error_msg = await self.fetch_thread_safe(guild_id, thread_id)
        if error_msg:
            return None, error_msg
        if not thread:
            return None, "Erreur inconnue lors de la récupération du fil."  # Sécurité

        # Créer le contenu texte de la transcription
        transcript_content = await self.create_thread_transcript(thread)

        # Créer un fichier temporaire pour stocker la transcription
        try:
            # Utiliser delete=False pour pouvoir envoyer le fichier avant qu'il soit supprimé
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".txt", delete=False
            ) as temp_file:
                temp_file.write(transcript_content)
                file_path = temp_file.name  # Récupérer le chemin du fichier temporaire

            # Préparer le nom du fichier pour Discord
            # Remplacer les caractères non autorisés dans les noms de fichiers
            safe_thread_name = re.sub(r'[\\/*?:"<>|]', "", thread.name)
            discord_filename = f"transcription_{safe_thread_name[:50]}_{thread.id}.txt"

            return (
                file_path,
                discord_filename,
            )  # Retourne le chemin local et le nom pour Discord

        except Exception as e:
            print(f"Generate Transcript: Error creating temp file: {e}")
            return (
                None,
                f"Une erreur est survenue lors de la création du fichier de transcription : {e}",
            )
