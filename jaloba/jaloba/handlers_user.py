from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext

from states import NewComplaint
from keyboards import (
    main_menu_kb, categories_kb, skip_kb, confirm_kb, location_kb
)
from utils import gen_id
from storage import save_complaint, add_media, list_user_complaints
from handlers_group import post_to_group

user_router = Router()

CATEGORIES = [
    "Вода", "Свет", "Газ", "Канализация", "Мусор",
    "Дороги", "Лифт", "Благоустройство", "Шум", "Животные", "Другое",
]


# ===== Команды =====

@user_router.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Здравствуйте! Я бот обращений. Что хотите сделать?", reply_markup=main_menu_kb())

@user_router.message(Command("stop"))
async def cmd_stop(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("⛔ Бот остановлен. Чтобы возобновить работу, введите /start", reply_markup=main_menu_kb())

@user_router.message(Command("mine"))
async def cmd_mine(m: Message):
    await my_complaints(m)


# ===== Новый инцидент =====

@user_router.message(F.text == "Оставить жалобу")
async def new_complaint(m: Message, state: FSMContext):
    await state.set_state(NewComplaint.category)
    await m.answer("Выберите категорию:", reply_markup=categories_kb(CATEGORIES))

@user_router.callback_query(F.data.startswith("cat:"), NewComplaint.category)
async def set_category(c: CallbackQuery, state: FSMContext):
    cat = c.data.split(":", 1)[1]
    await state.update_data(category=cat)

    await state.set_state(NewComplaint.text)
    await c.message.edit_reply_markup()  # убираем клавиатуру категорий
    await c.message.answer("Опишите проблему (текст):")
    await c.answer()

@user_router.message(NewComplaint.text)
async def after_text_ask_address(m: Message, state: FSMContext):
    await state.update_data(text=m.text.strip())
    await state.set_state(NewComplaint.address)
    await m.answer("Адрес (улица/дом/ориентир). Или нажмите «Пропустить».", reply_markup=skip_kb())

@user_router.callback_query(F.data == "skip", NewComplaint.address)
async def skip_address(c: CallbackQuery, state: FSMContext):
    await state.update_data(address_text=None)
    await state.set_state(NewComplaint.location)
    await c.message.answer("Отправьте геолокацию или нажмите «Пропустить».", reply_markup=location_kb())
    await c.answer()

@user_router.message(NewComplaint.address)
async def set_address(m: Message, state: FSMContext):
    await state.update_data(address_text=m.text.strip())
    await state.set_state(NewComplaint.location)
    await m.answer("Отправьте геолокацию или нажмите «Пропустить».", reply_markup=location_kb())

# --- Геолокация

@user_router.message(NewComplaint.location, F.location)
async def set_location(m: Message, state: FSMContext):
    await state.update_data(geo=(m.location.latitude, m.location.longitude))
    await state.set_state(NewComplaint.media)
    await m.answer("Прикрепите фото/видео (по желанию) или нажмите «Пропустить».", reply_markup=skip_kb())

@user_router.message(NewComplaint.location, F.text.casefold() == "пропустить")
async def skip_location(m: Message, state: FSMContext):
    await state.update_data(geo=None)
    await state.set_state(NewComplaint.media)
    await m.answer("Прикрепите фото/видео (по желанию) или нажмите «Пропустить».", reply_markup=skip_kb())

@user_router.message(NewComplaint.location)
async def only_location_required(m: Message):
    await m.answer("Нужно отправить геолокацию. Либо нажмите «Пропустить».", reply_markup=location_kb())

# --- Медиа

@user_router.message(NewComplaint.media, F.photo | F.video)
async def collect_media(m: Message, state: FSMContext):
    data = await state.get_data()
    cid = data.get("cid") or gen_id()
    await state.update_data(cid=cid)

    if m.photo:
        add_media(cid, m.photo[-1].file_id, "photo")
    elif m.video:
        add_media(cid, m.video.file_id, "video")

    await state.set_state(NewComplaint.confirm)
    await m.answer("Проверить и отправить?", reply_markup=confirm_kb())

@user_router.message(NewComplaint.media, F.text.casefold() == "пропустить")
async def skip_media_text(m: Message, state: FSMContext):
    await state.set_state(NewComplaint.confirm)
    await m.answer("Проверить и отправить?", reply_markup=confirm_kb())

@user_router.callback_query(F.data == "skip", NewComplaint.media)
async def skip_media_cb(c: CallbackQuery, state: FSMContext):
    await state.set_state(NewComplaint.confirm)
    await c.message.answer("Проверить и отправить?", reply_markup=confirm_kb())
    await c.answer()

@user_router.message(NewComplaint.media)
async def media_unrecognized(m: Message):
    await m.answer("Пришлите фото/видео или нажмите «Пропустить».", reply_markup=skip_kb())

# --- Подтверждение

@user_router.callback_query(F.data.startswith("confirm:"), NewComplaint.confirm)
async def confirm_send(c: CallbackQuery, state: FSMContext):
    action = c.data.split(":", 1)[1]
    if action != "send":
        await state.clear()
        await c.message.answer("Отменено.", reply_markup=main_menu_kb())
        await c.answer()
        return

    data = await state.get_data()
    cid = data.get("cid", gen_id())

    row = {
        "id": cid,
        "user_id": c.from_user.id,
        "username": c.from_user.username,
        "category": data.get("category"),
        "district": None,
        "address_text": data.get("address_text"),
        "geo_lat": (data.get("geo")[0] if data.get("geo") else None),
        "geo_lon": (data.get("geo")[1] if data.get("geo") else None),
        "text": data.get("text"),
        "media_group_id": None,
        "status": "New",
        "assignee_id": None,
    }

    save_complaint(row)

    await c.message.answer(
        f"Ваша жалоба зарегистрирована: #{cid}\n"
        f"Статус: Новая. Я сообщу, когда её возьмут в работу.",
        reply_markup=main_menu_kb()
    )
    await state.clear()

    await post_to_group(c.bot, row)
    await c.answer()


# ===== «Мои заявки»

@user_router.message(F.text == "Мои заявки")
async def my_complaints(m: Message):
    rows = list_user_complaints(m.from_user.id, limit=10)
    if not rows:
        await m.answer("У вас пока нет заявок.")
        return

    lines = []
    for cid, cat, addr, text, status, created_at, done_at in rows:
        short = (text or "—")
        if len(short) > 60:
            short = short[:57] + "…"
        lines.append(
            f"#{cid} • {status}\nКатегория: {cat or '—'}\nАдрес: {addr or '—'}\nОписание: {short}\n"
        )
    await m.answer("Ваши последние заявки:\n\n" + "\n".join(lines))
