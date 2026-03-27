from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def main_menu_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="Оставить жалобу")
    kb.button(text="Мои заявки")
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)

def categories_kb(categories: list[str]):
    b = InlineKeyboardBuilder()
    for c in categories:
        b.button(text=c, callback_data=f"cat:{c}")
    return b.adjust(2).as_markup()

def skip_kb():
    b = InlineKeyboardBuilder()
    b.button(text="Пропустить", callback_data="skip")
    return b.as_markup()

def confirm_kb():
    b = InlineKeyboardBuilder()
    b.button(text="Отправить", callback_data="confirm:send")
    b.button(text="Отмена", callback_data="confirm:cancel")
    return b.as_markup()

def group_card_kb(complaint_id: str, assignee_id: int | None):
    b = InlineKeyboardBuilder()
    if assignee_id is None:
        b.button(text="Берусь", callback_data=f"take:{complaint_id}")
    else:
        # видимые исполнителю кнопки
        b.button(text="Уточнить", callback_data=f"ask:{complaint_id}")
        b.button(text="Отказаться", callback_data=f"drop:{complaint_id}")
        b.button(text="Выполнено", callback_data=f"done:{complaint_id}")
    return b.adjust(3).as_markup()

def location_request_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,  # клавиатура спрячется после отправки
        input_field_placeholder="Нажмите кнопку ниже, чтобы отправить геолокацию"
    )

def location_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Отправить локацию", request_location=True)],
            [KeyboardButton(text="Пропустить")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

def in_work_kb(complaint_id: str):
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="❓ Уточнить", callback_data=f"ask:{complaint_id}"),
        InlineKeyboardButton(text="❌ Отказаться", callback_data=f"drop:{complaint_id}")
    )
    kb.row(
        InlineKeyboardButton(text="✅ Выполнено", callback_data=f"done:{complaint_id}")
    )
    return kb.as_markup()

