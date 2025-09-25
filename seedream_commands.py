import asyncio
import os
import io
import aiohttp
import discord
import dotenv

FAL_T2I_URL = "https://queue.fal.run/fal-ai/bytedance/seedream/v4/text-to-image"
FAL_EDIT_URL = "https://queue.fal.run/fal-ai/bytedance/seedream/v4/edit"
FAL_REQ_BASE = "https://queue.fal.run/fal-ai/bytedance/requests"


class SeedreamCommands:
    """
    Commandes d'image pour Seedream v4 (FAL).
    - Si aucune image jointe : text-to-image
    - Sinon : edit (img2img) avec les images du message
    """

    def __init__(self, bot):
        self.bot = bot
        dotenv.load_dotenv("/home/alexa/cogs/red_owl_cog/.env", override=True)
        self.fal_key = os.getenv("FAL_KEY", None)

    @staticmethod
    def _is_image_attachment(att: discord.Attachment) -> bool:
        if att.content_type and att.content_type.startswith("image/"):
            return True
        name = (att.filename or "").lower()
        return name.endswith((".png", ".jpg", ".jpeg", ".webp"))

    @staticmethod
    def _validate_size(value: int) -> int:
        value = int(value)
        if value < 1024 or value > 4096:
            raise ValueError("La taille doit être comprise entre 1024 et 4096 px.")
        return value

    async def _poll_status(self, session, headers, request_id, wait_msg, timeout_s=600):
        status_url = f"{FAL_REQ_BASE}/{request_id}/status"
        t0 = asyncio.get_event_loop().time()
        delay = 1.5
        last_notice = 0.0

        while True:
            async with session.get(status_url, headers=headers, timeout=60) as r:
                if r.status not in (200, 202):
                    text = await r.text()
                    raise RuntimeError(f"Statut API {r.status}: {text[:300]}")
                s = await r.json()

            status = (s.get("status") or s.get("state") or "").upper()
            err = s.get("error")
            done = (
                status in {"COMPLETED", "SUCCEEDED", "SUCCESS", "DONE"}
                or s.get("completed") is True
            )
            failed = (
                status in {"FAILED", "ERROR", "CANCELED", "CANCELLED"}
                or s.get("failed") is True
            )

            now = asyncio.get_event_loop().time()
            if now - last_notice > 6:
                last_notice = now
                extra = []
                if "position" in s:
                    extra.append(f"pos {s['position']}")
                if "eta" in s:
                    extra.append(f"eta {int(s['eta'])}s")
                suffix = f" ({', '.join(extra)})" if extra else ""
                await wait_msg.edit(
                    content=f"🧪 Seedream v4 — {status or 'EN COURS'}… *{int(now - t0)}s*{suffix}"
                )

            if err or failed:
                raise RuntimeError(f"Traitement en erreur: {err or status}")

            if done:
                return True

            if now - t0 > timeout_s:
                return False

            await asyncio.sleep(delay)
            delay = min(delay * 1.2, 3.0)

    async def _fetch_result(self, session, headers, request_id, response_url=None):
        result_url = response_url or f"{FAL_REQ_BASE}/{request_id}"
        async with session.get(result_url, headers=headers, timeout=180) as r:
            if r.status // 100 != 2:
                text = await r.text()
                raise RuntimeError(f"Récupération résultat {r.status}: {text[:300]}")
            return await r.json()

    async def gen(self, ctx, width: int, height: int, *, prompt: str):
        """
        Génère ou édite une image avec Seedream v4 (FAL).
        Usage: !gen <width> <height> <prompt>
        - Sans image jointe : génération (txt2img)
        - Avec images jointes : édition (img2img) sur les pièces jointes (max 10)
        Contraintes: width/height ∈ [1024, 4096]. Safety désactivée.
        """
        if not self.fal_key:
            await ctx.send(
                "⚠️ Variable d'environnement **FAL_KEY** absente. Configure-la avant d'utiliser `!gen`."
            )
            return

        try:
            width = self._validate_size(width)
            height = self._validate_size(height)
        except ValueError as e:
            await ctx.send(f"❌ {e}")
            return

        atts = [a for a in ctx.message.attachments if self._is_image_attachment(a)]
        image_urls = [a.url for a in atts][:10]

        base_payload = {
            "prompt": prompt,
            "image_size": {"width": width, "height": height},
            "num_images": 1,
            "enable_safety_checker": False,
        }

        is_edit = len(image_urls) > 0
        url = FAL_EDIT_URL if is_edit else FAL_T2I_URL
        if is_edit:
            base_payload["image_urls"] = image_urls

        action_text = "édition" if is_edit else "génération"
        wait_msg = await ctx.send(f"🧪 Seedream v4 — {action_text} en cours…")

        headers = {
            "Authorization": f"Key {self.fal_key}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=headers, json=base_payload, timeout=300
                ) as resp:
                    if resp.status // 100 != 2:
                        text = await resp.text()
                        await wait_msg.edit(
                            content=f"❌ Erreur API ({resp.status}) : {text[:500]}"
                        )
                        return
                    data = await resp.json()

                images = (data or {}).get("images") or []
                seed = (data or {}).get("seed")
                request_id = (data or {}).get("request_id")

                if not images:
                    if not request_id:
                        await wait_msg.edit(
                            content="❌ Réponse API sans `images` ni `request_id`. Impossible de continuer."
                        )
                        return

                    ok = await self._poll_status(
                        session, headers, request_id, wait_msg, timeout_s=600
                    )
                    if not ok:
                        await wait_msg.edit(
                            content="❌ Timeout en attendant la génération. Réessaie plus tard."
                        )
                        return

                    status_url = f"{FAL_REQ_BASE}/{request_id}/status"
                    response_url = None
                    try:
                        async with session.get(
                            status_url, headers=headers, timeout=60
                        ) as r:
                            if r.status // 100 == 2:
                                s = await r.json()
                                response_url = s.get("response_url")
                    except Exception:
                        response_url = None

                    result = await self._fetch_result(
                        session, headers, request_id, response_url=response_url
                    )
                    images = (result or {}).get("images") or []
                    seed = (result or {}).get("seed")

                if not images:
                    await wait_msg.edit(
                        content="❌ Aucun visuel dans le résultat final."
                    )
                    return

                img_meta = images[0] or {}
                img_url = img_meta.get("url")
                if not img_url:
                    await wait_msg.edit(
                        content="❌ URL d’image manquante dans le résultat."
                    )
                    return

                async with session.get(img_url, timeout=180) as img_resp:
                    if img_resp.status // 100 != 2:
                        await wait_msg.edit(
                            content=f"❌ Impossible de récupérer l’image ({img_resp.status})."
                        )
                        return
                    content_type = (img_resp.headers.get("Content-Type") or "").lower()
                    ext = ".png" if "png" in content_type else ".jpg"
                    data_bytes = await img_resp.read()

            embed = discord.Embed(
                title="🖼️ Seedream v4",
                description=(
                    "**Mode** : Edit (img2img)"
                    if is_edit
                    else "**Mode** : Text-to-Image"
                ),
                color=0x5865F2,
            )
            embed.add_field(name="Prompt", value=prompt[:1024], inline=False)
            embed.add_field(name="Taille", value=f"{width}×{height}", inline=True)
            if seed is not None:
                embed.add_field(name="Seed", value=str(seed), inline=True)

            file = discord.File(io.BytesIO(data_bytes), filename=f"seedream_v4{ext}")
            embed.set_image(url=f"attachment://seedream_v4{ext}")

            await wait_msg.edit(content=None, embed=embed, attachments=[file])

        except aiohttp.ClientError as e:
            await wait_msg.edit(content=f"❌ Erreur réseau : {e}")
        except Exception as e:
            await wait_msg.edit(
                content=f"❌ Erreur inattendue : {type(e).__name__}: {e}"
            )
