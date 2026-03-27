import os
import re
from datetime import datetime

from dotenv import load_dotenv
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest
from storage import save_hint_message, get_hint_message, delete_hint_message
from storage import (
    list_free, list_assignee_jobs,
    save_hint_message, get_hint_message, delete_hint_message,
    get_post_message_id, get_complaint, assign, set_status, get_media
)
from keyboards import group_card_kb, in_work_kb

from utils import notify_user
from keyboards import group_card_kb, in_work_kb
from storage import (
    set_status, assign, get_media, get_complaint,
    save_post_message, get_post_message_id,
    list_inprogress_detailed, list_done_detailed, list_free,
    get_hint_message, delete_hint_message,
)

# На случай, если .env не подхватили в main.py
load_dotenv()

group_router = Router()
ZAYAVKI_CHAT_ID = os.getenv("ZAYAVKI_CHAT_ID")  # строкой

ID_RE = re.compile(r"#([A-Za-z0-9\-]+)")

def _extract_id_from_message(msg) -> str | None:
    if not msg or not getattr(msg, "text", None):
        return None
    m = ID_RE.search(msg.text)
    return m.group(1) if m else None

def _short(text: str | None, n: int = 80) -> str:
    if not text:
        return "—"
    return text if len(text) <= n else text[: n - 1] + "…"

def _fmt_time(iso_str: str | None) -> str:
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%d.%m.%Y %H:%M") + " UTC"
    except Exception:
        return iso_str

async def _who(bot, chat_id, user_id: int) -> str:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        u = member.user
        return f"@{u.username}" if u.username else u.full_name
    except Exception:
        return str(user_id)


# -------- Постинг карточки в группу --------
async def post_to_group(bot, row: dict):
    if not ZAYAVKI_CHAT_ID:
        print("Posting error: ZAYAVKI_CHAT_ID is empty")
        return

    media = get_media(row["id"])
    user_ref = f"@{row.get('username')}" if row.get('username') else str(row.get("user_id"))

    text = (
        f"#{row['id']}  [категория: {row.get('category') or '—'}]\n"
        f"От: {user_ref}\n"
        f"Адрес: {row.get('address_text') or '—'}\n"
        f"Описание: {row.get('text') or '—'}\n\n"
        f"Статус: Новая"
    )

    kb = group_card_kb(row["id"], assignee_id=None)

    try:
        msg = await bot.send_message(chat_id=ZAYAVKI_CHAT_ID, text=text, reply_markup=kb)

        # Сохраняем связь complaint_id -> message_id
        try:
            save_post_message(row["id"], int(str(ZAYAVKI_CHAT_ID).lstrip("+")), msg.message_id)
        except Exception as e:
            print("save_post_message error:", e)

        # (опц.) закрепить карточку
        try:
            await bot.pin_chat_message(ZAYAVKI_CHAT_ID, msg.message_id, disable_notification=True)
        except TelegramBadRequest:
            pass

        # (опц.) медиа в тред
        for file_id, kind in media:
            try:
                if kind == "photo":
                    await bot.send_photo(ZAYAVKI_CHAT_ID, file_id, reply_to_message_id=msg.message_id)
                elif kind == "video":
                    await bot.send_video(ZAYAVKI_CHAT_ID, file_id, reply_to_message_id=msg.message_id)
            except TelegramBadRequest as e:
                print("Media posting error:", e)

        return msg.message_id
    except TelegramBadRequest as e:
        print("Posting error:", e)


# ============ Команды в группе ============

@group_router.message(Command("active"))
async def grp_active(m: Message):
    # 1) общий список "в работе"
    rows = list_inprogress_detailed(20)
    if rows:
        out = []
        for cid, cat, addr, text, assignee_id, taken_at in rows:
            who = await _who(m.bot, m.chat.id, assignee_id) if assignee_id else "—"
            out.append(
                f"#{cid} • {cat or '—'} • {addr or '—'}\n"
                f"Исполнитель: {who}\n"
                f"Взята: {_fmt_time(taken_at)}\n"
                f"Описание: {_short(text)}"
            )
        await m.answer("В работе:\n\n" + "\n\n".join(out))
    else:
        await m.answer("Заявок в работе нет.")

    # 2) подсказка по последней свободной заявке (в тред карточки, если знаем её message_id)
    free = list_free(limit=1)
    if not free:
        return

    fcid, fcat, faddr, ftext, _ = free[0]

    # удалить старый хинт (если был)
    old_hint = get_hint_message(fcid)
    if old_hint:
        try:
            await m.bot.delete_message(m.chat.id, old_hint)
        except Exception:
            pass
        delete_hint_message(fcid)

    reply_to = get_post_message_id(fcid)
    hint_text = (
        "Свободная заявка (можно брать):\n\n"
        f"#{fcid} • {fcat or '—'} • {faddr or '—'}\n"
        f"Описание: {_short(ftext)}"
    )
    try:
        sent = await m.bot.send_message(
            chat_id=m.chat.id,
            text=hint_text,
            reply_markup=group_card_kb(fcid, assignee_id=None),
            reply_to_message_id=reply_to
        )
    except TelegramBadRequest:
        sent = await m.answer(hint_text, reply_markup=group_card_kb(fcid, assignee_id=None))

    # сохранить id хинта, чтобы удалить его, когда кто-то нажмёт «Берусь»
    save_hint_message(fcid, sent.message_id)



@group_router.message(Command("done"))
async def grp_done(m: Message):
    # Если как reply — показать конкретную выполненную заявку в треде
    if m.reply_to_message:
        cid = _extract_id_from_message(m.reply_to_message)
        if cid:
            row = get_complaint(cid)
            if not row:
                await m.reply("Заявка не найдена.")
                return
            assignee_id = row[11]
            done_at     = row[14]
            who = await _who(m.bot, m.chat.id, assignee_id) if assignee_id else "—"
            text = (
                f"#{row[0]} • {row[3] or '—'} • {row[5] or '—'}\n"
                f"Выполнил: {who}\n"
                f"Когда: {_fmt_time(done_at)}\n"
                f"Описание: {_short(row[8])}"
            )
            await m.bot.send_message(
                chat_id=m.chat.id,
                text="Выполнено:\n\n" + text,
                reply_to_message_id=m.reply_to_message.message_id
            )
            return

    # Иначе — общий список выполненных
    rows = list_done_detailed(20)
    if not rows:
        await m.answer("Выполненных пока нет.")
        return

    out = []
    for cid, cat, addr, text, assignee_id, done_at in rows:
        who = await _who(m.bot, m.chat.id, assignee_id) if assignee_id else "—"
        out.append(
            f"#{cid} • {cat or '—'} • {addr or '—'}\n"
            f"Выполнил: {who}\n"
            f"Когда: {_fmt_time(done_at)}\n"
            f"Описание: {_short(text)}"
        )
    await m.answer("Выполнено (последние):\n\n" + "\n\n".join(out))


# ============ Кнопки карточек ============

@group_router.callback_query(F.data.startswith("take:"))
async def take_job(callback: CallbackQuery):
    complaint_id = callback.data.split(":")[1]
    row = get_complaint(complaint_id)
    if not row:
        await callback.answer("Заявка не найдена.", show_alert=True); return
    if row[11]:
        await callback.answer("Эта заявка уже в работе.", show_alert=True); return

    # убрать хинт
    hint_id = get_hint_message(complaint_id)
    if hint_id:
        try:
            await callback.bot.delete_message(ZAYAVKI_CHAT_ID, hint_id)
        except Exception:
            pass
        delete_hint_message(complaint_id)

    # назначить исполнителя (assign также ставит статус InProgress и taken_at)
    assign(complaint_id, callback.from_user.id)

    # уведомить жителя
    try:
        user_id = row[1]
        who = f"@{callback.from_user.username}" if callback.from_user.username else str(callback.from_user.id)
        await notify_user(
            callback.bot,
            user_id,
            f"Ваша заявка #{complaint_id} принята в работу.\nИсполнитель: {who}"
        )
    except Exception:
        pass

    await callback.answer("Вы взяли заявку в работу ✅")
    try:
        await callback.message.edit_reply_markup(reply_markup=in_work_kb(complaint_id))
    except Exception:
        pass




@group_router.callback_query(F.data.startswith("drop:"))
async def drop_job(c: CallbackQuery):
    complaint_id = c.data.split(":", 1)[1]
    row = get_complaint(complaint_id)
    if not row:
        await c.answer("Заявка не найдена", show_alert=True)
        return

    assignee_id = row[11]
    if assignee_id != c.from_user.id:
        await c.answer("Снять может только взявший", show_alert=True)
        return

    assign(complaint_id, None)  # снимаем исполнителя
    set_status(complaint_id, "New")

    try:
        base_text = c.message.text.replace("Статус: В работе", "Статус: Новая")
        if "Исполнитель:" in base_text:
            base_text = "\n".join([ln for ln in base_text.splitlines() if not ln.startswith("Исполнитель:")])

        await c.message.edit_text(base_text, reply_markup=group_card_kb(complaint_id, assignee_id=None))
    except TelegramBadRequest:
        await c.message.edit_reply_markup(reply_markup=group_card_kb(complaint_id, assignee_id=None))

    await c.answer("Вы отказались. Заявка снова свободна.")


@group_router.callback_query(F.data.startswith("ask:"))
async def ask_user(c: CallbackQuery):
    complaint_id = c.data.split(":", 1)[1]
    set_status(complaint_id, "NeedInfo")
    await c.answer("Запросите уточнение у заявителя (в личке).")


@group_router.callback_query(F.data.startswith("done:"))
async def done_job(c: CallbackQuery):
    complaint_id = c.data.split(":", 1)[1]
    row = get_complaint(complaint_id)
    if not row:
        await c.answer("Заявка не найдена", show_alert=True); return

    assignee_id = row[11]
    if assignee_id != c.from_user.id:
        await c.answer("Закрыть может только взявший", show_alert=True); return

    set_status(complaint_id, "Done")

    new_text = (c.message.text
                .replace("Статус: Новая", "Статус: Выполнено")
                .replace("Статус: В работе", "Статус: Выполнено"))
    try:
        await c.message.edit_text(new_text, reply_markup=group_card_kb(complaint_id, assignee_id=c.from_user.id))
    except TelegramBadRequest:
        pass

    await c.answer("Отмечено как выполнено")

    # уведомить жителя
    try:
        user_id = row[1]
        await notify_user(
            c.bot, user_id,
            f"Ваша заявка #{complaint_id} выполнена ✅.\nЕсли есть замечания — ответьте на это сообщение."
        )
    except Exception:
        pass




@group_router.message(Command("finish"))
async def finish_by_reply(m: Message):
    if not m.reply_to_message:
        await m.reply("Ответьте командой /finish на сообщение с карточкой заявки (#ID).")
        return

    cid = _extract_id_from_message(m.reply_to_message)
    if not cid:
        await m.reply("Не удалось определить #ID заявки.")
        return

    row = get_complaint(cid)
    if not row:
        await m.reply("Заявка не найдена.")
        return

    assignee_id = row[11]
    if assignee_id and assignee_id != m.from_user.id:
        await m.reply("Закрыть может только взявший заявку.")
        return

    set_status(cid, "Done")
    await m.reply(f"Заявка #{cid} отмечена как выполненная ✅")

@group_router.message(Command("free"))
async def grp_free(m: Message):
    rows = list_free(limit=10)
    if not rows:
        await m.answer("Свободных заявок нет."); 
        return

    # список (текстом)
    lines = []
    for cid, cat, addr, text, created_at in rows:
        lines.append(f"#{cid} • {cat or '—'} • {addr or '—'}\nОписание: { (text or '—')[:120] }")
    await m.answer("Свободные заявки:\n\n" + "\n\n".join(lines))

    # отдельно подсветим самую новую c кнопкой «Берусь»,
    # и ответим в тред карточки, если знаем её message_id
    fcid, fcat, faddr, ftext, _ = rows[0]

    # удалим старый хинт (если был по этому id)
    old_hint = get_hint_message(fcid)
    if old_hint:
        try:
            await m.bot.delete_message(m.chat.id, old_hint)
        except Exception:
            pass
        delete_hint_message(fcid)

    reply_to = get_post_message_id(fcid)  # message_id карточки заявки
    hint_text = (
        "Свободная заявка (можно брать):\n\n"
        f"#{fcid} • {fcat or '—'} • {faddr or '—'}\n"
        f"Описание: {(ftext or '—')[:120]}"
    )
    try:
        sent = await m.bot.send_message(
            chat_id=m.chat.id,
            text=hint_text,
            reply_markup=group_card_kb(fcid, assignee_id=None),
            reply_to_message_id=reply_to
        )
    except TelegramBadRequest:
        sent = await m.answer(hint_text, reply_markup=group_card_kb(fcid, assignee_id=None))

    # сохраним id хинта — чтобы потом удалить, когда кто-то нажмёт «Берусь»
    save_hint_message(fcid, sent.message_id)

# /my — мои активные заявки с кнопками
@group_router.message(Command("my"))
async def grp_my(m: Message):
    from storage import list_assignee_jobs, get_post_message_id, get_complaint
    from keyboards import in_work_kb

    rows = list_assignee_jobs(m.from_user.id, limit=10, active_only=True)
    if not rows:
        await m.answer("У вас нет активных заявок.")
        return

    await m.answer("Ваши активные заявки:")

    def fmt_contact(user_id: int | None, username: str | None) -> str:
        # Глобально у тебя parse_mode=HTML, так что tg:// ссылка будет кликабельной
        if username:
            return f"@{username}"
        if user_id:
            return f'<a href="tg://user?id={user_id}">написать</a>'
        return "—"

    for cid, cat, addr, text, status, taken_at in rows:
        # достанем полные данные заявки, чтобы узнать автора
        full = get_complaint(cid)  # SELECT * FROM complaints WHERE id=?
        # индексы под твой complaints: (id,user_id,username,category,district,address_text,geo_lat,geo_lon,text,media_group_id,status,assignee_id,created_at,taken_at,done_at,closed_at)
        user_id   = full[1] if full else None
        username  = full[2] if full else None

        short = (text or "—")
        if len(short) > 300:
            short = short[:297] + "…"

        body = (
            f"#{cid} • {cat or '—'} • {addr or '—'}\n"
            f"Статус: {status or '—'}\n"
            f"Взята: {taken_at or '—'}\n"
            f"Заявитель: {fmt_contact(user_id, username)}\n"
            f"Описание: {short}"
        )

        reply_to = get_post_message_id(cid)

        try:
            await m.bot.send_message(
                chat_id=m.chat.id,
                text=body,
                reply_markup=in_work_kb(cid),
                reply_to_message_id=reply_to or None
            )
        except Exception:
            await m.answer(body, reply_markup=in_work_kb(cid))


