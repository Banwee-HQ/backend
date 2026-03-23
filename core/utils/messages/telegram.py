# from telegram import Update, Bot
# from telegram.ext import ContextTypes
# from typing import Optional


# class TelegramBotHandler:
#     def __init__(self, token: str):
#         self.bot = Bot(token=token)

#     async def get_bot_info(self):
#         me = await self.bot.get_me()
#         print(f"Bot Name: {me.firstname}")
#         print(f"Bot Username: @{me.username}")
#         return me

#     async def send(
#         self,
#         chat_id: int,
#         text: Optional[str] = None,
#         photo_path: Optional[str] = None,
#         document_path: Optional[str] = None,
#         photo_caption: Optional[str] = None,
#         document_caption: Optional[str] = None,
#     ):
#         if text:
#             await self.bot.send_message(chat_id=chat_id, text=text)

#         if photo_path:
#             with open(photo_path, "rb") as photo:
#                 await self.bot.send_photo(chat_id=chat_id, photo=photo, caption=photo_caption or "")

#         if document_path:
#             with open(document_path, "rb") as doc:
#                 await self.bot.send_document(chat_id=chat_id, document=doc, caption=document_caption or "")

#     async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
#         await update.message.reply_text("Hello! I'm alive 🚀")
#         # Example of dynamic send:
#         # await self.send(
#         #     update.effective_chat.id,
#         #     text="Welcome message with optional files!",
#         #     photo_path="image.jpg",
#         #     photo_caption="🖼️ Here's your image!",
#         #     document_path="document.pdf",
#         #     document_caption="📄 Here's your file."
#         # )

#     async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
#         await update.message.reply_text(
#             "Here’s how you can use me:\n"
#             "/start - start the bot\n"
#             "/help - show help"
#         )


