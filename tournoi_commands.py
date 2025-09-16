import discord
import asyncio
import random
import math
from datetime import datetime
from .google_forms_handler import GoogleFormsHandler


class TournoiCommands:
    """Système de gestion de tournois à élimination directe."""

    def __init__(self, bot, config):
        self.bot = bot
        self.config = config
        self.active_tournaments = {}  # guild_id -> tournament_data
        self.setup_sessions = {}  # user_id -> setup_data
        self.google_forms_handler = GoogleFormsHandler()

        asyncio.create_task(self.load_active_tournaments())

    async def load_active_tournaments(self):
        """Charge les tournois actifs depuis la configuration."""
        await asyncio.sleep(2)

        for guild in self.bot.guilds:
            try:
                tournaments = await self.config.guild(guild).active_tournaments()
                if tournaments:
                    for guild_id_str, tournament_data in tournaments.items():
                        guild_id = int(guild_id_str)
                        if tournament_data and tournament_data.get("state") == "active":
                            self.active_tournaments[guild_id] = tournament_data
                            print(
                                f"[Tournament] Tournoi chargé pour le serveur {guild.name}"
                            )
            except Exception as e:
                print(
                    f"[Tournament] Erreur lors du chargement des tournois pour {guild.name}: {e}"
                )

    async def start_tournament_setup(self, ctx):
        """Démarre la configuration d'un tournoi en MP."""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Seuls les administrateurs peuvent créer des tournois.")
            return

        guild_id = str(ctx.guild.id)
        tournaments = await self.config.guild(ctx.guild).active_tournaments()
        if guild_id in tournaments and tournaments[guild_id]:
            await ctx.send(
                "⚠️ Un tournoi est déjà en cours sur ce serveur. Utilisez `!tournoi_stop` pour l'arrêter."
            )
            return

        await ctx.send("📨 Je t'ai envoyé un message privé pour configurer le tournoi!")

        self.setup_sessions[ctx.author.id] = {
            "guild": ctx.guild,
            "step": "theme",
            "theme": None,
            "participants": [],
            "channel": None,
            "vote_duration": 3600,
            "between_rounds_delay": 300,
            "creator": ctx.author,
            "vote_mode": "discord",
        }

        try:
            embed = discord.Embed(
                title="🏆 Configuration du Tournoi",
                description="Bienvenue dans l'assistant de création de tournoi!\n\n**Étape 1/6: Thème du tournoi**\n\nQuel est le thème de votre tournoi? (ex: Les méchants de films, Les meilleurs desserts, etc.)",
                color=0x3498DB,
            )
            embed.set_footer(text="Tapez 'annuler' à tout moment pour abandonner")
            await ctx.author.send(embed=embed)
        except discord.Forbidden:
            await ctx.send(
                "❌ Je ne peux pas t'envoyer de MP. Vérifie tes paramètres de confidentialité."
            )
            del self.setup_sessions[ctx.author.id]

    async def handle_setup_dm(self, message):
        """Gère les messages de configuration en MP."""
        if message.author.id not in self.setup_sessions:
            return False

        session = self.setup_sessions[message.author.id]
        content = message.content.strip()

        if content.lower() == "annuler":
            await message.channel.send("❌ Configuration annulée.")
            del self.setup_sessions[message.author.id]
            return True

        if session["step"] == "theme":
            session["theme"] = content
            session["step"] = "participants"

            embed = discord.Embed(
                title="🏆 Configuration du Tournoi",
                description=f"**Thème défini:** {content}\n\n**Étape 2/6: Participants**\n\nMaintenant, envoie-moi les participants un par un.\n\n**Instructions:**\n• Écris simplement le nom du participant\n• Tu peux joindre une image au message (optionnel)\n• Exemple: `Dark Vador` + image attachée\n\nTape `fini` quand tu as ajouté tous les participants (minimum 4).",
                color=0x3498DB,
            )
            embed.add_field(
                name="Participants ajoutés", value="Aucun pour l'instant", inline=False
            )
            await message.channel.send(embed=embed)

        elif session["step"] == "participants":
            if content.lower() == "fini":
                if len(session["participants"]) < 4:
                    await message.channel.send(
                        "❌ Il faut au moins 4 participants! Continue d'en ajouter."
                    )
                    return True

                session["step"] = "vote_mode"

                embed = discord.Embed(
                    title="🏆 Configuration du Tournoi",
                    description=f"**Participants:** {len(session['participants'])} ajoutés\n\n**Étape 3/6: Mode de vote**\n\nComment veux-tu gérer les votes?\n\n**1️⃣ Discord** - Les matchs sont affichés dans Discord avec des réactions (mode classique)\n**2️⃣ Google Forms** - Un formulaire Google est créé pour chaque tour (plus organisé pour beaucoup de participants)\n\nRéponds avec **1** ou **2**",
                    color=0x3498DB,
                )

                if not self.google_forms_handler.credentials:
                    embed.add_field(
                        name="⚠️ Note",
                        value="Google Forms nécessite une configuration préalable. Si non configuré, le mode Discord sera utilisé.",
                        inline=False,
                    )

                await message.channel.send(embed=embed)
            else:
                name = content.strip()
                image_url = None

                if message.attachments:
                    for attachment in message.attachments:
                        if (
                            attachment.content_type
                            and attachment.content_type.startswith("image/")
                        ):
                            image_url = attachment.url
                            break

                session["participants"].append(
                    {
                        "name": name,
                        "image": image_url,
                        "id": len(session["participants"]),
                    }
                )

                participants_list = "\n".join(
                    [
                        f"{i+1}. {p['name']}"
                        for i, p in enumerate(session["participants"])
                    ]
                )
                embed = discord.Embed(
                    title="✅ Participant ajouté!",
                    description=f"**{name}** a été ajouté au tournoi.",
                    color=0x2ECC71,
                )
                if image_url:
                    embed.set_thumbnail(url=image_url)
                    embed.add_field(
                        name="Image", value="✅ Image attachée", inline=False
                    )

                embed.add_field(
                    name=f"Participants ({len(session['participants'])})",
                    value=participants_list[-1000:] or "Aucun",
                    inline=False,
                )
                embed.set_footer(
                    text="Continue d'ajouter des participants ou tape 'fini'"
                )
                await message.channel.send(embed=embed)

        elif session["step"] == "vote_mode":
            if content in ["1", "2"]:
                if content == "1":
                    session["vote_mode"] = "discord"
                    mode_text = "Discord (réactions)"
                else:
                    session["vote_mode"] = "google_forms"
                    mode_text = "Google Forms"

                    if not self.google_forms_handler.credentials:
                        await message.channel.send(
                            "⚠️ Google Forms n'est pas configuré. Utilisation du mode Discord par défaut."
                        )
                        session["vote_mode"] = "discord"
                        mode_text = "Discord (réactions)"

                session["step"] = "channel"
                channels_list = "\n".join(
                    [
                        f"{i+1}. {ch.name}"
                        for i, ch in enumerate(session["guild"].text_channels)
                    ]
                )

                embed = discord.Embed(
                    title="🏆 Configuration du Tournoi",
                    description=f"**Mode de vote:** {mode_text}\n\n**Étape 4/6: Canal du tournoi**\n\nDans quel canal veux-tu que le tournoi se déroule? Envoie le numéro ou le nom du canal.\n\n{channels_list[:1900]}",
                    color=0x3498DB,
                )
                await message.channel.send(embed=embed)
            else:
                await message.channel.send(
                    "❌ Réponds avec **1** pour Discord ou **2** pour Google Forms"
                )
                return True

        elif session["step"] == "channel":
            channel = None
            if content.isdigit():
                idx = int(content) - 1
                if 0 <= idx < len(session["guild"].text_channels):
                    channel = session["guild"].text_channels[idx]
            else:
                channel = discord.utils.get(
                    session["guild"].text_channels, name=content
                )

            if not channel:
                await message.channel.send(
                    "❌ Canal introuvable. Réessaie avec le nom ou le numéro."
                )
                return True

            session["channel"] = channel
            session["step"] = "vote_duration"

            embed = discord.Embed(
                title="🏆 Configuration du Tournoi",
                description=f"**Canal sélectionné:** #{channel.name}\n\n**Étape 5/6: Durée des votes**\n\nCombien de temps doit durer chaque vote?\n\nExemples:\n- `30m` pour 30 minutes\n- `2h` pour 2 heures\n- `1d` pour 1 jour",
                color=0x3498DB,
            )
            await message.channel.send(embed=embed)

        elif session["step"] == "vote_duration":
            duration = self.parse_duration(content)
            if not duration:
                await message.channel.send(
                    "❌ Format invalide. Utilise par exemple: 30m, 2h, 1d"
                )
                return True

            session["vote_duration"] = duration
            session["step"] = "between_rounds"

            embed = discord.Embed(
                title="🏆 Configuration du Tournoi",
                description=f"**Durée des votes:** {self.format_duration(duration)}\n\n**Étape 6/6: Délai entre les tours**\n\nCombien de temps entre la fin d'un tour et le début du suivant?\n\nExemples:\n- `5m` pour 5 minutes\n- `30m` pour 30 minutes\n- `1h` pour 1 heure",
                color=0x3498DB,
            )
            await message.channel.send(embed=embed)

        elif session["step"] == "between_rounds":
            duration = self.parse_duration(content)
            if not duration:
                await message.channel.send(
                    "❌ Format invalide. Utilise par exemple: 5m, 30m, 1h"
                )
                return True

            session["between_rounds_delay"] = duration

            embed = discord.Embed(
                title="🏆 Récapitulatif du Tournoi",
                description=f"**Thème:** {session['theme']}\n**Participants:** {len(session['participants'])}\n**Mode de vote:** {'Discord (réactions)' if session['vote_mode'] == 'discord' else 'Google Forms'}\n**Canal:** #{session['channel'].name}\n**Durée des votes:** {self.format_duration(session['vote_duration'])}\n**Délai entre tours:** {self.format_duration(session['between_rounds_delay'])}",
                color=0x2ECC71,
            )

            sample = session["participants"][:10]
            participants_preview = "\n".join([f"• {p['name']}" for p in sample])
            if len(session["participants"]) > 10:
                participants_preview += (
                    f"\n... et {len(session['participants']) - 10} autres"
                )
            embed.add_field(
                name="Aperçu des participants", value=participants_preview, inline=False
            )

            embed.set_footer(
                text="Tape 'confirmer' pour lancer le tournoi ou 'annuler' pour abandonner"
            )
            session["step"] = "confirm"
            await message.channel.send(embed=embed)

        elif session["step"] == "confirm":
            if content.lower() == "confirmer":
                await message.channel.send("🚀 Lancement du tournoi...")
                await self.launch_tournament(session)
                del self.setup_sessions[message.author.id]
            else:
                await message.channel.send("❌ Utilise 'confirmer' ou 'annuler'")

        return True

    def parse_duration(self, duration_str):
        """Parse une durée comme '30m' ou '2h' en secondes."""
        import re

        match = re.match(r"^(\d+)([mhd])$", duration_str.lower())
        if not match:
            return None

        value = int(match.group(1))
        unit = match.group(2)

        multipliers = {"m": 60, "h": 3600, "d": 86400}
        return value * multipliers[unit]

    def format_duration(self, seconds):
        """Formate une durée en secondes en texte lisible."""
        if seconds < 3600:
            return f"{seconds // 60} minutes"
        elif seconds < 86400:
            return f"{seconds // 3600} heures"
        else:
            return f"{seconds // 86400} jours"

    async def launch_tournament(self, session):
        """Lance le tournoi avec les paramètres configurés."""
        guild = session["guild"]

        participants = session["participants"][:]
        random.shuffle(participants)

        tournament_data = {
            "theme": session["theme"],
            "participants": {str(p["id"]): p for p in participants},
            "channel_id": session["channel"].id,
            "vote_duration": session["vote_duration"],
            "between_rounds_delay": session["between_rounds_delay"],
            "creator_id": session["creator"].id,
            "current_round": 1,
            "matches": {},
            "results": {},
            "bracket": self.create_bracket(participants),
            "state": "active",
            "created_at": datetime.now().isoformat(),
            "vote_mode": session["vote_mode"],
            "current_form_id": None,
        }

        guild_id_int = guild.id if isinstance(guild.id, int) else int(guild.id)

        self.active_tournaments[guild_id_int] = tournament_data
        tournaments = await self.config.guild(guild).active_tournaments()
        tournaments[str(guild_id_int)] = tournament_data
        await self.config.guild(guild).active_tournaments.set(tournaments)

        embed = discord.Embed(
            title=f"🏆 TOURNOI: {session['theme']}",
            description=f"Un nouveau tournoi commence avec **{len(participants)} participants**!\n\nLe tournoi se déroulera en élimination directe. {'Votez pour votre préféré dans chaque match!' if session['vote_mode'] == 'discord' else 'Un formulaire Google sera partagé pour voter!'}\n\n**Mode de vote:** {'Discord (réactions)' if session['vote_mode'] == 'discord' else 'Google Forms'}\n**Durée des votes:** {self.format_duration(session['vote_duration'])}\n**Créé par:** {session['creator'].mention}",
            color=0xF39C12,
            timestamp=datetime.utcnow(),
        )
        embed.set_footer(text="Que le meilleur gagne!")

        announcement = await session["channel"].send(embed=embed)
        try:
            await announcement.pin()
        except:
            pass  # Si on ne peut pas épingler, ce n'est pas grave

        await asyncio.sleep(5)

        await self.start_round(guild_id_int)

    def create_bracket(self, participants):
        """Crée la structure du bracket du tournoi."""
        n = len(participants)
        rounds_needed = math.ceil(math.log2(n))
        bracket_size = 2**rounds_needed

        bracket = {}

        participant_ids = [p["id"] for p in participants]
        random.shuffle(participant_ids)

        matches = []
        match_count = 0

        i = 0
        while i < len(participant_ids) or match_count * 2 < bracket_size:
            match_count += 1
            match_id = f"R1_M{match_count}"

            p1 = participant_ids[i] if i < len(participant_ids) else None
            p2 = participant_ids[i + 1] if i + 1 < len(participant_ids) else None

            if p1 is None and p2 is not None:
                p1, p2 = p2, p1

            if p1 is not None:
                matches.append(
                    {
                        "id": match_id,
                        "round": 1,
                        "participant1": p1,
                        "participant2": p2,
                        "winner": None,
                        "votes": {},
                    }
                )

            i += 2

        bracket["matches"] = {m["id"]: m for m in matches}
        bracket["rounds"] = rounds_needed
        bracket["current_round"] = 1

        return bracket

    async def start_round(self, guild_id):
        """Démarre un nouveau tour du tournoi."""
        if isinstance(guild_id, str):
            guild_id = int(guild_id)

        tournament = self.active_tournaments.get(guild_id)
        if not tournament:
            print(f"[Tournament] Aucun tournoi trouvé pour guild_id: {guild_id}")
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            print(f"[Tournament] Guild non trouvé: {guild_id}")
            return

        channel = guild.get_channel(tournament["channel_id"])
        if not channel:
            print(f"[Tournament] Channel non trouvé: {tournament['channel_id']}")
            return

        current_round = tournament["bracket"]["current_round"]

        round_matches = [
            m
            for m in tournament["bracket"]["matches"].values()
            if m["round"] == current_round
            and m["winner"] is None
            and m["participant1"] is not None
        ]

        if not round_matches:
            tournament["bracket"]["current_round"] += 1
            await self.create_next_round_matches(guild_id)
            await self.start_round(guild_id)
            return

        embed = discord.Embed(
            title=f"🥊 TOUR {current_round}",
            description=f"**{len(round_matches)} matchs** vont se dérouler!\n\n{'Votez avec les réactions 1️⃣ et 2️⃣' if tournament['vote_mode'] == 'discord' else 'Un formulaire Google va être partagé pour voter!'}",
            color=0xE74C3C,
        )
        await channel.send(embed=embed)

        if tournament["vote_mode"] == "google_forms":
            await self.start_round_google_forms(guild_id, round_matches)
        else:
            await self.start_round_discord(guild_id, round_matches)

    async def start_round_discord(self, guild_id, round_matches):
        """Démarre un tour avec le mode de vote Discord (méthode originale)."""
        tournament = self.active_tournaments[guild_id]
        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(tournament["channel_id"])

        tasks = []
        bye_messages = []

        for match in round_matches:
            if match["participant1"] is None:
                continue
            elif match["participant2"] is None:
                match["winner"] = match["participant1"]
                participant = tournament["participants"][str(match["participant1"])]

                tournament["results"][match["id"]] = {
                    "winner": match["participant1"],
                    "participant1_votes": 0,
                    "participant2_votes": 0,
                    "bye": True,
                    "participant1_name": participant["name"],
                    "participant2_name": None,
                }

                bye_embed = discord.Embed(
                    title="🎯 Passage automatique",
                    description=f"**{participant['name']}** passe automatiquement au tour suivant!",
                    color=0x2ECC71,
                )
                bye_messages.append(channel.send(embed=bye_embed))
            else:
                tasks.append(self.run_match_discord(guild_id, match))

        if bye_messages:
            await asyncio.gather(*bye_messages)
            await asyncio.sleep(2)

        if tasks:
            await asyncio.gather(*tasks)

        await self.finalize_round(guild_id, tournament["bracket"]["current_round"])

    async def start_round_google_forms(self, guild_id, round_matches):
        """Démarre un tour avec Google Forms."""
        tournament = self.active_tournaments[guild_id]
        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(tournament["channel_id"])

        bye_messages = []
        active_matches = []

        for match in round_matches:
            if match["participant1"] is None:
                continue
            elif match["participant2"] is None:
                match["winner"] = match["participant1"]
                participant = tournament["participants"][str(match["participant1"])]

                tournament["results"][match["id"]] = {
                    "winner": match["participant1"],
                    "participant1_votes": 0,
                    "participant2_votes": 0,
                    "bye": True,
                    "participant1_name": participant["name"],
                    "participant2_name": None,
                }

                bye_embed = discord.Embed(
                    title="🎯 Passage automatique",
                    description=f"**{participant['name']}** passe automatiquement au tour suivant!",
                    color=0x2ECC71,
                )
                bye_messages.append(channel.send(embed=bye_embed))
            else:
                active_matches.append(match)

        if bye_messages:
            await asyncio.gather(*bye_messages)
            await asyncio.sleep(2)

        if not active_matches:
            await self.finalize_round(guild_id, tournament["bracket"]["current_round"])
            return

        waiting_embed = discord.Embed(
            title="⏳ Création du formulaire de vote...",
            description="Merci de patienter quelques secondes pendant la préparation du formulaire Google.",
            color=0xF39C12,
        )
        waiting_msg = await channel.send(embed=waiting_embed)

        form_matches = []
        for match in active_matches:
            p1 = tournament["participants"][str(match["participant1"])]
            p2 = tournament["participants"][str(match["participant2"])]

            form_match = {
                "match_id": match["id"],
                "participant1_id": match["participant1"],
                "participant2_id": match["participant2"],
                "participant1_name": p1["name"],
                "participant2_name": p2["name"],
                "participant1_image": p1.get("image"),
                "participant2_image": p2.get("image"),
            }
            form_matches.append(form_match)

        form_id, form_url = await self.google_forms_handler.create_tournament_form(
            tournament["theme"],
            tournament["bracket"]["current_round"],
            form_matches,
            self.format_duration(tournament["vote_duration"]),
        )

        try:
            await waiting_msg.delete()
        except:
            pass

        if not form_id:
            error_embed = discord.Embed(
                title="⚠️ Erreur Google Forms",
                description="Impossible de créer le formulaire Google. Utilisation du mode Discord à la place.",
                color=0xE74C3C,
            )
            await channel.send(embed=error_embed)
            await self.start_round_discord(guild_id, round_matches)
            return

        tournament["current_form_id"] = form_id

        form_embed = discord.Embed(
            title="🗳️ VOTEZ MAINTENANT !",
            description=f"**Tour {tournament['bracket']['current_round']}** du tournoi **{tournament['theme']}**",
            color=0x4285F4,
        )

        form_embed.add_field(
            name="📋 Accès au formulaire",
            value=f"[**Cliquez ici pour voter**]({form_url})",
            inline=False,
        )

        form_embed.add_field(
            name="⏱️ Temps restant",
            value=self.format_duration(tournament["vote_duration"]),
            inline=True,
        )

        form_embed.add_field(
            name="🥊 Matchs", value=f"{len(active_matches)} matchs", inline=True
        )

        form_embed.add_field(
            name="💡 Conseils",
            value="• Les images sont cliquables pour agrandir\n• Un seul vote par personne\n• Tous les matchs sont obligatoires",
            inline=False,
        )

        form_embed.set_footer(
            text="Le formulaire sera automatiquement supprimé à la fin du vote",
            icon_url="https://upload.wikimedia.org/wikipedia/commons/5/5b/Google_Forms_2020_Logo.svg",
        )

        form_embed.timestamp = datetime.utcnow()

        form_message = await channel.send(embed=form_embed)

        try:
            await form_message.pin()
        except:
            pass  # Si on ne peut pas épingler, ce n'est pas grave

        total_time = tournament["vote_duration"]
        start_time = asyncio.get_event_loop().time()

        reminders = {
            # 0.25: ("⏰ Rappel", 0xF39C12),
            0.50: ("⏰ Mi-temps", 0xF39C12),
            # 0.75: ("⏰ Dernier quart", 0xF39C12),
            0.90: ("⚠️ DERNIÈRE CHANCE !", 0xE74C3C),
        }

        reminders_sent = set()

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            remaining = total_time - elapsed

            if remaining <= 0:
                break

            progress = elapsed / total_time
            for threshold, (title, color) in reminders.items():
                if progress >= threshold and threshold not in reminders_sent:
                    reminders_sent.add(threshold)
                    reminder_embed = discord.Embed(
                        title=title,
                        description=f"Il reste **{self.format_duration(int(remaining))}** pour voter !",
                        color=color,
                    )
                    await channel.send(embed=reminder_embed, delete_after=300)

            await asyncio.sleep(min(30, remaining))

        try:
            closed_embed = discord.Embed(
                title="🔒 Vote terminé",
                description="**Le temps de vote est écoulé!**\n\nLes résultats sont en cours de traitement...",
                color=0xE74C3C,
                timestamp=datetime.utcnow(),
            )
            closed_embed.set_footer(text="Merci à tous les participants!")
            await form_message.edit(embed=closed_embed)

            await form_message.unpin()
        except:
            pass

        processing_embed = discord.Embed(
            title="🔄 Traitement des résultats",
            description="Calcul des votes en cours...",
            color=0x3498DB,
        )
        processing_msg = await channel.send(embed=processing_embed)

        await self.process_google_form_results(guild_id, form_id, active_matches)

        try:
            await processing_msg.delete()
        except:
            pass

        deleted = await self.google_forms_handler.delete_form(form_id)
        if deleted:
            print(f"Formulaire {form_id} supprimé avec succès")
        else:
            print(f"Impossible de supprimer le formulaire {form_id}")

        tournament["current_form_id"] = None

        await self.finalize_round(guild_id, tournament["bracket"]["current_round"])

    async def process_google_form_results(self, guild_id, form_id, matches):
        """Traite les résultats d'un Google Form."""
        tournament = self.active_tournaments[guild_id]
        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(tournament["channel_id"])

        votes_data = await self.google_forms_handler.get_form_responses(form_id)

        if not votes_data:
            await channel.send(
                "⚠️ Aucun vote reçu ou erreur lors de la récupération. Sélection aléatoire des gagnants..."
            )
            for match in matches:
                match["winner"] = random.choice(
                    [match["participant1"], match["participant2"]]
                )
                p1 = tournament["participants"][str(match["participant1"])]
                p2 = tournament["participants"][str(match["participant2"])]

                tournament["results"][match["id"]] = {
                    "winner": match["winner"],
                    "participant1_votes": 0,
                    "participant2_votes": 0,
                    "participant1_name": p1["name"],
                    "participant2_name": p2["name"],
                }
            return

        total_responses = 0
        for match_votes in votes_data.values():
            total_responses += sum(match_votes.values())

        if total_responses > 0:
            await channel.send(f"📊 **{total_responses} votes** reçus au total!")

        for match_idx, match in enumerate(matches):
            p1 = tournament["participants"][str(match["participant1"])]
            p2 = tournament["participants"][str(match["participant2"])]

            match_votes = votes_data.get(str(match_idx), {})

            p1_votes = match_votes.get(str(match["participant1"]), 0)
            p2_votes = match_votes.get(str(match["participant2"]), 0)

            print(
                f"[Tournament] Match {match['id']}: {p1['name']} ({p1_votes}) vs {p2['name']} ({p2_votes})"
            )

            if p1_votes > p2_votes:
                winner = match["participant1"]
                winner_name = p1["name"]
            elif p2_votes > p1_votes:
                winner = match["participant2"]
                winner_name = p2["name"]
            else:
                if p1_votes == 0 and p2_votes == 0:
                    await channel.send(
                        f"⚠️ Aucun vote pour le match **{p1['name']}** vs **{p2['name']}**. Tirage au sort..."
                    )
                else:
                    await channel.send(
                        f"⚖️ Égalité dans le match **{p1['name']}** vs **{p2['name']}** ! Tirage au sort..."
                    )

                winner = random.choice([match["participant1"], match["participant2"]])
                winner_name = (
                    p1["name"] if winner == match["participant1"] else p2["name"]
                )

            if p1_votes > 0 or p2_votes > 0:
                result_embed = discord.Embed(
                    title=f"📊 Résultat - Match {match_idx + 1}", color=0x2ECC71
                )
                result_embed.add_field(
                    name=f"{p1['name']}", value=f"**{p1_votes}** votes", inline=True
                )
                result_embed.add_field(name="VS", value="⚔️", inline=True)
                result_embed.add_field(
                    name=f"{p2['name']}", value=f"**{p2_votes}** votes", inline=True
                )
                result_embed.add_field(
                    name="🏆 Gagnant", value=f"**{winner_name}**", inline=False
                )

                await channel.send(embed=result_embed)
                await asyncio.sleep(1)

            match["winner"] = winner
            tournament["results"][match["id"]] = {
                "winner": winner,
                "participant1_votes": p1_votes,
                "participant2_votes": p2_votes,
                "participant1_name": p1["name"],
                "participant2_name": p2["name"],
            }

    async def finalize_round(self, guild_id, round_num):
        """Finalise un tour et prépare le suivant."""
        tournament = self.active_tournaments[guild_id]
        guild = self.bot.get_guild(guild_id)

        await self.post_round_summary(guild_id, round_num)

        tournaments = await self.config.guild(guild).active_tournaments()
        tournaments[str(guild_id)] = tournament
        await self.config.guild(guild).active_tournaments.set(tournaments)

        remaining_matches = [
            m
            for m in tournament["bracket"]["matches"].values()
            if m["winner"] is None and m["participant1"] is not None
        ]

        winners_count = len(
            [
                m["winner"]
                for m in tournament["bracket"]["matches"].values()
                if m["round"] == round_num and m["winner"] is not None
            ]
        )

        if winners_count == 1 and not remaining_matches:
            await self.end_tournament(guild_id)
            return
        elif winners_count == 0 and not remaining_matches:
            if round_num > 1:
                prev_winners = [
                    m["winner"]
                    for m in tournament["bracket"]["matches"].values()
                    if m["round"] == round_num - 1 and m["winner"] is not None
                ]
                if len(prev_winners) == 1:
                    await self.end_tournament(guild_id)
                    return

        await asyncio.sleep(tournament["between_rounds_delay"])

        tournament["bracket"]["current_round"] += 1
        await self.create_next_round_matches(guild_id)
        await self.start_round(guild_id)

    async def run_match_discord(self, guild_id, match):
        """Exécute un match individuel en mode Discord."""
        tournament = self.active_tournaments[guild_id]
        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(tournament["channel_id"])

        if match["participant1"] is None or match["participant2"] is None:
            return

        p1 = tournament["participants"][str(match["participant1"])]
        p2 = tournament["participants"][str(match["participant2"])]

        embed = discord.Embed(
            title=f"⚔️ MATCH: {p1['name']} VS {p2['name']}",
            description="Votez pour votre préféré!",
            color=0x9B59B6,
        )

        if p1.get("image"):
            embed.add_field(name=f"1️⃣ {p1['name']}", value="\u200b", inline=True)
        else:
            embed.add_field(name=f"1️⃣ {p1['name']}", value="(Pas d'image)", inline=True)

        embed.add_field(name="VS", value="⚔️", inline=True)

        if p2.get("image"):
            embed.add_field(name=f"2️⃣ {p2['name']}", value="\u200b", inline=True)
        else:
            embed.add_field(name=f"2️⃣ {p2['name']}", value="(Pas d'image)", inline=True)

        if p1.get("image") and p2.get("image"):
            embed1 = discord.Embed(color=0x3498DB)
            embed1.set_author(name=f"1️⃣ {p1['name']}")
            embed1.set_image(url=p1["image"])

            embed2 = discord.Embed(color=0xE74C3C)
            embed2.set_author(name=f"2️⃣ {p2['name']}")
            embed2.set_image(url=p2["image"])

            msg = await channel.send(embeds=[embed, embed1, embed2])
        elif p1.get("image"):
            embed.set_image(url=p1["image"])
            embed.set_footer(text=f"Image: {p1['name']}")
            msg = await channel.send(embed=embed)
        elif p2.get("image"):
            embed.set_image(url=p2["image"])
            embed.set_footer(text=f"Image: {p2['name']}")
            msg = await channel.send(embed=embed)
        else:
            msg = await channel.send(embed=embed)

        await msg.add_reaction("1️⃣")
        await asyncio.sleep(0.5)
        await msg.add_reaction("2️⃣")

        match["message_id"] = msg.id

        await asyncio.sleep(tournament["vote_duration"])

        try:
            msg = await channel.fetch_message(msg.id)
            votes_1 = 0
            votes_2 = 0

            for reaction in msg.reactions:
                if str(reaction.emoji) == "1️⃣":
                    votes_1 = reaction.count - 1
                elif str(reaction.emoji) == "2️⃣":
                    votes_2 = reaction.count - 1

            if votes_1 > votes_2:
                winner = match["participant1"]
            elif votes_2 > votes_1:
                winner = match["participant2"]
            else:
                winner = random.choice([match["participant1"], match["participant2"]])

            match["winner"] = winner
            tournament["results"][match["id"]] = {
                "winner": winner,
                "participant1_votes": votes_1,
                "participant2_votes": votes_2,
                "participant1_name": p1["name"],
                "participant2_name": p2["name"],
            }

        except discord.NotFound:
            match["winner"] = random.choice(
                [match["participant1"], match["participant2"]]
            )
            tournament["results"][match["id"]] = {
                "winner": match["winner"],
                "participant1_votes": 0,
                "participant2_votes": 0,
                "participant1_name": p1["name"],
                "participant2_name": p2["name"],
            }

    async def post_round_summary(self, guild_id, round_num):
        """Affiche un récapitulatif du tour avec les qualifiés et éliminés."""
        tournament = self.active_tournaments[guild_id]
        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(tournament["channel_id"])

        round_matches = [
            m
            for m in tournament["bracket"]["matches"].values()
            if m["round"] == round_num
        ]

        qualified = []
        eliminated = []

        for match in round_matches:
            if match["id"] not in tournament["results"]:
                continue

            result = tournament["results"][match["id"]]

            if result.get("bye"):
                winner_name = result.get(
                    "participant1_name",
                    tournament["participants"][str(match["winner"])]["name"],
                )
                qualified.append(f"✅ **{winner_name}** (passage automatique)")
            else:
                winner_id = result["winner"]
                loser_id = (
                    match["participant2"]
                    if winner_id == match["participant1"]
                    else match["participant1"]
                )

                winner_name = result.get(
                    "participant1_name"
                    if winner_id == match["participant1"]
                    else "participant2_name"
                )
                loser_name = result.get(
                    "participant2_name"
                    if winner_id == match["participant1"]
                    else "participant1_name"
                )

                if not winner_name:
                    winner_name = tournament["participants"][str(winner_id)]["name"]
                if not loser_name:
                    loser_name = tournament["participants"][str(loser_id)]["name"]

                votes_winner = (
                    result["participant1_votes"]
                    if winner_id == match["participant1"]
                    else result["participant2_votes"]
                )
                votes_loser = (
                    result["participant2_votes"]
                    if winner_id == match["participant1"]
                    else result["participant1_votes"]
                )

                qualified.append(f"✅ **{winner_name}** ({votes_winner} votes)")
                eliminated.append(f"❌ {loser_name} ({votes_loser} votes)")

        embed = discord.Embed(
            title=f"📊 Résultats du Tour {round_num}",
            color=0x3498DB,
            timestamp=datetime.utcnow(),
        )

        if qualified:
            embed.add_field(
                name=f"🎯 Qualifiés pour le prochain tour ({len(qualified)})",
                value="\n".join(qualified[:10])
                + ("\n..." if len(qualified) > 10 else ""),
                inline=False,
            )

        if eliminated:
            embed.add_field(
                name=f"💔 Éliminés ({len(eliminated)})",
                value="\n".join(eliminated[:10])
                + ("\n..." if len(eliminated) > 10 else ""),
                inline=False,
            )

        matches_played = len(
            [r for r in tournament["results"].values() if not r.get("bye")]
        )
        total_votes = sum(
            r.get("participant1_votes", 0) + r.get("participant2_votes", 0)
            for r in tournament["results"].values()
            if not r.get("bye")
        )

        stats_text = f"Matchs joués: {matches_played}"
        if total_votes > 0:
            stats_text += f" | Total des votes: {total_votes}"

        if tournament.get("vote_mode") == "google_forms":
            stats_text += " | Mode: Google Forms"

        embed.set_footer(text=stats_text)

        await channel.send(embed=embed)

    async def create_next_round_matches(self, guild_id):
        """Crée les matchs du tour suivant."""
        tournament = self.active_tournaments[guild_id]
        current_round = tournament["bracket"]["current_round"]

        previous_matches = sorted(
            [
                m
                for m in tournament["bracket"]["matches"].values()
                if m["round"] == current_round - 1
            ],
            key=lambda x: x["id"],
        )

        winners = [m["winner"] for m in previous_matches if m["winner"] is not None]

        if len(winners) == 0:
            return
        elif len(winners) == 1:
            return

        random.shuffle(winners)

        new_matches = []
        for i in range(0, len(winners), 2):
            match_id = f"R{current_round}_M{len(new_matches) + 1}"
            new_match = {
                "id": match_id,
                "round": current_round,
                "participant1": winners[i],
                "participant2": winners[i + 1] if i + 1 < len(winners) else None,
                "winner": None,
                "votes": {},
            }
            new_matches.append(new_match)
            tournament["bracket"]["matches"][match_id] = new_match

    async def end_tournament(self, guild_id):
        """Termine le tournoi et annonce le gagnant."""
        tournament = self.active_tournaments.get(guild_id)
        if not tournament:
            return

        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(tournament["channel_id"])

        final_matches = [
            m
            for m in tournament["bracket"]["matches"].values()
            if m["round"] == tournament["bracket"]["rounds"]
        ]

        if final_matches and final_matches[0]["winner"] is not None:
            winner_id = final_matches[0]["winner"]
            winner = tournament["participants"][str(winner_id)]

            embed = discord.Embed(
                title="🏆 VICTOIRE! 🏆",
                description=f"# {winner['name']}\n\nremporte le tournoi **{tournament['theme']}**!",
                color=0xFFD700,
            )

            if winner.get("image"):
                embed.set_image(url=winner["image"])

            total_matches = len(
                [
                    m
                    for m in tournament["bracket"]["matches"].values()
                    if not m.get("bye")
                ]
            )
            total_votes = sum(
                r.get("participant1_votes", 0) + r.get("participant2_votes", 0)
                for r in tournament["results"].values()
            )

            embed.add_field(
                name="📊 Statistiques",
                value=f"Participants: {len(tournament['participants'])}\nMatchs joués: {total_matches}\nVotes totaux: {total_votes}\nMode de vote: {'Discord' if tournament.get('vote_mode', 'discord') == 'discord' else 'Google Forms'}",
                inline=False,
            )

            await channel.send(embed=embed)
        else:
            all_winners = [
                m["winner"]
                for m in tournament["bracket"]["matches"].values()
                if m["winner"] is not None
            ]
            if all_winners:
                winner_id = all_winners[-1]
                winner = tournament["participants"][str(winner_id)]

                embed = discord.Embed(
                    title="🏆 VICTOIRE! 🏆",
                    description=f"# {winner['name']}\n\nremporte le tournoi **{tournament['theme']}**!",
                    color=0xFFD700,
                )

                if winner.get("image"):
                    embed.set_image(url=winner["image"])

                await channel.send(embed=embed)
            else:
                error_embed = discord.Embed(
                    title="❌ Erreur du tournoi",
                    description="Le tournoi s'est terminé sans gagnant. Cela ne devrait pas arriver.",
                    color=0xE74C3C,
                )
                await channel.send(embed=error_embed)

        del self.active_tournaments[guild_id]
        tournaments = await self.config.guild(guild).active_tournaments()
        if str(guild_id) in tournaments:
            del tournaments[str(guild_id)]
            await self.config.guild(guild).active_tournaments.set(tournaments)

    async def stop_tournament(self, ctx):
        """Arrête le tournoi en cours."""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Seuls les administrateurs peuvent arrêter les tournois.")
            return

        guild_id = ctx.guild.id
        tournament = self.active_tournaments.get(guild_id)

        if tournament and tournament.get("current_form_id"):
            await self.google_forms_handler.delete_form(tournament["current_form_id"])

        if guild_id in self.active_tournaments:
            del self.active_tournaments[guild_id]

        tournaments = await self.config.guild(ctx.guild).active_tournaments()
        if str(guild_id) in tournaments:
            del tournaments[str(guild_id)]
            await self.config.guild(ctx.guild).active_tournaments.set(tournaments)

        await ctx.send("✅ Tournoi arrêté.")

    async def tournament_status(self, ctx):
        """Affiche le statut du tournoi en cours."""
        guild_id = ctx.guild.id
        tournament = self.active_tournaments.get(guild_id)

        if not tournament:
            await ctx.send("❌ Aucun tournoi en cours.")
            return

        embed = discord.Embed(
            title=f"📊 Statut du tournoi: {tournament['theme']}", color=0x3498DB
        )

        current_round = tournament["bracket"]["current_round"]
        total_rounds = tournament["bracket"]["rounds"]

        embed.add_field(
            name="Tour actuel", value=f"{current_round}/{total_rounds}", inline=True
        )
        embed.add_field(
            name="Participants", value=len(tournament["participants"]), inline=True
        )
        embed.add_field(
            name="Mode de vote",
            value="Discord"
            if tournament.get("vote_mode", "discord") == "discord"
            else "Google Forms",
            inline=True,
        )

        remaining = len(
            [
                m
                for m in tournament["bracket"]["matches"].values()
                if m["round"] == current_round and m["winner"] is None
            ]
        )
        embed.add_field(name="Matchs restants", value=remaining, inline=True)

        await ctx.send(embed=embed)
