from datetime import datetime
from aiogram import Bot

async def notify_user(bot: Bot, user_id: int, text: str):
    """Отправка личного уведомления пользователю. Тихо игнорим ошибки,
    если пользователь не писал боту или запретил ЛС."""
    try:
        await bot.send_message(user_id, text)
    except Exception:
        pass



def gen_id():
    # Пример: Z-2025-0915-0012
    return "Z-" + datetime.utcnow().strftime("%Y%m%d-%H%M%S")
