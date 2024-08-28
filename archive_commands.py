import discord
import os
import aiohttp
import asyncio


class ArchiveCommands:
    def __init__(self, bot):
        self.bot = bot

    async def archive_thread(self, ctx, thread_url: str):
        thread_id = int(thread_url.split("/")[-1])
        try:
            thread = await self.bot.fetch_channel(thread_id)
        except discord.errors.NotFound:
            await ctx.send("Fil non trouvé. Vérifiez l'URL.")
            return

        base_folder = f"archive_{thread_id}"
        os.makedirs(base_folder, exist_ok=True)
        os.makedirs(os.path.join(base_folder, "images"), exist_ok=True)
        os.makedirs(os.path.join(base_folder, "audio"), exist_ok=True)
        os.makedirs(os.path.join(base_folder, "autres"), exist_ok=True)

        status_message = await ctx.send("Début de l'archivage...")
        await self.archive_messages(thread, base_folder, status_message)
        await status_message.edit(
            content=f"Archivage terminé. Les fichiers sont dans le dossier '{base_folder}'."
        )

    async def archive_channel(self, ctx, channel: discord.TextChannel):
        base_folder = f"archive_channel_{channel.id}"
        os.makedirs(base_folder, exist_ok=True)
        status_message = await ctx.send("Début de l'archivage du canal...")
        await self.archive_messages(channel, base_folder, status_message)

        active_threads = channel.threads
        archived_threads = []
        async for thread in channel.archived_threads():
            archived_threads.append(thread)

        all_threads = active_threads + archived_threads
        total_threads = len(all_threads)

        for index, thread in enumerate(all_threads):
            thread_folder = os.path.join(base_folder, f"thread_{thread.id}")
            os.makedirs(thread_folder, exist_ok=True)
            await status_message.edit(
                content=f"Archivage du fil {index + 1}/{total_threads}: {thread.name}"
            )
            await self.archive_messages(
                thread, thread_folder, status_message, is_thread=True
            )

        await status_message.edit(
            content=f"Archivage du canal terminé. Les fichiers sont dans le dossier '{base_folder}'."
        )

    async def archive_messages(self, channel, folder, status_message, is_thread=False):
        os.makedirs(os.path.join(folder, "images"), exist_ok=True)
        os.makedirs(os.path.join(folder, "audio"), exist_ok=True)
        os.makedirs(os.path.join(folder, "autres"), exist_ok=True)

        messages_file = os.path.join(folder, "messages.txt")
        attachment_counter = 1
        total_messages = 0

        async for _ in channel.history(limit=None, oldest_first=True):
            total_messages += 1

        with open(messages_file, "w", encoding="utf-8") as f:
            async for message in channel.history(limit=None, oldest_first=True):
                f.write(
                    f"[{message.created_at}] {message.author.name}: {message.content}\n"
                )

                for attachment in message.attachments:
                    ext = os.path.splitext(attachment.filename)[1].lower()
                    subfolder = (
                        "images"
                        if ext in [".jpg", ".jpeg", ".png", ".gif"]
                        else "audio"
                        if ext in [".mp3", ".wav", ".ogg"]
                        else "autres"
                    )
                    new_filename = f"{attachment_counter}{ext}"
                    file_path = await self.download_attachment(
                        attachment.url, os.path.join(folder, subfolder), new_filename
                    )
                    if file_path:
                        f.write(f"[Pièce jointe] {file_path}\n")
                        attachment_counter += 1

                if not is_thread and message.thread:
                    thread_folder = os.path.join(folder, f"thread_{message.thread.id}")
                    f.write(
                        f"\n[THREAD] {message.author.name} a ouvert un fil à partir de ce message. Fil accessible au chemin : {thread_folder}\n\n"
                    )

                f.write("\n")

                if total_messages % 100 == 0:
                    if is_thread:
                        await status_message.edit(
                            content=f"{status_message.content}\nProgression: {total_messages} messages archivés"
                        )
                    else:
                        await status_message.edit(
                            content=f"Archivage en cours... {total_messages} messages archivés"
                        )

                await asyncio.sleep(0.01)

        return total_messages

    async def download_attachment(self, url, folder, filename):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    file_path = os.path.join(folder, filename)
                    with open(file_path, "wb") as f:
                        f.write(await resp.read())
                    return file_path
        return None
