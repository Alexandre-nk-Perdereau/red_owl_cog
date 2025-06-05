import discord
import asyncio
import random
import math
from datetime import datetime


class TournoiCommands:
    """Système de gestion de tournois à élimination directe."""

    def __init__(self, bot, config):
        self.bot = bot
        self.config = config
        self.active_tournaments = {}  # guild_id -> tournament_data
        self.setup_sessions = {}  # user_id -> setup_data

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
        }

        try:
            embed = discord.Embed(
                title="🏆 Configuration du Tournoi",
                description="Bienvenue dans l'assistant de création de tournoi!\n\n**Étape 1/5: Thème du tournoi**\n\nQuel est le thème de votre tournoi? (ex: Les méchants de films, Les meilleurs desserts, etc.)",
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
                description=f"**Thème défini:** {content}\n\n**Étape 2/5: Participants**\n\nMaintenant, envoie-moi les participants un par un.\n\n**Instructions:**\n• Écris simplement le nom du participant\n• Tu peux joindre une image au message (optionnel)\n• Exemple: `Dark Vador` + image attachée\n\nTape `fini` quand tu as ajouté tous les participants (minimum 4).",
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

                session["step"] = "channel"
                channels_list = "\n".join(
                    [
                        f"{i+1}. {ch.name}"
                        for i, ch in enumerate(session["guild"].text_channels)
                    ]
                )

                embed = discord.Embed(
                    title="🏆 Configuration du Tournoi",
                    description=f"**Participants:** {len(session['participants'])} ajoutés\n\n**Étape 3/5: Canal du tournoi**\n\nDans quel canal veux-tu que le tournoi se déroule? Envoie le numéro ou le nom du canal.\n\n{channels_list[:1900]}",
                    color=0x3498DB,
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
                description=f"**Canal sélectionné:** #{channel.name}\n\n**Étape 4/5: Durée des votes**\n\nCombien de temps doit durer chaque vote?\n\nExemples:\n- `30m` pour 30 minutes\n- `2h` pour 2 heures\n- `1d` pour 1 jour",
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
                description=f"**Durée des votes:** {self.format_duration(duration)}\n\n**Étape 5/5: Délai entre les tours**\n\nCombien de temps entre la fin d'un tour et le début du suivant?\n\nExemples:\n- `5m` pour 5 minutes\n- `30m` pour 30 minutes\n- `1h` pour 1 heure",
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
                description=f"**Thème:** {session['theme']}\n**Participants:** {len(session['participants'])}\n**Canal:** #{session['channel'].name}\n**Durée des votes:** {self.format_duration(session['vote_duration'])}\n**Délai entre tours:** {self.format_duration(session['between_rounds_delay'])}",
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
        }

        self.active_tournaments[guild.id] = tournament_data
        tournaments = await self.config.guild(guild).active_tournaments()
        tournaments[str(guild.id)] = tournament_data
        await self.config.guild(guild).active_tournaments.set(tournaments)

        embed = discord.Embed(
            title=f"🏆 TOURNOI: {session['theme']}",
            description=f"Un nouveau tournoi commence avec **{len(participants)} participants**!\n\nLe tournoi se déroulera en élimination directe. Votez pour votre préféré dans chaque match!\n\n**Durée des votes:** {self.format_duration(session['vote_duration'])}\n**Créé par:** {session['creator'].mention}",
            color=0xF39C12,
            timestamp=datetime.utcnow(),
        )
        embed.set_footer(text="Que le meilleur gagne!")

        announcement = await session["channel"].send(embed=embed)
        await announcement.pin()

        await asyncio.sleep(5)

        await self.start_round(guild.id)

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
        tournament = self.active_tournaments.get(guild_id)
        if not tournament:
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        channel = guild.get_channel(tournament["channel_id"])
        if not channel:
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
            description=f"**{len(round_matches)} matchs** vont se dérouler!\n\nVotez avec les réactions 1️⃣ et 2️⃣",
            color=0xE74C3C,
        )
        await channel.send(embed=embed)

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
                tasks.append(self.run_match(guild_id, match))

        if bye_messages:
            await asyncio.gather(*bye_messages)
            await asyncio.sleep(2)

        if tasks:
            await asyncio.gather(*tasks)

        if round_matches:
            await self.post_round_summary(guild_id, current_round)

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
                if m["round"] == current_round and m["winner"] is not None
            ]
        )

        if winners_count == 1 and not remaining_matches:
            await self.end_tournament(guild_id)
            return
        elif winners_count == 0 and not remaining_matches:
            if current_round > 1:
                prev_winners = [
                    m["winner"]
                    for m in tournament["bracket"]["matches"].values()
                    if m["round"] == current_round - 1 and m["winner"] is not None
                ]
                if len(prev_winners) == 1:
                    await self.end_tournament(guild_id)
                    return

        await asyncio.sleep(tournament["between_rounds_delay"])

        tournament["bracket"]["current_round"] += 1
        await self.create_next_round_matches(guild_id)
        await self.start_round(guild_id)

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

        embed.set_footer(text=stats_text)

        await channel.send(embed=embed)

    async def run_match(self, guild_id, match):
        """Exécute un match individuel."""
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
                value=f"Participants: {len(tournament['participants'])}\nMatchs joués: {total_matches}\nVotes totaux: {total_votes}",
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

        remaining = len(
            [
                m
                for m in tournament["bracket"]["matches"].values()
                if m["round"] == current_round and m["winner"] is None
            ]
        )
        embed.add_field(name="Matchs restants", value=remaining, inline=True)

        await ctx.send(embed=embed)
