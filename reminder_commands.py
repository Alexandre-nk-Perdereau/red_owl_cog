"""
Système de rappels pour Red Discord Bot.
Supporte les rappels uniques et récurrents avec persistance.
"""

import asyncio
import re
from datetime import datetime
from typing import Optional, Dict
import discord
from redbot.core import Config, commands


class ReminderCommands:
    """Gère tous les rappels avec persistance et fonctionnalités avancées."""

    def __init__(self, bot, config: Config):
        self.bot = bot
        self.config = config
        self.active_tasks: Dict[str, asyncio.Task] = {}

        default_user = {"reminders": []}
        self.config.register_user(**default_user)

        self.bot.loop.create_task(self._restore_reminders())

    async def _restore_reminders(self):
        """Restaure tous les rappels actifs après un redémarrage."""
        await self.bot.wait_until_ready()

        all_users = await self.config.all_users()
        now = datetime.now().timestamp()
        restored_count = 0

        for user_id, user_data in all_users.items():
            reminders = user_data.get("reminders", [])
            valid_reminders = []

            for reminder in reminders:
                if reminder["timestamp"] <= now:
                    if now - reminder["timestamp"] < 300:
                        await self._send_reminder(reminder)

                    if reminder.get("interval"):
                        reminder["timestamp"] = now + reminder["interval"]
                        valid_reminders.append(reminder)
                        self._schedule_reminder(reminder)
                        restored_count += 1
                else:
                    valid_reminders.append(reminder)
                    self._schedule_reminder(reminder)
                    restored_count += 1

            await self.config.user_from_id(user_id).reminders.set(valid_reminders)

        if restored_count > 0:
            print(f"[ReminderCommands] {restored_count} rappel(s) restauré(s)")

    def _parse_duration(self, duration_str: str) -> Optional[int]:
        """
        Parse une durée flexible (ex: 10m, 2h30m, 1d3h15m).
        Retourne le nombre de secondes ou None si invalide.
        """
        pattern = r"(\d+)([smhdwSMHDW])"
        matches = re.findall(pattern, duration_str)

        if not matches:
            return None

        time_map = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}

        total_seconds = 0
        for amount, unit in matches:
            total_seconds += int(amount) * time_map.get(unit.lower(), 0)

        return total_seconds if total_seconds > 0 else None

    def _format_duration(self, seconds: int) -> str:
        """Formate une durée en secondes en texte lisible."""
        parts = []

        units = [
            ("semaine", 604800),
            ("jour", 86400),
            ("heure", 3600),
            ("minute", 60),
            ("seconde", 1),
        ]

        for name, duration in units:
            if seconds >= duration:
                count = seconds // duration
                seconds %= duration
                plural = "s" if count > 1 else ""
                parts.append(f"{count} {name}{plural}")

        return ", ".join(parts) if parts else "0 seconde"

    def _format_timestamp(self, timestamp: float) -> str:
        """Formate un timestamp en date lisible Discord."""
        return f"<t:{int(timestamp)}:F> (<t:{int(timestamp)}:R>)"

    async def _send_reminder(self, reminder: dict):
        """Envoie un rappel à l'utilisateur."""
        try:
            channel = self.bot.get_channel(reminder["channel_id"])
            if not channel:
                return

            user = self.bot.get_user(reminder["user_id"])
            if not user:
                return

            embed = discord.Embed(
                title="⏰ Rappel",
                description=reminder["message"],
                color=discord.Color.orange(),
                timestamp=datetime.now(),
            )

            if reminder.get("interval"):
                next_time = reminder["timestamp"] + reminder["interval"]
                embed.add_field(
                    name="Prochain rappel",
                    value=self._format_timestamp(next_time),
                    inline=False,
                )

            await channel.send(user.mention, embed=embed)

        except Exception as e:
            print(f"[ReminderCommands] Erreur envoi rappel: {e}")

    def _schedule_reminder(self, reminder: dict):
        """Schedule l'envoi d'un rappel."""
        reminder_id = reminder["id"]

        async def reminder_task():
            now = datetime.now().timestamp()
            wait_time = max(0, reminder["timestamp"] - now)

            await asyncio.sleep(wait_time)
            await self._send_reminder(reminder)

            user_id = reminder["user_id"]
            async with self.config.user_from_id(user_id).reminders() as reminders:
                for i, r in enumerate(reminders):
                    if r["id"] == reminder_id:
                        if r.get("interval"):
                            reminders[i]["timestamp"] = (
                                datetime.now().timestamp() + r["interval"]
                            )
                            self._schedule_reminder(reminders[i])
                        else:
                            reminders.pop(i)
                        break

            if reminder_id in self.active_tasks:
                del self.active_tasks[reminder_id]

        if reminder_id in self.active_tasks:
            self.active_tasks[reminder_id].cancel()

        self.active_tasks[reminder_id] = self.bot.loop.create_task(reminder_task())

    async def remind(
        self, ctx: commands.Context, duration: str, *, message: str = "Votre rappel !"
    ):
        """
        Crée un rappel.

        Exemples:
        - !remind 10m Prendre une pause
        - !remind 2h30m Réunion importante
        - !remind 1d Vérifier les emails
        """
        seconds = self._parse_duration(duration)

        if seconds is None or seconds < 10:
            await ctx.send(
                "❌ **Durée invalide.** Utilisez le format: `10m`, `2h30m`, `1d3h`, etc.\n"
                "Unités: s (secondes), m (minutes), h (heures), d (jours), w (semaines)\n"
                "Durée minimum: 10 secondes"
            )
            return

        if seconds > 31536000:
            await ctx.send("❌ **Durée trop longue.** Maximum: 1 an")
            return

        reminder_id = f"{ctx.author.id}_{int(datetime.now().timestamp() * 1000)}"
        timestamp = datetime.now().timestamp() + seconds

        reminder = {
            "id": reminder_id,
            "user_id": ctx.author.id,
            "channel_id": ctx.channel.id,
            "guild_id": ctx.guild.id if ctx.guild else None,
            "message": message[:1000],
            "timestamp": timestamp,
            "interval": None,
            "created_at": datetime.now().timestamp(),
        }

        async with self.config.user(ctx.author).reminders() as reminders:
            reminders.append(reminder)

        self._schedule_reminder(reminder)

        embed = discord.Embed(
            title="✅ Rappel créé", description=message, color=discord.Color.green()
        )
        embed.add_field(
            name="Quand", value=self._format_timestamp(timestamp), inline=False
        )
        embed.add_field(name="Dans", value=self._format_duration(seconds), inline=False)
        embed.set_footer(text=f"ID: {reminder_id}")

        await ctx.send(embed=embed)

    async def remind_repeat(
        self, ctx: commands.Context, interval: str, *, message: str = "Rappel récurrent"
    ):
        """
        Crée un rappel récurrent.

        Exemples:
        - !remind_repeat 1h Boire de l'eau
        - !remind_repeat 1d Standup meeting
        """
        seconds = self._parse_duration(interval)

        if seconds is None or seconds < 60:
            await ctx.send("❌ **Intervalle invalide.** Minimum: 1 minute (1m)")
            return

        if seconds > 2592000:
            await ctx.send("❌ **Intervalle trop long.** Maximum: 30 jours")
            return

        reminder_id = f"{ctx.author.id}_{int(datetime.now().timestamp() * 1000)}"
        timestamp = datetime.now().timestamp() + seconds

        reminder = {
            "id": reminder_id,
            "user_id": ctx.author.id,
            "channel_id": ctx.channel.id,
            "guild_id": ctx.guild.id if ctx.guild else None,
            "message": message[:1000],
            "timestamp": timestamp,
            "interval": seconds,
            "created_at": datetime.now().timestamp(),
        }

        async with self.config.user(ctx.author).reminders() as reminders:
            reminders.append(reminder)

        self._schedule_reminder(reminder)

        embed = discord.Embed(
            title="🔄 Rappel récurrent créé",
            description=message,
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="Premier rappel", value=self._format_timestamp(timestamp), inline=False
        )
        embed.add_field(
            name="Intervalle", value=self._format_duration(seconds), inline=False
        )
        embed.set_footer(text=f"ID: {reminder_id}")

        await ctx.send(embed=embed)

    async def remind_list(self, ctx: commands.Context):
        """Liste tous vos rappels actifs."""
        reminders = await self.config.user(ctx.author).reminders()

        if not reminders:
            await ctx.send("📭 Vous n'avez aucun rappel actif.")
            return

        reminders.sort(key=lambda r: r["timestamp"])

        embed = discord.Embed(
            title=f"📋 Vos rappels ({len(reminders)})", color=discord.Color.blue()
        )

        for i, reminder in enumerate(reminders[:10], 1):
            is_recurring = "🔄" if reminder.get("interval") else "⏰"
            time_info = self._format_timestamp(reminder["timestamp"])

            if reminder.get("interval"):
                time_info += (
                    f"\n*Répète tous les {self._format_duration(reminder['interval'])}*"
                )

            embed.add_field(
                name=f"{is_recurring} {i}. {reminder['message'][:50]}{'...' if len(reminder['message']) > 50 else ''}",
                value=time_info,
                inline=False,
            )

        if len(reminders) > 10:
            embed.set_footer(
                text=f"... et {len(reminders) - 10} autre(s). Utilisez !remind_clear pour nettoyer."
            )

        await ctx.send(embed=embed)

    async def remind_cancel(self, ctx: commands.Context, reminder_index: int):
        """
        Annule un rappel spécifique.

        Usage: !remind_cancel <numéro>
        Utilisez !remind_list pour voir les numéros.
        """
        async with self.config.user(ctx.author).reminders() as reminders:
            if not reminders:
                await ctx.send("❌ Vous n'avez aucun rappel actif.")
                return

            if reminder_index < 1 or reminder_index > len(reminders):
                await ctx.send(
                    f"❌ Numéro invalide. Utilisez un nombre entre 1 et {len(reminders)}."
                )
                return

            reminders.sort(key=lambda r: r["timestamp"])
            reminder = reminders[reminder_index - 1]

            if reminder["id"] in self.active_tasks:
                self.active_tasks[reminder["id"]].cancel()
                del self.active_tasks[reminder["id"]]

            reminders.remove(reminder)

            await ctx.send(
                f"✅ Rappel **{reminder_index}** annulé : *{reminder['message'][:100]}*"
            )

    async def remind_clear(self, ctx: commands.Context):
        """Supprime tous vos rappels."""
        reminders = await self.config.user(ctx.author).reminders()

        if not reminders:
            await ctx.send("❌ Vous n'avez aucun rappel à supprimer.")
            return

        count = len(reminders)

        for reminder in reminders:
            if reminder["id"] in self.active_tasks:
                self.active_tasks[reminder["id"]].cancel()
                del self.active_tasks[reminder["id"]]

        await self.config.user(ctx.author).reminders.set([])

        await ctx.send(f"✅ **{count}** rappel(s) supprimé(s).")
