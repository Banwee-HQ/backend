# import httpx
# from typing import Optional
# from fastapi import BackgroundTasks
# from core.config import settings


# class WhatsappBotHandler:
#     def __init__(self, whatsapp_token, phone_number_id, background_tasks: BackgroundTasks):
#         self.background_tasks = background_tasks
#         self.whatsapp_token = whatsapp_token
#         self.phone_number_id = phone_number_id
#         self.api_url = f"https://graph.facebook.com/v15.0/{self.phone_number_id}/messages"

#     async def send_whatsapp(
#         self,
#         to_phone_number: str,
#         message: str,
#         media_url: Optional[str] = None
#     ):
#         headers = {
#             "Authorization": f"Bearer {self.whatsapp_token}",
#             "Content-Type": "application/json"
#         }

#         # Prepare message data payload
#         if media_url:
#             payload = {
#                 "messaging_product": "whatsapp",
#                 "to": to_phone_number,
#                 "type": "image",
#                 "image": {"link": media_url, "caption": message}
#             }
#         else:
#             payload = {
#                 "messaging_product": "whatsapp",
#                 "to": to_phone_number,
#                 "type": "text",
#                 "text": {"body": message}
#             }

#         async with httpx.AsyncClient() as client:
#             response = await client.post(self.api_url, headers=headers, json=payload)
#             response.raise_for_status()
#             return response.json()


# WHATSAPP_ACCESS_TOKEN = str(settings.WHATSAPP_ACCESS_TOKEN)
# PHONE_NUMBER_ID = str(settings.PHONE_NUMBER_ID)

# whatapp_bot = WhatsappBotHandler(WHATSAPP_ACCESS_TOKEN, PHONE_NUMBER_ID, BackgroundTasks)
