import asyncio
from redbot.core import commands
import speech_recognition as sr
from pydub import AudioSegment
import os
import tempfile
import aiohttp
import logging
from vosk import Model, KaldiRecognizer, SetLogLevel
import wave
import json

from utils import get_message_from_link


class AudioCommands(commands.Cog):
    def __init__(self, bot, config):
        self.bot = bot
        self.config = config
        self.logger = logging.getLogger("red.mycog.AudioCommands")

    def get_commands(self):
        return [("speech2text", self.speech2text)]

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

        message = await get_message_from_link(ctx, message_link)
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
                await asyncio.sleep(
                    0.25
                )  # delay between each msg to avoid rate limiting

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
        """Transcrit un fichier audio en texte en utilisant Google Speech Recognition."""
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

            result = rec.FinalResult()
            self.logger.info(f"Résultat de la transcription : {result}")

            return json.loads(result)["text"]

        except Exception as e:
            return f"Erreur lors de la transcription locale : {str(e)}"
