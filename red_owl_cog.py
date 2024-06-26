import asyncio
import base64
import io
import time
import aiohttp
import logging
import random
from datetime import datetime, timedelta
import os
import tempfile
import json
import speech_recognition as sr
from pydub import AudioSegment

import discord
from redbot.core import Config, commands


class RedOwlCog(commands.Cog):
    """Red Owl Cog"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "response_rules": {},
            "deaf_channels": {},
            "deaf_threads": {},
        }
        self.config.register_guild(**default_guild)
        self.logger = logging.getLogger("red.mycog.RedOwlCog")

    @commands.hybrid_command(aliases=["h"])
    async def hexa(self, ctx, num_dice: int, extra_success: int = 0):
        """Rolls dice and counts successes, with optional extra successes"""
        if num_dice < 1:
            await ctx.send("Number of dices must be at least 1")
            return
        if num_dice > 100:
            await ctx.send("Number of dices must be at maximum 100")
            return

        rolls, success = self.roll_dices(num_dice)
        initial_success = success
        success += extra_success

        # Création de l'embed
        embed = discord.Embed(title="🎲 Résultat des lancers", color=0x4CAF50)
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar.url)

        success_text = f"**{initial_success}** succès"
        if extra_success != 0:
            success_text += (
                f" + **{extra_success}** succès supplémentaires = **{success}** total"
            )
        embed.add_field(name="🏆 Succès", value=success_text, inline=False)

        # Formatage des résultats des lancers pour l'affichage
        detailed_rolls = " \n ".join(
            f"🎲 Lancer {i+1}: " + ", ".join(self.format_roll(r) for r in roll)
            for i, roll in enumerate(rolls)
        )
        embed.add_field(name="Détail des lancers", value=detailed_rolls, inline=False)
        embed.set_footer(text=f"Demandé par {ctx.author.display_name}")

        # Envoi de l'embed
        await ctx.send(embed=embed)
        self.logger.info(
            f"{ctx.author.display_name} {success_text} \n {detailed_rolls}"
        )

    def roll_dices(self, num_dice: int):
        num_faces = 6
        rolls = []
        success = 0

        while num_dice > 0:
            roll = [random.randint(1, num_faces) for _ in range(num_dice)]
            roll.sort(reverse=True)
            rolls.append(roll)
            num_dice = roll.count(6)
            success += sum(r >= 3 for r in roll)

        return rolls, success

    def format_roll(self, roll):
        if roll == 6:
            return f"**{roll}**"
        return str(roll)

    @commands.hybrid_command()
    async def fate(self, ctx, bonus: int = 0):
        """Rolls 4 Fate dice and applies an optional bonus."""
        dice = [-1, 0, 1]  # Possible values for each Fate die
        rolls = [random.choice(dice) for _ in range(4)]  # Roll 4 dice
        total = sum(rolls) + bonus  # Calculate the total by adding the bonus

        # Create an embed to display the result
        embed = discord.Embed(title="🎲 Résultat du lancer Fate", color=0x4CAF50)
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar.url)

        # Display the roll details
        roll_details = " ".join(self.format_fate_die(r) for r in rolls)
        embed.add_field(name="Lancers", value=roll_details, inline=False)

        # Display the bonus if it's non-zero
        if bonus != 0:
            embed.add_field(name="Bonus", value=f"{bonus:+}", inline=False)

        # Display the total
        embed.add_field(name="Total", value=str(total), inline=False)

        await ctx.send(embed=embed)

    def format_fate_die(self, roll):
        if roll == -1:
            return "[-]"
        elif roll == 1:
            return "[+]"
        else:
            return "[0]"

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    async def response(self, ctx, user: discord.Member, keyword: str, *, response: str):
        """Sets a response for a specific keyword for a specific user"""
        user_id_str = str(user.id)

        # Récupérer le dictionnaire de configuration actuel pour les règles de réponse
        all_response_rules = await self.config.guild(ctx.guild).response_rules()

        # Vérifier si l'utilisateur existe déjà dans les règles, sinon l'ajouter
        if user_id_str not in all_response_rules:
            all_response_rules[user_id_str] = {}

        # Mettre à jour la réponse pour le mot-clé spécifique
        all_response_rules[user_id_str][keyword] = response

        # Sauvegarder les modifications dans la configuration
        await self.config.guild(ctx.guild).response_rules.set(all_response_rules)

        await ctx.send(f"Response set for {user.display_name} when saying '{keyword}'.")

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    async def remove_response(self, ctx, user: discord.Member, keyword: str):
        """Removes a specific automated response for a user"""
        guild_responses = await self.config.guild(ctx.guild).response_rules.get_raw(
            str(user.id)
        )

        if keyword in guild_responses:
            del guild_responses[keyword]
            await self.config.guild(ctx.guild).response_rules.set_raw(
                user.id, value=guild_responses
            )
            await ctx.send(
                f"Removed automated response for {user.display_name} for keyword '{keyword}'."
            )
        else:
            await ctx.send("No automated response found for that keyword and user.")

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
            return  # Ignorer les messages si le canal ou le fil est marqué comme sourd

        user_id = str(message.author.id)
        response_rules = await self.config.guild(message.guild).response_rules()

        # Vérifiez si des règles de réponse existent pour cet utilisateur
        if user_id in response_rules:
            user_rules = response_rules[user_id]
            for keyword, response in user_rules.items():
                if keyword in message.content:
                    # Attendre un certain temps avant de répondre
                    await asyncio.sleep(3)

                    # Vérifier si le message existe toujours
                    try:
                        msg = await message.channel.fetch_message(message.id)
                        if msg:
                            await message.channel.send(response)
                    except discord.NotFound:
                        pass
                    break

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    async def list_responses(self, ctx):
        """Lists all the automated responses set for users in the guild using embeds."""
        all_response_rules = await self.config.guild(ctx.guild).response_rules()

        if not all_response_rules:
            await ctx.send("No automated responses set.")
            return

        for user_id, keywords in all_response_rules.items():
            member = ctx.guild.get_member(int(user_id))
            member_name = member.display_name if member else f"UserID {user_id}"

            embed = discord.Embed(
                title=f"Automated Responses for {member_name}", color=0x4CAF50
            )

            for keyword, response in keywords.items():
                embed.add_field(
                    name=f"Keyword: '{keyword}'",
                    value=f"Response: '{response}'",
                    inline=False,
                )

            # Vérifier si l'embed ne dépasse pas la limite de champs
            if len(embed.fields) <= 25 and embed.fields:
                await ctx.send(embed=embed)
            else:
                # Si l'embed a trop de champs, le diviser et envoyer en plusieurs messages
                split_embeds = self.split_embed(embed)
                for e in split_embeds:
                    if e.fields:
                        await ctx.send(embed=e)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        """Delete the bot messages on a specific emote reaction"""
        if reaction.message.author == self.bot.user:
            specific_emote = "TG"

            emoji_matches = False
            if isinstance(
                reaction.emoji, discord.Emoji
            ):  # Pour les emojis personnalisés
                emoji_matches = reaction.emoji.name == specific_emote
            elif isinstance(reaction.emoji, str):  # Pour les emojis standards
                emoji_matches = reaction.emoji == specific_emote

            if emoji_matches:
                try:
                    await reaction.message.delete()
                except discord.Forbidden:
                    print("Je n'ai pas les permissions pour supprimer ce message.")
                except discord.HTTPException as e:
                    print(f"Erreur lors de la suppression du message : {e}")

    def split_embed(self, embed):
        """Divide a large embed into smaller embeds if it exceeds field limits."""
        embeds = []
        current_embed = discord.Embed(title=embed.title, color=embed.color)
        for index, field in enumerate(embed.fields):
            if index % 25 == 0 and index != 0:
                embeds.append(current_embed)
                current_embed = discord.Embed(title=embed.title, color=embed.color)
            current_embed.add_field(
                name=field.name, value=field.value, inline=field.inline
            )
        embeds.append(current_embed)
        return embeds

    @commands.hybrid_command()
    async def deaf(self, ctx, *, channel_or_thread=None):
        """Rend le bot sourd aux messages dans le canal ou le fil spécifié."""
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
        """Permet au bot d'écouter à nouveau les messages dans le canal ou fil spécifié."""
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
        """Définit un rappel après une durée spécifiée."""
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
    async def speech2text(
        self, ctx, message_link: str, language: str = "french", service: str = "google"
    ):
        """
        Transcrit un message audio en texte.

        Langues disponibles:
        - french (Français)
        - english (Anglais)
        - spanish (Espagnol)
        - german (Allemand)
        - italian (Italien)
        - portuguese (Portugais)
        - dutch (Néerlandais)
        - russian (Russe)
        - japanese (Japonais)
        - chinese (Chinois simplifié)
        - korean (Coréen)

        Utilisez le nom de la langue (entre parenthèses) comme argument.

        Services disponibles:
        - google (par défaut)
        - local (utilise Vosk pour une reconnaissance vocale locale)
        """
        lang_codes = {
            "french": "fr-FR",
            "english": "en-US",
            "spanish": "es-ES",
            "german": "de-DE",
            "italian": "it-IT",
            "portuguese": "pt-PT",
            "dutch": "nl-NL",
            "russian": "ru-RU",
            "japanese": "ja-JP",
            "chinese": "zh-CN",
            "korean": "ko-KR",
        }
        language = language.lower()

        if language not in lang_codes:
            await ctx.send(
                f"Langue non prise en charge. Les langues disponibles sont : {', '.join(lang_codes.keys())}"
            )
            return

        language_code = lang_codes[language]

        message = await self.get_message_from_link(ctx, message_link)
        if message is None:
            return

        if message.attachments and message.attachments[0].filename.endswith(
            (".mp3", ".wav", ".ogg")
        ):
            file_extension = os.path.splitext(message.attachments[0].filename)[1]
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=file_extension
            ) as temp_audio:
                await message.attachments[0].save(temp_audio.name)
                transcription = await self.transcribe_audio(
                    temp_audio.name, language_code, service
                )
            try:
                os.unlink(temp_audio.name)
            except FileNotFoundError:
                pass  # File has been already deleted, ignore this error
        elif message.content.startswith(
            "https://cdn.discordapp.com/attachments/"
        ) and message.content.endswith((".mp3", ".wav", ".ogg")):
            # get file extension from the URL
            file_extension = os.path.splitext(message.content)[1]
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=file_extension
            ) as temp_audio:
                async with aiohttp.ClientSession() as session:
                    async with session.get(message.content) as response:
                        with open(temp_audio.name, "wb") as f:
                            while True:
                                chunk = await response.content.read(1024)
                                if not chunk:
                                    break
                                f.write(chunk)
                transcription = await self.transcribe_audio(
                    temp_audio.name, language_code, service
                )
            try:
                os.unlink(temp_audio.name)
            except FileNotFoundError:
                pass  # File has been already deleted, ignore this error
        else:
            await ctx.send("Le message lié ne contient pas d'audio valide.")
            return

        self.logger.info(f"Transcription: {transcription}")

        max_length = 2000  # max message length
        if len(transcription) < max_length:
            await ctx.send(f"Transcription: {transcription}")
        else:
            messages = [
                transcription[i : i + max_length]
                for i in range(0, len(transcription), max_length)
            ]

            await ctx.send("Transcription :")

            for message in messages:
                await ctx.send(message)
                await asyncio.sleep(0.25)  # delay between each msg to

    async def get_message_from_link(self, ctx, link):
        """Récupère un message à partir d'un lien."""
        try:
            message_id = int(link.split("/")[-1])
            channel_id = int(link.split("/")[-2])
            guild = ctx.guild
            channel = guild.get_channel(channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(message_id)
                    return message
                except discord.NotFound:
                    await ctx.send("Message introuvable.")
        except (IndexError, ValueError):
            await ctx.send("Lien de message invalide.")
        return None

    async def transcribe_audio(self, audio_path, language_code, service):
        """Transcrit un fichier audio en texte."""
        try:
            _, file_extension = os.path.splitext(audio_path)
            wav_path = None

            # Convertir en WAV si nécessaire
            if file_extension.lower() != ".wav":
                audio = None
                if file_extension.lower() == ".ogg":
                    audio = AudioSegment.from_ogg(audio_path)
                elif file_extension.lower() == ".mp3":
                    audio = AudioSegment.from_mp3(audio_path)
                if audio:
                    # Exporter l'audio en WAV
                    fd, wav_path = tempfile.mkstemp(suffix=".wav")
                    audio.export(wav_path, format="wav")
                    os.close(fd)
                    audio_path = wav_path
                else:
                    raise ValueError(
                        f"Le format de fichier {file_extension} n'est pas pris en charge."
                    )

            if service == "google":
                transcription = await self.transcribe_google(audio_path, language_code)
            elif service == "local":
                transcription = await self.transcribe_local(audio_path, language_code)
            else:
                raise ValueError(
                    f"Service de reconnaissance vocale {service} non pris en charge."
                )

            return transcription

        except Exception as e:
            return f"Erreur lors du traitement de l'audio : {str(e)}"

        finally:
            # Supprimer les fichiers temporaires
            if file_extension.lower() != ".wav" and os.path.exists(audio_path):
                os.remove(audio_path)
            if wav_path and os.path.exists(wav_path):
                os.remove(wav_path)

    async def transcribe_google(self, audio_path, language_code):
        """Transcrit un fichier audio en texte."""
        recognizer = sr.Recognizer()

        with sr.AudioFile(audio_path) as source:
            audio = recognizer.record(source)
        try:
            text = recognizer.recognize_google(audio, language=language_code)
            return text
        except sr.UnknownValueError:
            return "Impossible de transcrire l'audio."
        except sr.RequestError as e:
            return f"Erreur lors de la transcription : {str(e)}"

    async def transcribe_local(self, audio_path, language_code):
        """Transcrit un fichier audio en texte en utilisant Vosk."""
        if language_code != "fr-FR":
            return "Seul le français est pour l'instant supporté en local, veuillez utilisez le service Google pour une autre langue"
        try:
            from vosk import Model, KaldiRecognizer, SetLogLevel
            import wave
            import json

            SetLogLevel(0)  # Afficher les logs de Vosk pour le débogage

            model_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "models",
                "vosk-model-small-fr-0.22",
            )
            self.logger.info(f"Chemin du modèle Vosk : {model_path}")

            model = Model(model_path)
            self.logger.info("Modèle Vosk chargé")

            wf = wave.open(audio_path, "rb")

            self.logger.info(f"Fichier audio ouvert : {audio_path}")
            self.logger.info(f"Taux d'échantillonnage : {wf.getframerate()}")

            # Rééchantillonner le fichier audio si nécessaire
            target_sample_rate = (
                16000  # Taux d'échantillonnage cible (à ajuster selon le modèle Vosk)
            )
            if wf.getframerate() != target_sample_rate:
                self.logger.info(
                    f"Rééchantillonnage du fichier audio à {target_sample_rate} Hz"
                )
                audio = AudioSegment.from_wav(audio_path)
                audio = audio.set_frame_rate(target_sample_rate)
                audio.export(audio_path, format="wav")
                wf = wave.open(audio_path, "rb")

            rec = KaldiRecognizer(model, wf.getframerate())
            self.logger.info("KaldiRecognizer initialisé")

            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                rec.AcceptWaveform(data)
                # res = json.loads(rec.Result())
                # self.logger.info(res)
                # else:
                # res = json.loads(rec.PartialResult())
                # self.logger.info(res)

            result = rec.FinalResult()
            self.logger.info(f"Résultat de la transcription : {result}")

            return json.loads(result)["text"]

        except Exception as e:
            return f"Erreur lors de la transcription locale : {str(e)}"

    @commands.hybrid_command()
    async def draw(
        self,
        ctx,
        prompt: str,
        model: str,
        amount: int = 1,
        width: int = 1024,
        height: int = 1024,
        steps: int = 40,
        sampler_name: str = "k_dpmpp_2s_a",
        timeout: int = 300,
        cfg_scale: int = 7,
        negative_prompt: str = "",
    ):
        """Génère une image avec l'API REST d'AI Horde."""
        # Vérifier si les paramètres obligatoires sont fournis
        if not prompt or not model:
            await ctx.send("Les paramètres prompt et model sont obligatoires.")
            return

        with open(
            os.path.join(os.path.dirname(__file__), "horde_api_key.txt"), "r"
        ) as file:
            api_key = file.read().strip()

        if negative_prompt != "":
            prompt += "###" + negative_prompt

        # Définir les paramètres de la requête
        payload = {
            "prompt": prompt,
            "params": {
                "sampler_name": sampler_name,
                "cfg_scale": cfg_scale,
                "seed": "",
                "height": height,
                "width": width,
                "steps": steps,
                "n": amount,
            },
            "nsfw": True,
            "r2": True,  # Activer l'upload vers R2
            "shared": True,
            "models": [model],
        }

        if model == "Pony Diffusion XL":
            payload["params"]["clip_skip"] = 2

        headers = {
            "apikey": api_key,
            "Client-Agent": "ai-horde-bot/1.0",
        }

        try:
            # Envoyer la requête de génération d'image à l'API d'AI Horde
            async with aiohttp.ClientSession() as session:
                self.logger.info(f"Generation request: {json.dumps(payload)}")
                async with session.post(
                    "https://stablehorde.net/api/v2/generate/async",
                    json=payload,
                    headers=headers,
                ) as response:
                    if response.status == 202:
                        data = await response.json()
                        request_id = data["id"]
                        kudos = data["kudos"]
                        status_message = await ctx.send(
                            f"La génération d'image a été lancée avec succès. ID de la requête : {request_id}. Coût en Kudos : {kudos}"
                        )

                        # Attendre que la génération soit terminée
                        start_time = time.time()
                        while True:
                            if time.time() - start_time > timeout:
                                await ctx.send("La génération d'image a expiré.")
                                return
                            await asyncio.sleep(
                                5
                            )  # Attendre 5 secondes avant de vérifier à nouveau l'état de la requête
                            self.logger.info("Vérification de l'état de la requête...")
                            async with session.get(
                                f"https://stablehorde.net/api/v2/generate/check/{request_id}"
                            ) as check_response:
                                if check_response.status == 200:
                                    check_data = await check_response.json()
                                    if check_data["done"]:
                                        self.logger.info(
                                            "La génération d'image est terminée."
                                        )
                                        break
                                    else:
                                        self.logger.info(
                                            f"État de la requête : {check_data}"
                                        )
                                        # Mettre à jour le message avec les informations d'avancement
                                        await status_message.edit(
                                            content=f"La génération d'image est en cours. ID de la requête : {request_id}. Coût en Kudos : {kudos}\n"
                                            f"Avancement : {check_data['finished']} terminées, {check_data['processing']} en traitement, {check_data['waiting']} en attente."
                                        )
                                else:
                                    self.logger.warning(
                                        f"Erreur lors de la vérification de l'état de la requête. Code de statut : {check_response.status}"
                                    )

                        # Récupérer les résultats de la génération d'image
                        async with session.get(
                            f"https://stablehorde.net/api/v2/generate/status/{request_id}"
                        ) as status_response:
                            self.logger.info(
                                "Récupération des résultats de la génération d'image..."
                            )
                            if status_response.status == 200:
                                status_data = await status_response.json()
                                files = []
                                for generation in status_data["generations"]:
                                    image_url = generation["img"]

                                    # Télécharger l'image à partir de l'URL
                                    async with session.get(image_url) as image_response:
                                        if image_response.status == 200:
                                            image_data = await image_response.read()

                                            # Créer un fichier image en mémoire
                                            image_file = io.BytesIO(image_data)
                                            image_file.seek(0)
                                            discord_file = discord.File(
                                                image_file,
                                                filename=f"{generation['id']}.webp",
                                            )

                                            # Ajouter le fichier à la liste
                                            files.append(discord_file)
                                        else:
                                            self.logger.warning(
                                                f"Erreur lors du téléchargement de l'image. Code de statut : {image_response.status}"
                                            )

                                await ctx.reply(files=files)
                            else:
                                await ctx.reply(
                                    f"Erreur lors de la récupération des résultats. Code de statut : {status_response.status}"
                                )
                    else:
                        await ctx.reply(
                            f"Erreur lors de la génération d'image. Code de statut : {response.status}"
                        )
        except Exception as e:
            self.logger.error(
                f"Une erreur s'est produite lors de la génération d'image : {str(e)}"
            )
            await ctx.send("Une erreur s'est produite lors de la génération d'image.")

    @commands.hybrid_command()
    async def kudos(self, ctx):
        with open(
            os.path.join(os.path.dirname(__file__), "horde_api_key.txt"), "r"
        ) as file:
            api_key = file.read().strip()

        headers = {
            "apikey": api_key,
            "Client-Agent": "ai-horde-bot/1.0",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://stablehorde.net/api/v2/find_user", headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    kudos = data["kudos"]
                    await ctx.send(f"Vous avez actuellement {kudos} Kudos.")
                else:
                    await ctx.send("Erreur lors de la récupération des Kudos.")
