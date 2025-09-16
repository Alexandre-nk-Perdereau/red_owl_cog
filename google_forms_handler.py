import os
import asyncio
import json
import aiohttp
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime


class GoogleFormsHandler:
    """Gère la création et la récupération des réponses Google Forms pour les tournois."""

    def __init__(self):
        self.credentials = None
        self.forms_service = None
        self.drive_service = None
        self.match_mappings = {}
        self.initialize_services()

    def initialize_services(self):
        """Initialise les services Google API."""
        print("[GoogleForms] Début de l'initialisation des services Google...")
        try:
            credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
            print(
                f"[GoogleForms] GOOGLE_CREDENTIALS_JSON présent: {bool(credentials_json)}"
            )

            if credentials_json:
                print(
                    "[GoogleForms] Tentative de chargement depuis GOOGLE_CREDENTIALS_JSON..."
                )
                try:
                    credentials_info = json.loads(credentials_json)
                    print(
                        f"[GoogleForms] JSON parsé avec succès. Type: {credentials_info.get('type')}"
                    )
                    self.credentials = (
                        service_account.Credentials.from_service_account_info(
                            credentials_info,
                            scopes=[
                                "https://www.googleapis.com/auth/forms",
                                "https://www.googleapis.com/auth/drive",
                            ],
                        )
                    )
                    print("[GoogleForms] Credentials créés depuis JSON")
                except json.JSONDecodeError as je:
                    print(f"[GoogleForms] Erreur de parsing JSON: {je}")
                except Exception as e:
                    print(f"[GoogleForms] Erreur création credentials depuis JSON: {e}")
            else:
                credentials_path = os.getenv(
                    "GOOGLE_CREDENTIALS_PATH",
                    "/home/alexa/cogs/red_owl_cog/google.json",
                )
                print(f"[GoogleForms] Recherche du fichier: {credentials_path}")
                print(
                    f"[GoogleForms] Fichier existe: {os.path.exists(credentials_path)}"
                )

                if os.path.exists(credentials_path):
                    print("[GoogleForms] Chargement depuis fichier...")
                    self.credentials = (
                        service_account.Credentials.from_service_account_file(
                            credentials_path,
                            scopes=[
                                "https://www.googleapis.com/auth/forms",
                                "https://www.googleapis.com/auth/drive",
                            ],
                        )
                    )
                    print("[GoogleForms] Credentials créés depuis fichier")
                else:
                    print("[GoogleForms] Aucun fichier de credentials trouvé")

            if self.credentials:
                print("[GoogleForms] Création des services Google...")
                self.forms_service = build("forms", "v1", credentials=self.credentials)
                print("[GoogleForms] Service Forms créé")
                self.drive_service = build("drive", "v3", credentials=self.credentials)
                print("[GoogleForms] Service Drive créé")
                print("[GoogleForms] Initialisation réussie!")
            else:
                print("[GoogleForms] ERREUR: Aucun credentials chargé")

        except Exception as e:
            print(
                f"[GoogleForms] ERREUR lors de l'initialisation des services Google: {type(e).__name__}: {e}"
            )
            import traceback

            print(f"[GoogleForms] Traceback complet:\n{traceback.format_exc()}")

    async def upload_image_to_drive(self, image_url):
        """Upload une image depuis une URL vers Google Drive et retourne l'ID du fichier."""
        try:
            print(f"[GoogleForms] Téléchargement de l'image: {image_url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status != 200:
                        print(
                            f"[GoogleForms] Erreur téléchargement image: {response.status}"
                        )
                        return None

                    image_data = await response.read()
                    content_type = response.headers.get("content-type", "image/jpeg")

            extension = ".jpg"
            if "png" in content_type:
                extension = ".png"
            elif "gif" in content_type:
                extension = ".gif"
            elif "webp" in content_type:
                extension = ".webp"

            import tempfile

            with tempfile.NamedTemporaryFile(
                delete=False, suffix=extension
            ) as tmp_file:
                tmp_file.write(image_data)
                tmp_file_path = tmp_file.name

            file_metadata = {
                "name": f"tournament_image_{datetime.now().timestamp()}{extension}",
                "mimeType": content_type,
            }

            from googleapiclient.http import MediaFileUpload

            media = MediaFileUpload(tmp_file_path, mimetype=content_type)

            file = (
                self.drive_service.files()
                .create(body=file_metadata, media_body=media, fields="id")
                .execute()
            )

            os.unlink(tmp_file_path)

            self.drive_service.permissions().create(
                fileId=file.get("id"), body={"type": "anyone", "role": "reader"}
            ).execute()

            print(f"[GoogleForms] Image uploadée avec succès: {file.get('id')}")
            return file.get("id")

        except Exception as e:
            print(f"[GoogleForms] Erreur upload image: {type(e).__name__}: {e}")
            import traceback

            print(f"[GoogleForms] Traceback:\n{traceback.format_exc()}")
            return None

    async def create_tournament_form(
        self, tournament_theme, round_number, matches, vote_duration
    ):
        """Crée un Google Form pour un tour de tournoi."""
        print(f"[GoogleForms] Création d'un formulaire pour le tour {round_number}...")
        print(f"[GoogleForms] forms_service présent: {self.forms_service is not None}")

        if not self.forms_service:
            print("[GoogleForms] ERREUR: Services Google non initialisés")
            return None, "Services Google non initialisés"

        try:
            form = {
                "info": {
                    "title": f"{tournament_theme} - Tour {round_number}",
                    "documentTitle": f"{tournament_theme} - Tour {round_number}",
                }
            }

            print("[GoogleForms] Appel API pour créer le formulaire...")
            result = self.forms_service.forms().create(body=form).execute()
            form_id = result["formId"]
            form_url = result["responderUri"]
            print(f"[GoogleForms] Formulaire créé avec succès! ID: {form_id}")

            self.match_mappings[form_id] = {}

            description_request = {
                "requests": [
                    {
                        "updateFormInfo": {
                            "info": {
                                "description": f"🎮 Votez pour vos préférés dans chaque match!\n\n⏱️ Temps limite: {vote_duration}"
                            },
                            "updateMask": "description",
                        }
                    }
                ]
            }

            print("[GoogleForms] Ajout de la description...")
            self.forms_service.forms().batchUpdate(
                formId=form_id, body=description_request
            ).execute()

            image_uploads = []
            for match in matches:
                if not match.get("bye"):
                    if match.get("participant1_image"):
                        image_uploads.append(
                            (
                                match["participant1_id"],
                                match["participant1_name"],
                                match["participant1_image"],
                            )
                        )
                    if match.get("participant2_image"):
                        image_uploads.append(
                            (
                                match["participant2_id"],
                                match["participant2_name"],
                                match["participant2_image"],
                            )
                        )

            image_mapping = {}
            if image_uploads:
                print(f"[GoogleForms] Upload de {len(image_uploads)} images...")
                upload_tasks = []
                for p_id, p_name, p_image in image_uploads:
                    upload_tasks.append(self.upload_image_to_drive(p_image))

                upload_results = await asyncio.gather(
                    *upload_tasks, return_exceptions=True
                )

                for (p_id, p_name, p_image), result in zip(
                    image_uploads, upload_results
                ):
                    if isinstance(result, str) and result:
                        image_mapping[p_id] = result
                        print(f"[GoogleForms] Image mappée pour {p_name} (ID: {p_id})")

            requests = []
            match_index = 0
            for _, match in enumerate(matches):
                if match.get("bye"):
                    continue

                p1_name = match["participant1_name"]
                p2_name = match["participant2_name"]
                p1_id = match["participant1_id"]
                p2_id = match["participant2_id"]

                self.match_mappings[form_id][match_index] = {
                    "p1_id": str(p1_id),
                    "p2_id": str(p2_id),
                    "p1_name": p1_name,
                    "p2_name": p2_name,
                }

                print(
                    f"[GoogleForms] Ajout de la question pour le match {match_index+1}: {p1_name} vs {p2_name}"
                )

                options = []

                option1 = {"value": p1_name}
                if p1_id in image_mapping:
                    option1["image"] = {
                        "sourceUri": f"https://drive.google.com/uc?export=view&id={image_mapping[p1_id]}",
                        "altText": p1_name,
                    }
                options.append(option1)

                option2 = {"value": p2_name}
                if p2_id in image_mapping:
                    option2["image"] = {
                        "sourceUri": f"https://drive.google.com/uc?export=view&id={image_mapping[p2_id]}",
                        "altText": p2_name,
                    }
                options.append(option2)

                question = {
                    "createItem": {
                        "item": {
                            "title": f"🥊 Match {match_index + 1}",
                            "description": f"{p1_name} VS {p2_name}",
                            "questionItem": {
                                "question": {
                                    "required": False,
                                    "choiceQuestion": {
                                        "type": "RADIO",
                                        "options": options,
                                        "shuffle": False,
                                    },
                                }
                            },
                        },
                        "location": {"index": match_index},
                    }
                }

                requests.append(question)
                match_index += 1

            if requests:
                print(
                    f"[GoogleForms] Ajout de {len(requests)} questions au formulaire..."
                )
                update_body = {"requests": requests}
                self.forms_service.forms().batchUpdate(
                    formId=form_id, body=update_body
                ).execute()
                print("[GoogleForms] Questions ajoutées avec succès")

            settings_requests = [
                {
                    "updateSettings": {
                        "settings": {"quizSettings": {"isQuiz": False}},
                        "updateMask": "quizSettings.isQuiz",
                    }
                }
            ]

            print("[GoogleForms] Configuration des paramètres du formulaire...")
            self.forms_service.forms().batchUpdate(
                formId=form_id, body={"requests": settings_requests}
            ).execute()

            print(f"[GoogleForms] Formulaire créé avec succès! URL: {form_url}")
            return form_id, form_url

        except HttpError as error:
            print(
                f"[GoogleForms] ERREUR HTTP lors de la création du formulaire: {error}"
            )
            print(
                f"[GoogleForms] Status: {error.resp.status}, Reason: {error.resp.reason}"
            )
            print(f"[GoogleForms] Content: {error.content}")
            return None, f"Erreur lors de la création du formulaire: {error}"
        except Exception as e:
            print(f"[GoogleForms] ERREUR inattendue: {type(e).__name__}: {e}")
            import traceback

            print(f"[GoogleForms] Traceback:\n{traceback.format_exc()}")
            return None, f"Erreur inattendue: {e}"

    async def get_form_responses(self, form_id):
        """Récupère les réponses d'un Google Form."""
        if not self.forms_service:
            return None

        try:
            responses = (
                self.forms_service.forms().responses().list(formId=form_id).execute()
            )

            print(
                f"[GoogleForms] Nombre de réponses reçues: {len(responses.get('responses', []))}"
            )
            form = self.forms_service.forms().get(formId=form_id).execute()
            print(
                f"[GoogleForms] Nombre d'items dans le formulaire: {len(form.get('items', []))}"
            )
            option_to_participant = {}
            items = form.get("items", [])

            for idx, item in enumerate(items):
                if "questionItem" in item:
                    print(f"[GoogleForms] Question {idx} - ID: {item['itemId']}")
                    options = (
                        item["questionItem"]["question"]
                        .get("choiceQuestion", {})
                        .get("options", [])
                    )
                    print(
                        f"[GoogleForms] Options: {[opt.get('value') for opt in options]}"
                    )

                    if (
                        form_id in self.match_mappings
                        and idx in self.match_mappings[form_id]
                    ):
                        match_info = self.match_mappings[form_id][idx]
                        for opt in options:
                            opt_value = opt.get("value", "")
                            if opt_value == match_info["p1_name"]:
                                option_to_participant[opt_value] = match_info["p1_id"]
                            elif opt_value == match_info["p2_name"]:
                                option_to_participant[opt_value] = match_info["p2_id"]

            print(
                f"[GoogleForms] Mapping option -> participant: {option_to_participant}"
            )

            votes_by_match = {}
            match_votes = {}

            if "responses" in responses:
                for response_idx, response in enumerate(responses["responses"]):
                    print(f"[GoogleForms] Traitement de la réponse {response_idx + 1}")

                    if "answers" in response:
                        for _, answer in response["answers"].items():
                            participant_name = None

                            if (
                                "textAnswers" in answer
                                and "answers" in answer["textAnswers"]
                            ):
                                for text_answer in answer["textAnswers"]["answers"]:
                                    participant_name = text_answer.get("value", "")
                                    break

                            if (
                                participant_name
                                and participant_name in option_to_participant
                            ):
                                participant_id = option_to_participant[participant_name]
                                print(
                                    f"[GoogleForms] Vote pour {participant_name} (ID: {participant_id})"
                                )

                                for match_idx, match_info in self.match_mappings[
                                    form_id
                                ].items():
                                    if participant_id in [
                                        match_info["p1_id"],
                                        match_info["p2_id"],
                                    ]:
                                        if match_idx not in match_votes:
                                            match_votes[match_idx] = {}

                                        if participant_id not in match_votes[match_idx]:
                                            match_votes[match_idx][participant_id] = 0

                                        match_votes[match_idx][participant_id] += 1
                                        break

            for match_idx, votes in match_votes.items():
                votes_by_match[str(match_idx)] = votes

            print(f"[GoogleForms] Votes compilés par match: {votes_by_match}")
            return votes_by_match

        except Exception as e:
            print(f"[GoogleForms] Erreur lors de la récupération des réponses: {e}")
            import traceback

            print(f"[GoogleForms] Traceback:\n{traceback.format_exc()}")
            return None

    async def close_form(self, form_id):
        """Arrête d'accepter les réponses d'un Google Form."""
        if not self.forms_service:
            return False

        try:
            form = self.forms_service.forms().get(formId=form_id).execute()

            update_body = {
                "requests": [
                    {
                        "updateFormInfo": {
                            "info": {
                                "title": form["info"]["title"] + " [FERMÉ]",
                                "description": "❌ Ce formulaire n'accepte plus de réponses.\n\nLes résultats sont en cours de traitement...",
                            },
                            "updateMask": "title,description",
                        }
                    }
                ]
            }

            self.forms_service.forms().batchUpdate(
                formId=form_id, body=update_body
            ).execute()

            return True

        except Exception as e:
            print(f"Erreur lors de la fermeture du formulaire: {e}")
            return False

    async def delete_form(self, form_id):
        """Supprime un Google Form via Google Drive API."""
        if not self.drive_service:
            print("Drive service non initialisé, impossible de supprimer le formulaire")
            return False

        try:
            if form_id in self.match_mappings:
                del self.match_mappings[form_id]

            self.drive_service.files().delete(fileId=form_id).execute()
            print(f"Formulaire {form_id} supprimé avec succès")
            return True
        except HttpError as error:
            if error.resp.status == 404:
                print(f"Formulaire {form_id} déjà supprimé ou introuvable")
                return True
            else:
                print(
                    f"Erreur HTTP lors de la suppression du formulaire {form_id}: {error}"
                )
                return False
        except Exception as e:
            print(f"Erreur lors de la suppression du formulaire {form_id}: {e}")
            return False
