import discord
import random


class DiceCommands:
    @staticmethod
    async def hexa(ctx, num_dice: int, extra_success: int = 0):
        """Lance des d6 (succès sur 3+, les 6 se relancent)."""
        if num_dice < 1:
            await ctx.send("Le nombre de dés doit être au minimum 1.")
            return
        if num_dice > 100:
            await ctx.send("Le nombre de dés doit être au maximum 100.")
            return

        rolls, success = DiceCommands.roll_dices(num_dice)
        initial_success = success
        success += extra_success

        embed = discord.Embed(title="🎲 Résultat des lancers", color=0x4CAF50)
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar.url)

        success_text = f"**{initial_success}** succès"
        if extra_success != 0:
            success_text += (
                f" + **{extra_success}** succès supplémentaires = **{success}** total"
            )
        embed.add_field(name="🏆 Succès", value=success_text, inline=False)

        detailed_rolls = " \n ".join(
            f"🎲 Lancer {i+1}: " + ", ".join(DiceCommands.format_roll(r) for r in roll)
            for i, roll in enumerate(rolls)
        )
        embed.add_field(name="Détail des lancers", value=detailed_rolls, inline=False)
        embed.set_footer(text=f"Demandé par {ctx.author.display_name}")

        await ctx.send(embed=embed)

    @staticmethod
    async def fate(ctx, bonus: int = 0):
        """Lance 4dF ([-], [0], [+]) avec bonus optionnel."""
        dice = [-1, 0, 1]
        rolls = [random.choice(dice) for _ in range(4)]
        total = sum(rolls) + bonus

        embed = discord.Embed(title="🎲 Résultat du lancer Fate", color=0x4CAF50)
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar.url)

        roll_details = " ".join(DiceCommands.format_fate_die(r) for r in rolls)
        embed.add_field(name="Lancers", value=roll_details, inline=False)

        if bonus != 0:
            embed.add_field(name="Bonus", value=f"{bonus:+}", inline=False)

        embed.add_field(name="Total", value=str(total), inline=False)

        await ctx.send(embed=embed)

    @staticmethod
    def roll_dices(num_dice: int):
        """Effectue les lancers et relances (6 → relance)."""
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

    @staticmethod
    def format_roll(roll):
        if roll == 6:
            return f"**{roll}**"
        return str(roll)

    @staticmethod
    def format_fate_die(roll):
        if roll == -1:
            return "[-]"
        elif roll == 1:
            return "[+]"
        else:
            return "[0]"
