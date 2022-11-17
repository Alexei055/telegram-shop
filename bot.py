import json
import time
import traceback
from collections import defaultdict
from telethon.sync import TelegramClient, events, types, functions, Button
from telethon.tl.types import InputPhoneContact, Invoice, InputMediaInvoice, LabeledPrice, MessageMediaContact
from telethon.tl.functions.contacts import ImportContactsRequest
import random
import asyncio
import tracemalloc
import psycopg2
from telethon.tl.types import KeyboardButtonRow
from mysql.connector import (connection)
import re
import datetime
import hashlib

mydb = connection.MySQLConnection(
    host="localhost",
    user="root",
    passwd="admin",
    database="telegram_shop"
)
SQL = mydb.cursor(buffered=True)

api_id = 48
api_hash = '3'
admin_ids = [888888, 8888889]
admin_chat_id = 5
shopinfo = "EyeHome"
mainkb = [[Button.inline("Личный кабинет", b"Profile"), Button.inline("Корзина", b"Cart")],
          [Button.inline("Заказать линзы", b"Order"), Button.inline("Повторить заказ", b"OrderRepeat")],
          [Button.inline("Информация", b"Info"), Button.inline("Служба поддержки", b"Support")]]
admin_mainkb = [[Button.inline("Личный кабинет", b"Profile"), Button.inline("Корзина", b"Cart")],
                [Button.inline("Заказать линзы", b"Order"), Button.inline("Повторить заказ", b"OrderRepeat")],
                [Button.inline("Информация", b"Info"), Button.inline("Служба поддержки", b"Support")],
                [Button.inline("Админ-панель", b"AdminPanel")]]
loginkb = [[Button.inline("Войти", b"Login"), Button.inline("Зарегистрироваться", b"Register")],
           [Button.inline("Информация", b"Info"), Button.inline("Поддержка", b"Support")]]
users = defaultdict(dict)

provider_token = '401640'
bot = TelegramClient(f'bot_session', api_id, api_hash, proxy=None).start()


@bot.on(events.NewMessage())
async def test2(event):
    try:
        if hasattr(event, 'contact'):
            if 'reg' not in users[event.chat_id]:
                return
            delta = datetime.timedelta(hours=3, minutes=0)
            telephone = event.contact.phone_number
            telephone = re.sub(r'\D', '', telephone)
            telephone = f'8 ({telephone[1:4]}) {telephone[4:7]}-{telephone[7:9]}-{telephone[9:11]}'
            SQL.execute(f"SELECT * FROM fd_customer WHERE telephone = '{telephone}'")
            db_tel = SQL.fetchone()
            if db_tel:
                await bot.send_message(event.chat_id, 'Пользователь с таким номером телефона уже существует.',
                                       buttons=[Button.inline("Отменить регистрацию", b"Register_or_login_cancel")])
                return
            a = users[event.chat_id]['reg']
            SQL.execute(f"INSERT INTO fd_customer"
                        f"(customer_group_id, firstname, lastname, email, telephone, password, date_added, telegram_id, fax, salt, custom_field, ip, status, approved, safe, token) "
                        f"VALUES(1, '{a['first_name']}', '{a['last_name']}', '{a['email']}', '{telephone}', '{a['password']}', '{datetime.datetime.utcnow() + delta}', {event.chat_id}, 'fax', 'salt', 'custom_field', 'ip', 1, 1, 0, 'token')")
            mydb.commit()
            await bot.send_message(event.chat_id, f"Регистрация прошла успешно!", buttons=Button.clear())
            await bot.send_message(event.chat_id, f"Добро пожаловать, {a['first_name']}! Выберите действие.",
                                   buttons=mainkb)
    except Exception as e:
        print(e)


@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    try:
        SQL.execute(f"SELECT * FROM fd_customer WHERE telegram_id = {event.chat_id}")
        memdata = SQL.fetchone()
        if memdata:
            if memdata[0] in admin_ids:
                but = admin_mainkb
            else:
                but = mainkb
            await bot.send_message(event.chat_id, f"Добро пожаловать, {memdata[3]}! Выберите действие.", buttons=but)
        else:
            but = loginkb
            await bot.send_message(event.chat_id, f"Вы не вошли. Зарегистрироваться можно здесь или у нас на сайте.",
                                   buttons=but)
    except Exception:
        traceback.print_exc()


loop = asyncio.get_event_loop()
tracemalloc.start()


@bot.on(events.NewMessage(pattern='/reply'))
async def reply(event):
    try:
        mes = event.message.split(' ', maxsplit=1)
        chat_id = int(mes[0])
        await bot.send_message(chat_id, f"Пришёл ответ от службы поддержки:\n{mes[1]}")
    except Exception as e:
        print(e)


# That event is handled when customer enters his card/etc, on final pre-checkout
# If we don't `SetBotPrecheckoutResultsRequest`, money won't be charged from buyer, and nothing will happen next.
@bot.on(events.Raw(types.UpdateBotPrecheckoutQuery))
async def payment_pre_checkout_handler(event: types.UpdateBotPrecheckoutQuery):
    if event.payload.decode('UTF-8').isdigit():
        # so we have to confirm payment
        await bot(
            functions.messages.SetBotPrecheckoutResultsRequest(
                query_id=event.query_id,
                success=True,
                error=None
            )
        )
        print(f'Order {event.payload.decode("UTF-8")} card enter')
    else:
        # for example, something went wrong (whatever reason). We can tell customer about that:
        await bot(
            functions.messages.SetBotPrecheckoutResultsRequest(
                query_id=event.query_id,
                success=False,
                error='Something went wrong'
            )
        )
    raise events.StopPropagation


# That event is handled at the end, when customer payed.
@bot.on(events.Raw(types.UpdateNewMessage))
async def payment_received_handler(event):
    if isinstance(event.message.action, types.MessageActionPaymentSentMe):
        payment: types.MessageActionPaymentSentMe = event.message.action
        # do something after payment was received
        if payment.payload.decode('UTF-8').isdigit():
            SQL.execute(
                f'UPDATE fd_order_history SET order_status_id = 1 WHERE order_id = {int(payment.payload.decode("UTF-8"))}')
            mydb.commit()
            await bot.send_message(event.message.from_id,
                                   f'Спасибо за покупку! Номер заказа: {payment.payload.decode("UTF-8")}. Статус заказа можно посмотреть в профиле. Дождитесь звонка оператора.',
                                   buttons=[Button.inline('В профиль', b'Profile')])
            print(f'Order {event.payload.decode("UTF-8")} confirm')
        raise events.StopPropagation


# let's put it in one function for more easier way
def generate_invoice(price_label: str, price_amount: int, currency: str, title: str,
                     description: str, payload: str, start_param: str = '') -> types.InputMediaInvoice:
    price = LabeledPrice(label=price_label, amount=price_amount)  # label - just a text, amount=10000 means 100.00
    invoice = Invoice(
        currency=currency,  # currency like USD
        prices=[price],  # there could be a couple of prices.
        test=False,  # if you're working with test token, else set test=False.
        # More info at https://core.telegram.org/bots/payments

        # params for requesting specific fields
        name_requested=False,
        phone_requested=False,
        email_requested=False,
        shipping_address_requested=False,

        # if price changes depending on shipping
        flexible=False,

        # send data to provider
        phone_to_provider=False,
        email_to_provider=False
    )
    return InputMediaInvoice(
        title=title,
        description=description,
        invoice=invoice,
        payload=payload.encode('UTF-8'),  # payload, which will be sent to next 2 handlers
        provider=provider_token,

        provider_data=types.DataJSON('{}'),
        # data about the invoice, which will be shared with the payment provider. A detailed description of
        # required fields should be provided by the payment provider.

        start_param=start_param,
        # Unique deep-linking parameter. May also be used in UpdateBotPrecheckoutQuery
        # see: https://core.telegram.org/bots#deep-linking
        # it may be the empty string if not needed

    )


@bot.on(events.CallbackQuery)
async def handler(event):
    try:
        SQL.execute(f"SELECT * FROM fd_customer WHERE telegram_id = {event.chat_id}")
        memdata = SQL.fetchone()
        if event.data == b"Register":
            name = ''
            email = ''
            password = ''
            async with bot.conversation(event.chat_id, total_timeout=6000, exclusive=False) as conv:
                try:
                    while name == '':
                        await conv.send_message(f"Введите своё имя и фамилию через пробел:", buttons=[
                            Button.inline("Отменить регистрацию", b"Register_or_login_cancel")])
                        name = await conv.get_response()
                        name = name.message
                        if re.findall(r'[^\w\s]|\d', name):
                            await bot.send_message(event.chat_id, 'Имя и фамилия должны состоять только из букв.')
                            name = ''
                        elif len(name) < 2 or len(name) > 32:
                            await bot.send_message(event.chat_id, 'Длина имени должна составлять от 2 до 32 символов.')
                            name = ''
                    while email == '':
                        await conv.send_message(f"Введите адрес электронной почты:", buttons=[
                            Button.inline("Отменить регистрацию", b"Register_or_login_cancel")])
                        email = await conv.get_response()
                        email = email.message
                        SQL.execute(f"SELECT * FROM fd_customer WHERE email = '{email}'")
                        db_email = SQL.fetchone()
                        if db_email:
                            await bot.send_message(event.chat_id, 'Пользователь с таким e-mail уже существует.')
                            email = ''
                        elif not re.findall(r'.+@.+\..+', email):
                            await bot.send_message(event.chat_id, 'Неверный формат электронного адреса.')
                            email = ''
                    while password == '':
                        await conv.send_message(f"Введите пароль:", buttons=[
                            Button.inline("Отменить регистрацию", b"Register_or_login_cancel")])
                        password = await conv.get_response()
                        password = password.message
                        if re.findall(r'[^\w_]', password):
                            await bot.send_message(event.chat_id,
                                                   'Пароль может содержать только заглавные и строчные буквы, цифры и знак подчёркивания.')
                            password = ''
                        elif len(password) < 5 or len(password) > 32:
                            await bot.send_message(event.chat_id, 'Длина пароля должна составлять от 5 до 32 символов.')
                            password = ''
                        password = hashlib.md5(bytes(password, 'utf-8')).hexdigest()
                    conv.cancel()
                except asyncio.TimeoutError:
                    await bot.send_message(event.chat_id, 'Время ожидания истекло. Повторите операцию', buttons=loginkb)
                    conv.cancel()
                    return
            first_name = name.split(' ')[0]
            first_name = first_name[0].upper() + first_name[1:]
            last_name = ''
            if ' ' in name:
                last_name = name.split(' ')[1]
            users[event.chat_id]['reg'] = {'first_name': first_name, 'last_name': last_name, 'email': email,
                                           'password': password}
            but = [[Button.inline("Я введу телефон с клавиатуры", b"Telephone_custom")],
                   [Button.inline("Отменить регистрацию", b"Register_or_login_cancel")]]
            await bot.send_message(event.chat_id, 'Также мы просим вас оставить свой телефон.', buttons=but)
            await bot.send_message(event.chat_id,
                                   'Если вы хотите использовать номер из Telegram, сперва оставьте контакт нашему боту по кнопке ниже.',
                                   buttons=[Button.request_phone("Передать контакт", resize=True, single_use=True)])
        elif event.data == b"Telephone_custom":
            delta = datetime.timedelta(hours=3, minutes=0)
            telephone = ''
            async with bot.conversation(event.chat_id, total_timeout=6000, exclusive=False) as conv:
                try:
                    while telephone == '':
                        mes = await conv.send_message(f"Введите номер телефона (с цифрой 8):", buttons=[
                            Button.inline("Отменить регистрацию", b"Register_or_login_cancel")])
                        telephone = await conv.get_response()
                        telephone = re.sub(r'\D', '', telephone.message)
                        if len(telephone) != 11:
                            await bot.send_message(event.chat_id, 'Номер телефона должен состоять из 11 цифр.')
                            telephone = ''
                        else:
                            telephone = f'8 ({telephone[1:4]}) {telephone[4:7]}-{telephone[7:9]}-{telephone[9:11]}'
                            SQL.execute(f"SELECT * FROM fd_customer WHERE telephone = '{telephone}'")
                            db_tel = SQL.fetchone()
                            if db_tel:
                                await bot.send_message(event.chat_id,
                                                       'Пользователь с таким номером телефона уже существует.')
                                telephone = ''
                    conv.cancel()
                except asyncio.TimeoutError:
                    await bot.send_message(event.chat_id, 'Время ожидания истекло. Повторите операцию.',
                                           buttons=loginkb)
                    conv.cancel()
                    return
            a = users[event.chat_id]['reg']
            SQL.execute(f"INSERT INTO fd_customer"
                        f"(customer_group_id, firstname, lastname, email, telephone, password, date_added, telegram_id, fax, salt, custom_field, ip, status, approved, safe, token) "
                        f"VALUES(1, '{a['first_name']}', '{a['last_name']}', '{a['email']}', '{telephone}', '{a['password']}', '{datetime.datetime.utcnow() + delta}', {event.chat_id}, 'fax', 'salt', 'custom_field', 'ip', 1, 1, 0, 'token')")
            mydb.commit()
            await bot.send_message(event.chat_id, f"Регистрация прошла успешно!", buttons=Button.clear())
            await bot.send_message(event.chat_id, f"Добро пожаловать, {a['first_name']}! Выберите действие.",
                                   buttons=mainkb)

        elif event.data == b"Login":
            user = ''
            password = ''
            async with bot.conversation(event.chat_id, total_timeout=6000, exclusive=False) as conv:
                try:
                    while user == '':
                        await conv.send_message(f"Введите адрес электронной почты или телефон:",
                                                buttons=[Button.inline("Назад", b"Register_or_login_cancel")])
                        data = await conv.get_response()
                        data = data.message
                        if '@' in data:
                            SQL.execute(f"SELECT * FROM fd_customer WHERE email = '{data}'")
                            db_email = SQL.fetchone()
                            if db_email:
                                user = db_email
                            elif not re.findall(r'.+@.+\..+', data):
                                await bot.send_message(event.chat_id,
                                                       'Номер телефона должен включать цифру 8, а почта — содержать формат eyehome@ya.ru.')
                                user = ''
                            else:
                                await bot.send_message(event.chat_id, 'Пользователя с таким e-mail нет.')
                                user = ''
                        else:
                            telephone = re.sub(r'\D', '', data)
                            if len(telephone) != 11:
                                await bot.send_message(event.chat_id,
                                                       'Номер телефона должен включать цифру 8, а почта — содержать формат eyehome@ya.ru.')
                                user = ''
                            else:
                                telephone = f'8 ({telephone[1:4]}) {telephone[4:7]}-{telephone[7:9]}-{telephone[9:11]}'
                                SQL.execute(f"SELECT * FROM fd_customer WHERE telephone = '{telephone}'")
                                db_phone = SQL.fetchone()
                                if db_phone:
                                    user = db_phone
                                else:
                                    await bot.send_message(event.chat_id, 'Пользователя с таким номером телефона нет.')
                                    user = ''
                    while password == '':
                        await conv.send_message(f"Введите пароль:",
                                                buttons=[Button.inline("Назад", b"Register_or_login_cancel")])
                        password = await conv.get_response()
                        password = password.message
                        if re.findall(r'[^\w_]', password):
                            await bot.send_message(event.chat_id,
                                                   'Пароль может содержать только заглавные и строчные буквы, цифры и знак подчёркивания.')
                            password = ''
                        elif len(password) < 5 or len(password) > 32:
                            await bot.send_message(event.chat_id, 'Длина пароля должна составлять от 5 до 32 символов.')
                            password = ''
                        else:
                            password = hashlib.md5(bytes(password, 'utf-8')).hexdigest()
                            if user[8] == password:
                                password = True
                            else:
                                await bot.send_message(event.chat_id, 'Пароль неверный.')
                                password = ''
                    conv.cancel()
                except asyncio.TimeoutError:
                    await bot.send_message(event.chat_id, 'Время ожидания истекло. Повторите операцию.',
                                           buttons=loginkb)
                    conv.cancel()
                    return
            if not user[21]:
                SQL.execute(f'UPDATE fd_customer SET telegram_id = ? WHERE customer_id = {user[0]}', (event.chat_id,))
            if user[0] in admin_ids:
                but = admin_mainkb
            else:
                but = mainkb
            await bot.send_message(event.chat_id, f"Добро пожаловать, {user[3]}! Выберите действие.", buttons=but)

        elif event.data == b"Register_or_login_cancel":
            async with bot.conversation(event.chat_id, exclusive=False) as conv:
                await conv.cancel_all()
            await bot.send_message(event.chat_id, f"Отменяю...", buttons=Button.clear())
            await bot.send_message(event.chat_id, f"Выберите опцию:", buttons=loginkb)

        elif event.data == b"Info":
            await bot.send_message(event.chat_id, shopinfo, buttons=[Button.inline("Назад", b"ToMain")])

        elif event.data == b"Support":
            async with bot.conversation(event.chat_id, total_timeout=6000, exclusive=False) as conv:
                try:
                    await conv.send_message(f"Напишите сообщение. Оно будет отправлено в поддержку.",
                                            buttons=[Button.inline("Назад", b"ToMain")])
                    mes = await conv.get_response()
                    mes = mes.message
                    conv.cancel()
                except asyncio.TimeoutError:
                    await bot.send_message(event.chat_id, 'Время ожидания истекло. Повторите операцию.',
                                           buttons=[Button.inline("Назад", b"ToMain")])
                    conv.cancel()
                    return
            if mes:
                name = ''
                if memdata:
                    name = f' ({memdata[3]})'
                await bot.send_message(admin_chat_id,
                                       f"Сообщение от пользователя {event.chat_id}{name}:\n{mes}\nОтветить: /reply {event.chat_id} <текст>")

        elif event.data == b'ToMain':
            async with bot.conversation(event.chat_id, exclusive=False) as conv:
                await conv.cancel_all()
            if memdata:
                if memdata[0] in admin_ids:
                    but = admin_mainkb
                else:
                    but = mainkb
                await bot.send_message(event.chat_id, f"Добро пожаловать, {memdata[3]}! Выберите действие.",
                                       buttons=but)
            else:
                await bot.send_message(event.chat_id,
                                       f"Вы не вошли. Зарегистрироваться можно здесь или у нас на сайте.",
                                       buttons=loginkb)

        elif not memdata:
            await bot.send_message(event.chat_id, f"Вы не вошли. Зарегистрироваться можно здесь или у нас на сайте.",
                                   buttons=loginkb)
            return

        if event.data == b"Profile":
            async with bot.conversation(event.chat_id, exclusive=False) as conv:
                await conv.cancel_all()
            profile = f'Профиль пользователя {memdata[3]}\n'
            if memdata[5]:
                profile += f'E-mail: {memdata[5]}\n'
            profile += f'ФИО: {memdata[3]}'
            if memdata[4]:
                profile += f' {memdata[4]}'  # фамилия
            profile += '\n'
            if memdata[6]:
                profile += f'Телефон: {memdata[6]}\n'
            SQL.execute(f"SELECT * FROM fd_address WHERE customer_id = {memdata[0]}")
            addresses = SQL.fetchall()
            if addresses:
                profile += f'\nАдреса:\n'
                for i, a in enumerate(addresses):
                    profile += f'{i + 1}. {a[5]}\n'
            else:
                profile += f'\nУ вас нет адресов доставки.\n'
            but = [[Button.inline("История заказов", b"History"), Button.inline("Заказать линзы", b"Order")],
                   [Button.inline("Добавить адрес", b"GetAddress"), Button.inline('Вернуться в меню', b'ToMain')]]
            await bot.send_message(event.chat_id, profile, buttons=but)

        if event.data.startswith(b"Cart") and not event.data.startswith(b"CartAdd"):
            if not 'cart' in users[event.chat_id]:
                await bot.send_message(event.chat_id, 'Корзина пуста', buttons=[Button.inline("Назад", b"ToMain")])
            elif not users[event.chat_id]['cart']:
                await bot.send_message(event.chat_id, 'Корзина пуста', buttons=[Button.inline("Назад", b"ToMain")])
            else:
                if b'|' in event.data:
                    code = event.data.split(b'|')[1].decode('utf-8')
                    if code.isdigit():
                        but = [[Button.inline("Удалить товар", b"Cart" + bytes('|d' + code, 'utf-8')),
                                Button.inline("Удалить единицу", b"Cart" + bytes('|q' + code, 'utf-8'))],
                               [Button.inline("Назад", b"Cart")]]
                        c = users[event.chat_id]["cart"][int(code)]
                        SQL.execute(f"SELECT price FROM fd_product WHERE product_id = {c['id']}")
                        price = SQL.fetchone()[0]
                        res = f'{c["name"]}'
                        if c['power']:
                            res += f' {c["power"]} дптр.'
                        if not '(' in c['name']:
                            res += f' {c["model"]}'
                        res += f'\n   {c["quantity"]} ед.  {round(price, 2)} руб.'
                        if c['quantity'] > 1:
                            res += f"   — всего {round(price * c['quantity'], 2)} руб."
                        res += '\n'
                        await bot.send_message(event.chat_id, res, buttons=but)
                        return
                    if code.startswith('q'):
                        code = int(code.split('q')[1])
                        if users[event.chat_id]["cart"][code]["quantity"] == 1:
                            resplus = f'\nТовар {users[event.chat_id]["cart"][code]["name"]} удалён.'
                            del users[event.chat_id]["cart"][code]
                        else:
                            users[event.chat_id]["cart"][code]["quantity"] -= 1
                            resplus = f'\nЕдиница {users[event.chat_id]["cart"][code]["name"]} удалена.'
                    else:
                        code = int(code.split('d')[1])
                        resplus = f'\nТовар {users[event.chat_id]["cart"][code]["name"]} удалён.'
                        del users[event.chat_id]["cart"][code]
                else:
                    resplus = '\nЧтобы удалить товар или единицу, нажмите конпку с его номером ниже:'
                but = [[]]
                but_idx = 0
                idx = 0
                if users[event.chat_id]["cart"]:
                    res = 'Ваша корзина:\n'
                else:
                    res = 'Корзина пуста\n'
                for i, c in enumerate(users[event.chat_id]["cart"]):
                    SQL.execute(f"SELECT price FROM fd_product WHERE product_id = {c['id']}")
                    price = SQL.fetchone()[0]
                    res += f'{i + 1}. {c["name"]}'
                    if c['power']:
                        res += f' {c["power"]} дптр.'
                    if not '(' in c['name']:
                        res += f' {c["model"]}'
                    res += f'\n   {c["quantity"]} ед.  {round(price, 2)} руб.'
                    if c['quantity'] > 1:
                        res += f"   — всего {round(price * c['quantity'], 2)} руб."
                    res += '\n'
                    if idx == 3:
                        but.append([])
                        but_idx += 1
                        idx = -1
                    idx += 1
                    but[but_idx].append(Button.inline(f"{i + 1}", b"Cart|" + bytes(str(i), 'utf-8')))
                res += resplus
                but.append([Button.inline("Назад", b"ToMain")])
                await bot.send_message(event.chat_id, res, buttons=but)

        if event.data == b'Order':
            but = [[]]
            but_idx = 0
            SQL.execute(f"SELECT category_id, name, meta_title FROM fd_category_description WHERE language_id = 1")
            cats = SQL.fetchall()
            idx = 0
            for i, c in enumerate(cats):
                name = c[2] if c[2] else c[1]
                if idx == 2 or len(name) > 24:
                    but.append([])
                    but_idx += 1
                    idx = 0
                idx += 1
                but[but_idx].append(Button.inline(name, b'OrderCategories' + bytes(str(c[0]), 'utf-8')))
                if len(name) > 24:
                    but.append([])
                    but_idx += 1
                    idx = 0
            but.append([Button.inline("В меню", b"ToMain"), Button.inline("Личный кабинет", b"Profile")])
            await bot.send_message(event.chat_id, 'Выберите категорию:', buttons=but)
        if event.data.startswith(b'OrderCategories'):
            but = [[]]
            but_idx = 0
            cat = int(event.data.split(b'OrderCategories')[1].decode("utf-8"))
            SQL.execute(f"SELECT name FROM fd_category_description WHERE language_id = 1 AND category_id = {cat}")
            cat_name = SQL.fetchone()[0]
            users[event.chat_id]['current'] = {'category': {'b': event.data, 'c': cat}}
            SQL.execute(
                f"SELECT manufacturer_id, name FROM fd_manufacturer WHERE manufacturer_id in (SELECT manufacturer_id FROM fd_product WHERE product_id in "
                f"(SELECT product_id FROM fd_product_to_category WHERE category_id = {cat}))")
            prods = SQL.fetchall()
            if not prods:
                await bot.send_message(event.chat_id, f'Вы выбрали: {cat_name}.\nКатегория сейчас пуста.',
                                       buttons=[Button.inline("Назад", b"Order"), Button.inline("В меню", b"ToMain"),
                                                Button.inline("Личный кабинет", b"Profile")])
                return
            idx = 0
            for i, c in enumerate(prods):
                name = c[1].replace('&amp;', '&')
                if idx == 3 or len(name) > 18:
                    but.append([])
                    but_idx += 1
                    idx = 0
                idx += 1
                but[but_idx].append(Button.inline(name, b'OrderProducers' + bytes(str(c[0]), 'utf-8')))
                if len(name) > 18:
                    but.append([])
                    but_idx += 1
                    idx = 0
            but.append([Button.inline("Назад", b"Order"), Button.inline("В меню", b"ToMain"),
                        Button.inline("Личный кабинет", b"Profile")])
            await bot.send_message(event.chat_id, f'Вы выбрали: {cat_name}.\nВыберите производителя:', buttons=but)
        if event.data.startswith(b'OrderProducers'):
            but = [[]]
            but_idx = 0
            cat = int(event.data.split(b'OrderProducers')[1].decode("utf-8"))
            SQL.execute(f"SELECT name, image FROM fd_manufacturer WHERE manufacturer_id = {cat}")
            cat_name, image = SQL.fetchone()
            users[event.chat_id]['current']['producer'] = {'b': event.data, 'c': cat}
            coms_list = []
            comnames = []
            SQL.execute(f"SELECT product_id, name FROM fd_product_description WHERE language_id = 1 AND product_id in "
                        f"(SELECT product_id FROM fd_product WHERE manufacturer_id = {cat}) AND product_id in "
                        f"(SELECT product_id FROM fd_product_to_category WHERE category_id = {users[event.chat_id]['current']['category']['c']})")
            coms = SQL.fetchall()
            print(coms)
            for com in coms:
                comname = com[1].split('(')[0].rstrip()
                if not comname in comnames:
                    coms_list.append([com[0], comname])
                    comnames.append(comname)
            idx = 0
            for i, c in enumerate(coms_list):
                if idx == 2 or len(c[1]) > 24:
                    but.append([])
                    but_idx += 1
                    idx = 0
                idx += 1
                but[but_idx].append(Button.inline(c[1], b'OrderComm' + bytes(str(c[0]), 'utf-8')))
                if len(c[1]) > 24:
                    but.append([])
                    but_idx += 1
                    idx = 0
            but.append([Button.inline("Назад", users[event.chat_id]['current']['category']['b']),
                        Button.inline("В меню", b"ToMain"), Button.inline("Личный кабинет", b"Profile")])
            await bot.send_message(event.chat_id, f"Вы выбрали: {cat_name.replace('&amp;', '&')}.", buttons=but)
            if image:
                await bot.send_file(event.chat_id, image)
        if event.data.startswith(b'OrderComm'):
            but = [[]]
            but_idx = 0
            cat = int(event.data.split(b'OrderComm')[1].decode("utf-8"))
            users[event.chat_id]['current']['commodity'] = {'b': event.data, 'c': cat}
            SQL.execute(f"SELECT name FROM fd_product_description WHERE language_id = 1 AND product_id = {cat}")
            cur_com = SQL.fetchone()
            if '(' in cur_com[0]:
                cat_name = cur_com[0].split('(')[0]
                SQL.execute(f"SELECT product_id, model, price, image FROM fd_product WHERE product_id in "
                            f"(SELECT product_id FROM fd_product_description WHERE language_id = 1 AND name LIKE '%{cat_name}(%')"
                            f"AND manufacturer_id = {users[event.chat_id]['current']['producer']['c']}")
                coms = SQL.fetchall()
            else:
                cat_name = cur_com[0]
                SQL.execute(f"SELECT product_id, model, price, image FROM fd_product WHERE product_id = {cat}")
                coms = SQL.fetchall()
            idx = 0
            for i, c in enumerate(coms):
                price = round(c[2], 2)
                text = f'{c[1]} — {price} р.'
                if idx == 3 or len(text) > 18:
                    but.append([])
                    but_idx += 1
                    idx = 0
                idx += 1
                but[but_idx].append(Button.inline(text, b'OrderCount' + bytes(str(c[0]), 'utf-8')))
                if len(text) > 18:
                    but.append([])
                    but_idx += 1
                    idx = 0
            but.append([Button.inline("Назад", users[event.chat_id]['current']['producer']['b']),
                        Button.inline("В меню", b"ToMain"), Button.inline("Личный кабинет", b"Profile")])
            await bot.send_message(event.chat_id, f'Вы выбрали: {cat_name.rstrip()}.\nВыберите количество/объём:',
                                   buttons=but)
            if coms[0][3]:
                await bot.send_file(event.chat_id, coms[0][3])
        if event.data.startswith(b'OrderCount'):
            cat = int(event.data.split(b'OrderCount')[1].decode("utf-8"))
            SQL.execute(f"SELECT name FROM fd_product_description WHERE language_id = 1 AND product_id = {cat}")
            cat_name = SQL.fetchone()[0]
            SQL.execute(f"SELECT name FROM fd_option_value_description WHERE language_id = 1 AND option_value_id in "
                        f"(SELECT option_value_id FROM fd_product_option_value WHERE product_id = {cat} AND (option_id = 13 OR option_id = 18))")
            options = SQL.fetchall()
            if not options:
                but = [[Button.inline("В корзину", b'CartAdd' + bytes(str(cat), 'utf-8')),
                        Button.inline("Оформить заказ", b"OrderCreate" + bytes(str(cat), 'utf-8'))]]
                users[event.chat_id]['current']['power'] = {'b': event.data, 'c': cat}
                SQL.execute(f"SELECT price, manufacturer_id FROM fd_product WHERE product_id = {cat}")
                com = SQL.fetchone()
                SQL.execute(f"SELECT name FROM fd_manufacturer WHERE manufacturer_id = {com[1]}")
                man_name = SQL.fetchone()[0]
                res = f'Выбранный товар: {cat_name}\nПроизводитель: {man_name}\nЦена: {round(com[0], 2)} р.'
                but.append([Button.inline("Назад", users[event.chat_id]['current']['commodity']['b']),
                            Button.inline("В меню", b"ToMain"), Button.inline("Личный кабинет", b"Profile")])
                await bot.send_message(event.chat_id, res, buttons=but)
            else:
                but = [[]]
                but_idx = 0
                idx = 0
                for i, c in enumerate(options):
                    but[but_idx].append(Button.inline(str(c[0]),
                                                      b'OrderPower' + bytes(str(cat), 'utf-8') + b'|' + bytes(str(c[0]),
                                                                                                              'utf-8')))
                    if idx == 2:
                        but.append([])
                        but_idx += 1
                        idx = -1
                    idx += 1
                but.append([Button.inline("Назад", users[event.chat_id]['current']['commodity']['b']),
                            Button.inline("В меню", b"ToMain"), Button.inline("Личный кабинет", b"Profile")])
                await bot.send_message(event.chat_id, f'Вы выбрали: {cat_name}.\nВыберите оптическую силу:',
                                       buttons=but)
        if event.data.startswith(b'OrderPower'):
            data = event.data.split(b'OrderPower')[1].decode("utf-8")
            but = [[Button.inline("В корзину", b'CartAdd' + bytes(data, 'utf-8')),
                    Button.inline("Оформить заказ", b"OrderCreate" + bytes(data, 'utf-8'))]]
            cat, power = data.split('|', maxsplit=1)
            cat = int(cat)
            print(data)
            users[event.chat_id]['current']['power'] = {'b': event.data, 'c': cat}
            SQL.execute(f"SELECT price, manufacturer_id FROM fd_product WHERE product_id = {cat}")
            com = SQL.fetchone()
            SQL.execute(f"SELECT name FROM fd_manufacturer WHERE manufacturer_id = {com[1]}")
            man_name = SQL.fetchone()[0]
            SQL.execute(f"SELECT name FROM fd_product_description WHERE language_id = 1 AND product_id = {cat}")
            cat_name = SQL.fetchone()[0]
            res = f'Выбранный товар: {cat_name}\nПроизводитель: {man_name}\nОптическая сила: {power}\nЦена: {round(com[0], 2)} р.'
            but.append([Button.inline("Назад", users[event.chat_id]['current']['commodity']['b']),
                        Button.inline("В меню", b"ToMain"), Button.inline("Личный кабинет", b"Profile")])
            await bot.send_message(event.chat_id, res, buttons=but)

        if event.data.startswith(b'OrderCreate'):
            if event.data == b'OrderCreate':
                if not 'cart' in users[event.chat_id]:
                    await bot.send_message(event.chat_id, 'Ваша корзина пуста!',
                                           buttons=[Button.inline("Назад", b"Profile")])
                    return
                elif not users[event.chat_id]['cart']:
                    await bot.send_message(event.chat_id, 'Корзина пуста', buttons=[Button.inline("Назад", b"ToMain")])
                    return
            else:
                data = event.data.split(b'OrderCreate')[1].decode("utf-8")
                if '|' in data:
                    cat, power = data.split('|', maxsplit=1)
                else:
                    cat, power = data, ''
                cat = int(cat)
                SQL.execute(f"SELECT model FROM fd_product WHERE product_id = {cat}")
                cat_mod = SQL.fetchone()[0]
                SQL.execute(f"SELECT name FROM fd_product_description WHERE language_id = 1 AND product_id = {cat}")
                cat_name = SQL.fetchone()[0]
                if not 'cart' in users[event.chat_id]:
                    users[event.chat_id]["cart"] = [
                        {'id': cat, 'power': power, 'name': cat_name, 'model': cat_mod, 'quantity': 1}]
                elif not users[event.chat_id]['cart']:
                    users[event.chat_id]["cart"] = [
                        {'id': cat, 'power': power, 'name': cat_name, 'model': cat_mod, 'quantity': 1}]
                else:
                    exFlag = False
                    for idx, com in enumerate(users[event.chat_id]["cart"]):
                        if com['id'] == cat:
                            if com['power']:
                                if com['power'] == power:
                                    exFlag = True
                            else:
                                exFlag = True
                    if not exFlag:
                        users[event.chat_id]["cart"].append(
                            {'id': cat, 'power': power, 'name': cat_name, 'model': cat_mod, 'quantity': 1})
            res = 'Подтвердите данные заказа:\n'
            total_price = 0
            for i, c in enumerate(users[event.chat_id]["cart"]):
                SQL.execute(f"SELECT price FROM fd_product WHERE product_id = {c['id']}")
                price = SQL.fetchone()[0]
                res += f'{i + 1}. {c["name"]}'
                if c['power']:
                    res += f' {c["power"]} дптр.'
                if not '(' in c['name']:
                    res += f' {c["model"]}'
                res += f'\n   {c["quantity"]} ед.  {round(price, 2)} руб.'
                if c['quantity'] > 1:
                    res += f"   — всего {round(price * c['quantity'], 2)} руб."
                res += '\n'
                total_price += price
            res += f'\nСумма заказа:\n  {round(total_price, 2)} руб.\nСтоимость доставки:\n  190 руб.\nСумма к оплате:\n  {round(total_price, 2) + 190} руб.'
            button_b = b'ToMain' if event.data == b'OrderCreate' else b'OrderComm' + bytes(str(cat), 'utf-8')
            users[event.chat_id]['order'] = {'backtoshop': button_b}
            await bot.send_message(event.chat_id, res, buttons=[Button.inline("Подтвердить", b'OrderBilling_a'),
                                                                Button.inline("Отмена", button_b)])

        if event.data.startswith(b'OrderBilling'):
            if event.data.startswith(b'OrderBilling_a'):
                if event.data.startswith(b'OrderBilling_a_new'):
                    async with bot.conversation(event.chat_id, total_timeout=6000, exclusive=False) as conv:
                        try:
                            await conv.send_message(f"Введите адрес:",
                                                    buttons=[Button.inline("Назад", b'OrderBilling_a')])
                            address = await conv.get_response()
                            address = address.message
                            conv.cancel()
                        except asyncio.TimeoutError:
                            await bot.send_message(event.chat_id, 'Время ожидания истекло. Повторите операцию.')
                            conv.cancel()
                            return
                    sql_insert = f"INSERT INTO fd_address(customer_id, firstname, lastname, company, address_1," \
                                 f"address_2, city, postcode, country_id, zone_id, custom_field) " \
                                 f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                    SQL.execute(sql_insert, (memdata[0], memdata[3], memdata[4], '', address, '', '', '', 0, 0, '[]'))
                    mydb.commit()
                    await bot.send_message(event.chat_id, 'Успешно!')
                else:
                    async with bot.conversation(event.chat_id, exclusive=False) as conv:
                        await conv.cancel_all()
                but = [[]]
                but_idx = 0
                SQL.execute(f"SELECT * FROM fd_address WHERE customer_id = {memdata[0]}")
                addresses = SQL.fetchall()
                if addresses:
                    res = f'Выберите адрес доставки:\n'
                    for i, a in enumerate(addresses):
                        res += f'{i + 1}. {a[5]}\n'
                        but[but_idx].append(Button.inline(str(i + 1), b'OrderBilling_b' + bytes(str(i), 'utf-8')))
                        if i % 3 == 2:
                            but.append([])
                            but_idx += 1
                else:
                    res = f'У вас нет адресов. Вы можете добавить один:\n'
                but.append([Button.inline('Добавить адрес', b'OrderBilling_a_new'),
                            Button.inline('Вернуться', users[event.chat_id]['order']['backtoshop'])])
                await bot.send_message(event.chat_id, res, buttons=but)
            if event.data.startswith(b'OrderBilling_b'):
                aid = int(event.data.split(b'OrderBilling_b')[1].decode('utf-8'))
                bb = users[event.chat_id]['order']['backtoshop']
                users[event.chat_id]['order'] = {'backtoshop': bb, 'address': aid}
                res = f'Выберите время, в которое вам удобно получить заказ:'
                await bot.send_message(event.chat_id, res, buttons=[Button.inline('10-15 часов', b'OrderBilling_d0'),
                                                                    Button.inline('12-16 часов', b'OrderBilling_d1'),
                                                                    Button.inline('14-18 часов', b'OrderBilling_d2')])
            if event.data.startswith(b'OrderBilling_d'):
                tid = int(event.data.split(b'OrderBilling_d')[1].decode('utf-8'))
                users[event.chat_id]['order']['time'] = tid
                res = f'Выберите способ оплаты:'
                await bot.send_message(event.chat_id, res,
                                       buttons=[[Button.inline('Заплачу курьеру на месте', b'OrderBilling_e0')],
                                                [Button.inline('Оплата онлайн', b'OrderBilling_e1')]])
            if event.data.startswith(b'OrderBilling_e'):
                if not event.data.startswith(b'OrderBilling_ee') and not 'comment' in users[event.chat_id]['order']:
                    eid = int(event.data.split(b'OrderBilling_e')[1].decode('utf-8'))
                    users[event.chat_id]['order']['paykata'] = eid
                    async with bot.conversation(event.chat_id, total_timeout=6000, exclusive=False) as conv:
                        try:
                            await conv.send_message(f"Оставьте комментарий к заказу, например, удобную дату доставки:",
                                                    buttons=(
                                                    [Button.inline('Оставить без комментария', b'OrderBilling_ee')]))
                            comment = await conv.get_response()
                            comment = comment.message
                            conv.cancel()
                        except asyncio.TimeoutError:
                            await bot.send_message(event.chat_id, 'Время ожидания истекло. Повторите операцию.')
                            conv.cancel()
                            return
                else:
                    if 'comment' not in users[event.chat_id]['order']:
                        comment = ''
                    async with bot.conversation(event.chat_id, exclusive=False) as conv:
                        await conv.cancel_all()

                res = ''
                total_price = 0
                for i, c in enumerate(users[event.chat_id]["cart"]):
                    SQL.execute(f"SELECT price FROM fd_product WHERE product_id = {c['id']}")
                    price = SQL.fetchone()[0]
                    res += f'{i + 1}. {c["name"]}'
                    if c['power']:
                        res += f' {c["power"]} дптр.'
                    if not '(' in c['name']:
                        res += f' {c["model"]}'
                    res += f'\n   {c["quantity"]} ед.  {round(price, 2)} руб.'
                    if c['quantity'] > 1:
                        res += f"   — всего {round(price * c['quantity'], 2)} руб."
                    res += '\n'
                    total_price += price
                total_price = round(total_price, 2)
                SQL.execute(f"SELECT * FROM fd_address WHERE customer_id = {memdata[0]}")
                addresses = SQL.fetchall()
                times = ['10-15 часов', '12-16 часов', '14-18 часов']
                ds = ['На месте', 'Онлайн']
                res += f"\nАдрес: {addresses[users[event.chat_id]['order']['address']][5]}\n" \
                       f"Время доставки: {times[users[event.chat_id]['order']['time']]}\n" \
                       f"Способ оплаты: {ds[users[event.chat_id]['order']['paykata']]}\n" \
                       f"Сумма заказа:\n  {round(total_price, 2)} руб.\nСтоимость доставки:\n  190 руб.\n" \
                       f"Сумма к оплате:\n  {round(total_price, 2) + 190} руб."
                users[event.chat_id]['order']['total'] = total_price
                users[event.chat_id]['order']['comment'] = comment
                await bot.send_message(event.chat_id, f'Подтвердите все данные:\n' + res,
                                       buttons=[[Button.inline('Да, всё верно', b'OrderBilling_f')],
                                                [Button.inline('Вернуться', b'OrderBilling_a')]])
            if event.data.startswith(b'OrderBilling_f'):
                comment = users[event.chat_id]['order']['comment']
                time = datetime.datetime.utcnow()
                total_price = users[event.chat_id]['order']['total']

                SQL.execute('SELECT order_id FROM fd_order_history ORDER BY order_id DESC')
                order_id = SQL.fetchone()[0] + 1
                SQL.execute('SELECT order_product_id FROM fd_order_product ORDER BY order_product_id DESC')
                order_product_id = SQL.fetchone()[0] + 1

                sql_insert = 'INSERT INTO fd_order_history(order_id, order_status_id, notify, comment, date_added) VALUES (%s,%s,%s,%s,%s)'
                if users[event.chat_id]['order']['paykata'] == 0:
                    SQL.execute(sql_insert, (order_id, 1, 0, comment, time))
                else:
                    SQL.execute(sql_insert, (order_id, 17, 0, comment, time))

                sql_insert = 'INSERT INTO fd_order_total(order_id, code, title, value, sort_order) VALUES (%s,%s,%s,%s,%s)'
                val = [(order_id, 'sub_total', 'Предварительная стоимость', total_price, 1),
                       (order_id, 'shipping', 'Фиксированная стоимость доставки', 190, 3),
                       (order_id, 'total', 'Итого', total_price + 190, 9)]
                SQL.executemany(sql_insert, val)

                sql_insert = 'INSERT INTO fd_order_product(order_id, product_id, name, model, quantity, price, total, tax, reward) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)'
                val = []
                sql_insert2 = 'INSERT INTO fd_order_option(order_id, order_product_id, product_option_id, product_option_value_id, name, value, type) VALUES (%s,%s,%s,%s,%s,%s,%s)'
                val2 = []
                comnum = 0
                for i, c in enumerate(users[event.chat_id]["cart"]):
                    SQL.execute(f"SELECT price FROM fd_product WHERE product_id = {c['id']}")
                    price = SQL.fetchone()[0]
                    val.append(
                        (order_id, c['id'], c['name'], c['model'], c['quantity'], price, price * c['quantity'], 0.0, 0))
                    if c['power']:
                        SQL.execute(
                            f"SELECT product_option_id, product_option_value_id FROM fd_product_option_value WHERE option_value_id in (SELECT option_value_id FROM fd_option_value_description WHERE name = {str(c['power'])} AND (option_id = 13 OR option_id = 18))")
                        oids = SQL.fetchone()
                        if oids:
                            val2.append(
                                (order_id, order_product_id, oids[0], oids[1], 'Оптическая сила', c['power'], 'select'))
                        else:
                            val2.append(
                                (order_id, order_product_id, 0, 0, 'Оптическая сила', c['power'], 'select'))
                    order_product_id += 1
                    comnum += c['quantity']
                SQL.executemany(sql_insert, val)
                if val2:
                    SQL.executemany(sql_insert2, val2)

                SQL.execute(f"SELECT * FROM fd_address WHERE customer_id = {memdata[0]}")
                addresses = SQL.fetchall()
                times = ['10-15 часов', '12-16 часов', '14-18 часов']
                ds = ['При получении', 'Онлайн']

                sql_insert = 'INSERT INTO fd_order(order_id, invoice_prefix, store_name, store_url, customer_group_id, firstname,' \
                             ' lastname, email, telephone, fax, custom_field, payment_firstname, payment_lastname,' \
                             ' payment_company, payment_address_1, payment_address_2, payment_city, payment_postcode,' \
                             ' payment_country, payment_country_id, payment_zone, payment_zone_id,' \
                             ' payment_address_format, payment_custom_field, payment_method, payment_code,' \
                             ' shipping_firstname, shipping_lastname, shipping_company, shipping_address_1,' \
                             ' shipping_address_2, shipping_city, shipping_postcode, shipping_country,' \
                             ' shipping_country_id, shipping_zone, shipping_zone_id, shipping_address_format,' \
                             ' shipping_custom_field, shipping_method, shipping_code, comment, affiliate_id,' \
                             ' commission, marketing_id, tracking, language_id, currency_id, currency_code,' \
                             ' ip, forwarded_ip, user_agent, accept_language, date_added,' \
                             ' date_modified, comment_manager, manager_process_orders, text_ttn)' \
                             ' VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)'
                SQL.execute(sql_insert, (order_id, 'СЧТ-ЗФМД 16-00', 'Интернет-оптика Eye Home',
                                         'http://eyehome.ru/', memdata[1], memdata[3], memdata[4], memdata[5],
                                         memdata[6],
                                         memdata[7], '[]', memdata[3], memdata[4], '',
                                         addresses[users[event.chat_id]['order']['address']][5], '', '', '', '', 0, '',
                                         0, '', times[users[event.chat_id]['order']['time']],
                                         ds[users[event.chat_id]['order']['paykata']], 'cod', memdata[3],
                                         memdata[4], '', addresses[users[event.chat_id]['order']['address']][5], '',
                                         '', '', '', 0, '', 0, '', '[]', 'Фиксированная стоимость доставки',
                                         'flat.flat', comment, 0, 0.0, 0, '', 1, 1, 'RUB', 'no ip', '',
                                         'Telegram Bot', 'ru', time, time, '', '', ''))
                mydb.commit()
                if users[event.chat_id]['order']['paykata'] == 0:
                    await bot.send_message(event.chat_id,
                                           f'Спасибо за покупку! Номер заказа: {order_id}. Статус заказа можно посмотреть в профиле. Дождитесь звонка оператора.',
                                           buttons=[Button.inline('В профиль', b'Profile')])
                else:
                    await bot.send_message(event.chat_id, f'Форма для оплаты заказа:')
                    await bot.send_file(event.chat_id, generate_invoice(
                        price_label=f'Заказ #{order_id}', price_amount=int((total_price + 190) * 100), currency='RUB',
                        title='Оплата заказа Eye Home',
                        description=f"Заказ #{order_id}, единиц товара: {comnum}",
                        payload=f'{order_id}', start_param=f'{order_id}'))
                del users[event.chat_id]['order']
                del users[event.chat_id]['cart']

        if event.data.startswith(b'CartAdd'):
            data = event.data.split(b'CartAdd')[1].decode("utf-8")
            if '|' in data:
                cat, power = data.split('|', maxsplit=1)
            else:
                cat, power = data, ''
            cat = int(cat)
            SQL.execute(f"SELECT model FROM fd_product WHERE product_id = {cat}")
            cat_mod = SQL.fetchone()[0]
            SQL.execute(f"SELECT name FROM fd_product_description WHERE language_id = 1 AND product_id = {cat}")
            cat_name = SQL.fetchone()[0]
            if not 'cart' in users[event.chat_id]:
                if power:
                    cat_name += f' ({power})'
                users[event.chat_id]["cart"] = [
                    {'id': cat, 'power': power, 'name': cat_name, 'model': cat_mod, 'quantity': 1}]
                res = f'Добавлено: {cat_name}!\nТоваров в корзине: 1'
            elif not users[event.chat_id]['cart']:
                if power:
                    cat_name += f' ({power})'
                users[event.chat_id]["cart"] = [
                    {'id': cat, 'power': power, 'name': cat_name, 'model': cat_mod, 'quantity': 1}]
                res = f'Добавлено: {cat_name}!\nТоваров в корзине: 1'
            else:
                count = 0
                exFlag = False
                for idx, com in enumerate(users[event.chat_id]["cart"]):
                    count += users[event.chat_id]["cart"][idx]['quantity']
                    if com['id'] == cat:
                        if com['power']:
                            if com['power'] == power:
                                users[event.chat_id]["cart"][idx]['quantity'] += 1
                                exFlag = True
                        else:
                            users[event.chat_id]["cart"][idx]['quantity'] += 1
                            exFlag = True
                if not exFlag:
                    users[event.chat_id]["cart"].append(
                        {'id': cat, 'power': power, 'name': cat_name, 'model': cat_mod, 'quantity': 1})
                if power:
                    cat_name += f' ({power})'
                res = f'Добавлено: {cat_name}!\nТоваров в корзине: {count + 1}'
            await bot.send_message(event.chat_id, res,
                                   buttons=[[Button.inline("Назад", b'OrderComm' + bytes(str(cat), 'utf-8'))],
                                            [Button.inline('Перейти в корзину', b'Cart'),
                                             Button.inline('Оформить заказ', b'OrderCreate')]])

        if event.data.startswith(b'AdminPanel'):
            today = datetime.date.today()
            SQL.execute(
                f"SELECT order_id, firstname, lastname, payment_address_1, comment, date_added, payment_method, payment_custom_field, email FROM fd_order WHERE date_added >= '{today}'")
            orders = SQL.fetchall()
            totals = []
            for order in orders:
                SQL.execute(f"SELECT value FROM fd_order_total WHERE order_id = {order[0]} AND code = 'total'")
                totals.append(SQL.fetchone()[0])
            if orders:
                if b'|' in event.data:
                    page = int(event.data.split(b'AdminPanel')[1].split(b'|')[0].decode('utf-8'))
                    code = event.data.split(b'|')[1].decode('utf-8')
                    if code.isdigit():
                        order1, order2, order3 = orders[int(code)], [], []
                        res = ''
                        but = [[Button.inline("Подтвердить заказ",
                                              b"AdminPanel" + bytes(str(page) + '|p' + code, 'utf-8')),
                                Button.inline("Связаться с покупателем",
                                              b"AdminPanel" + bytes(str(page) + '|m' + code, 'utf-8'))],
                               [Button.inline("Назад", b"AdminPanel" + bytes(str(page), 'utf-8'))]]
                    elif code.startswith('p'):
                        code = code.split('p')[1]
                        order1, order2, order3 = orders[int(code)], [], []
                        res = ''
                        but = [[Button.inline("Связаться с покупателем",
                                              b"AdminPanel" + bytes(str(page) + '|m' + code, 'utf-8'))],
                               [Button.inline("Назад", b"AdminPanel" + bytes(str(page), 'utf-8'))]]
                        SQL.execute(
                            f'UPDATE fd_order_history SET order_status_id = 2 WHERE order_id = {orders[int(code)][0]}')
                        mydb.commit()
                        await bot.send_message(event.chat_id, f'Заказ #{orders[int(code)][0]} подтверждён.')
                    else:
                        code = code.split('m')[1]
                        order1, order2, order3 = orders[int(code)], [], []
                        res = ''
                        but = [[Button.inline("Назад", b"AdminPanel" + bytes(str(page), 'utf-8'))]]
                        async with bot.conversation(event.chat_id, total_timeout=6000, exclusive=False) as conv:
                            try:
                                await conv.send_message(f"Напишите сообщение. Оно будет отправлено заказчику.",
                                                        buttons=[
                                                            Button.inline("Назад", b"AdminPanel" + bytes(str(page)))])
                                mes = await conv.get_response()
                                mes = mes.message
                                conv.cancel()
                            except asyncio.TimeoutError:
                                await bot.send_message(event.chat_id, 'Время ожидания истекло. Повторите операцию.',
                                                       buttons=[
                                                           Button.inline("Назад", b"AdminPanel" + bytes(str(page)))])
                                conv.cancel()
                                return
                        if mes:
                            SQL.execute(
                                f"SELECT telegram_id, firstname, lastname FROM fd_customer WHERE email = {orders[int(code)][8]}")
                            chat = SQL.fetchone()
                            await bot.send_message(chat[0], mes)
                            await bot.send_message(event.chat_id, f'Сообщение отправлено заказчику {chat[1]} {chat[2]}')
                else:
                    res = f'Заказов сегодня: {len(orders)} на сумму {round(sum(totals), 2)}\n\n'
                    if event.data != b'AdminPanel':
                        async with bot.conversation(event.chat_id, exclusive=False) as conv:
                            await conv.cancel_all()
                    if event.data == b'AdminPanel' or event.data == b'AdminPanel0':
                        order1 = orders[0]
                        order2 = orders[1] if len(orders) > 1 else []
                        order3 = orders[2] if len(orders) > 2 else []
                        but = [[Button.inline("Назад в меню", b"ToMain")]]
                        if len(orders) > 3:
                            but[0].append(Button.inline("Дальше", b"AdminPanel1"))
                        idx = 0
                    else:
                        idx = int(event.data.split(b'AdminPanel')[1].split(b'|')[0].decode('utf-8'))
                        order1 = orders[idx * 3]
                        order2 = orders[idx * 3 + 1] if len(orders) > idx * 3 + 1 else []
                        order3 = orders[idx * 3 + 2] if len(orders) > idx * 3 + 2 else []
                        if len(orders) <= idx * 3 + 3:
                            but = [[Button.inline("Назад", b"AdminPanel" + bytes(str(idx - 1), 'utf-8')),
                                    Button.inline("Вернуться в меню", b"ToMain")]]
                        else:
                            but = [[Button.inline("Назад", b"AdminPanel" + bytes(str(idx - 1), 'utf-8')),
                                    Button.inline("Дальше", b"AdminPanel" + bytes(str(idx + 1), 'utf-8'))],
                                   [Button.inline("Вернуться в меню", b"ToMain")]]
                    lastidx = idx * 3 + 3 if order3 else idx * 3 + 2 if order2 else idx * 3 + 1
                    res += f'Страница {idx + 1} ({idx * 3 + 1}-{lastidx})\n'
                    but.append(
                        [Button.inline(str(idx * 3), b"AdminPanel" + bytes(str(idx) + '|' + str(idx * 3), 'utf-8')),
                         Button.inline(str(idx * 3 + 1),
                                       b"AdminPanel" + bytes(str(idx) + '|' + str(idx * 3 + 1), 'utf-8')),
                         Button.inline(str(idx * 3 + 2),
                                       b"AdminPanel" + bytes(str(idx) + '|' + str(idx * 3 + 2), 'utf-8'))])
                for order in [order1, order2, order3]:
                    if not order:
                        continue
                    total_price = totals[orders.index(order)]
                    SQL.execute(
                        f'SELECT order_product_id, name, quantity, total FROM fd_order_product WHERE order_id = {order[0]}')
                    products = SQL.fetchall()
                    SQL.execute(
                        f"SELECT name FROM fd_order_status WHERE order_status_id = (SELECT order_status_id FROM fd_order_history WHERE order_id = {order[0]})")
                    status = SQL.fetchone()[0]
                    SQL.execute(f"SELECT order_product_id, value FROM fd_order_option WHERE order_id = {order[0]}")
                    options = SQL.fetchall()
                    option_ids = [i[0] for i in options]
                    res += f'  Заказ #{order[0]}. Имя: {order[1]} {order[2]}\n  Дата и время заказа: {order[5]} (Доставка на {order[7]})\n  Способ оплаты и адрес: {order[6]}, {order[3]}\n  Общая стоимость: {round(total_price, 2)} руб., в т.ч. доставка: 190 руб.\n  Статус: {status}\n'
                    if order[4]:
                        res += f'  Комментарий: {order[4]}\n'
                    res += '  Содержание заказа:\n'
                    for i, com in enumerate(products):
                        res += f'    {i + 1}. {com[1]} '
                        if com[0] in option_ids:
                            res += f'({options[option_ids.index(com[0])][1]}) '
                        res += f'{com[2]} шт. на сумму {round(com[3], 2)}\n'
                    res += '\n'
                await bot.send_message(event.chat_id, res, buttons=but)
            else:
                await bot.send_message(event.chat_id, 'Заказов сегодня нет',
                                       buttons=[Button.inline("Назад", b"ToMain")])

        if event.data == b'GetAddress':
            async with bot.conversation(event.chat_id, total_timeout=6000, exclusive=False) as conv:
                try:
                    await conv.send_message(f"Введите адрес:", buttons=[Button.inline("Назад", b"Profile")])
                    address = await conv.get_response()
                    address = address.message
                    conv.cancel()
                except asyncio.TimeoutError:
                    await bot.send_message(event.chat_id, 'Время ожидания истекло. Повторите операцию.')
                    conv.cancel()
                    return
            sql_insert = f"INSERT INTO fd_address(customer_id, firstname, lastname, company, address_1," \
                         f"address_2, city, postcode, country_id, zone_id, custom_field) " \
                         f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            SQL.execute(sql_insert, (memdata[0], memdata[3], memdata[4], '', address, '', '', '', 0, 0, '[]'))
            mydb.commit()
            await bot.send_message(event.chat_id, 'Успешно!')

        if event.data.startswith(b'History'):
            SQL.execute(
                f"SELECT order_id, payment_address_1, comment, date_added, payment_method, payment_custom_field FROM fd_order WHERE email = '{memdata[5]}' ORDER BY date_added DESC")
            orders = SQL.fetchall()
            if orders:
                if b'|' in event.data:
                    page = int(event.data.split(b'History')[1].split(b'|')[0].decode('utf-8'))
                    code = event.data.split(b'|')[1].decode('utf-8')
                    if code.isdigit():
                        order1, order2, order3 = orders[int(code)], [], []
                        res = ''
                        but = [[Button.inline("Отменить заказ", b"History" + bytes(str(page) + '|c' + code, 'utf-8')),
                                Button.inline("Назад", b"History" + bytes(str(page), 'utf-8'))]]
                    elif code.startswith('c'):
                        code = code.split('c')[1]
                        order1, order2, order3 = orders[int(code)], [], []
                        res = ''
                        but = [[Button.inline("Вы уверены?", b"History" + bytes(str(page) + '|d' + code, 'utf-8')),
                                Button.inline("Назад", b"History" + bytes(str(page), 'utf-8'))]]
                    else:
                        code = code.split('d')[1]
                        order1, order2, order3 = orders[int(code)], [], []
                        res = ''
                        but = [[Button.inline("Назад", b"History" + bytes(str(page), 'utf-8'))]]
                        SQL.execute(
                            f'UPDATE fd_order_history SET order_status_id = 7 WHERE order_id = {orders[int(code)][0]}')
                        mydb.commit()
                        await bot.send_message(event.chat_id, f'Заказ #{orders[int(code)][0]} отменён.')
                else:
                    if event.data == b'History' or event.data == b'History0':
                        order1 = orders[0]
                        order2 = orders[1] if len(orders) > 1 else []
                        order3 = orders[2] if len(orders) > 2 else []
                        but = [[Button.inline("Вернуться в профиль", b"Profile")]]
                        if len(orders) > 3:
                            but[0].append(Button.inline("Дальше", b"History1"))
                        idx = 0
                    else:
                        idx = int(event.data.split(b'History')[1].split(b'|')[0].decode('utf-8'))
                        order1 = orders[idx * 3]
                        order2 = orders[idx * 3 + 1] if len(orders) > idx * 3 + 1 else []
                        order3 = orders[idx * 3 + 2] if len(orders) > idx * 3 + 2 else []
                        but = [[Button.inline("Назад", b"History" + bytes(str(idx - 1), 'utf-8'))],
                               [Button.inline("Вернуться в профиль", b"Profile")]]
                        if len(orders) > idx * 3 + 3:
                            but[0].append(Button.inline("Дальше", b"History" + bytes(str(idx + 1), 'utf-8')))
                    lastidx = idx * 3 + 3 if order3 else idx * 3 + 2 if order2 else idx * 3 + 1
                    addict_res = f' из {len(orders)})' if len(orders) > 2 else ')'
                    res = f'Страница {idx + 1} ({idx * 3 + 1}-{lastidx}{addict_res}\nЕсли вы хотите отменить заказ, нажмите на кнопку с его номером ниже.\n\n'
                    addict = [Button.inline(str(order1[0]), b"History" + bytes(str(idx) + '|' + str(idx * 3), 'utf-8'))]
                    if order2:
                        addict.append(Button.inline(str(order2[0]),
                                                    b"History" + bytes(str(idx) + '|' + str(idx * 3 + 1), 'utf-8')))
                    if order3:
                        addict.append(Button.inline(str(order3[0]),
                                                    b"History" + bytes(str(idx) + '|' + str(idx * 3 + 2), 'utf-8')))
                    but.append(addict)
                for order in [order1, order2, order3]:
                    if not order:
                        continue
                    SQL.execute(f"SELECT value FROM fd_order_total WHERE order_id = {order[0]} AND code = 'total'")
                    total_price = SQL.fetchone()[0]
                    SQL.execute(
                        f'SELECT order_product_id, name, quantity, total FROM fd_order_product WHERE order_id = {order[0]}')
                    products = SQL.fetchall()
                    SQL.execute(
                        f"SELECT name FROM fd_order_status WHERE order_status_id = (SELECT order_status_id FROM fd_order_history WHERE order_id = {order[0]})")
                    status = SQL.fetchone()[0]
                    SQL.execute(f"SELECT order_product_id, value FROM fd_order_option WHERE order_id = {order[0]}")
                    options = SQL.fetchall()
                    option_ids = [i[0] for i in options]
                    res += f'  Заказ #{order[0]} от {order[3]} (Доставка на {order[5]})\n  Способ оплаты и адрес: {order[4]}, {order[1]}\n  Общая стоимость: {round(total_price, 2)} руб., в т.ч. доставка: 190 руб.\n  Статус: {status}\n'
                    if order[2]:
                        res += f'  Комментарий: {order[2]}\n'
                    res += '  Содержание заказа:\n'
                    for i, com in enumerate(products):
                        res += f'    {i + 1}. {com[1]} '
                        if com[0] in option_ids:
                            res += f'({options[option_ids.index(com[0])][1]}) '
                        res += f'{com[2]} шт. на сумму {round(com[3], 2)}\n'
                    res += '\n'
                await bot.send_message(event.chat_id, res, buttons=but)
            else:
                await bot.send_message(event.chat_id, 'У вас нет заказов', buttons=[Button.inline("Назад", b"Profile")])

        if event.data.startswith(b'OrderRepeat'):
            SQL.execute(
                f"SELECT order_id, payment_address_1, comment, date_added, payment_method, payment_custom_field FROM fd_order WHERE email = '{memdata[5]}' ORDER BY date_added DESC")
            order = SQL.fetchone()
            if order:
                if event.data == b'OrderRepeat0':
                    SQL.execute(
                        f'SELECT order_product_id, product_id, name, model, quantity FROM fd_order_product WHERE order_id = {order[0]}')
                    products = SQL.fetchall()
                    SQL.execute(f"SELECT order_product_id, value FROM fd_order_option WHERE order_id = {order[0]}")
                    options = SQL.fetchall()
                    option_ids = [i[0] for i in options]
                    users[event.chat_id]["cart"] = []
                    for com in products:
                        power = options[option_ids.index(com[0])][1] if com[0] in option_ids else ''
                        users[event.chat_id]["cart"].append(
                            {'id': com[1], 'power': power, 'name': com[2], 'model': com[3], 'quantity': com[4]})
                    SQL.execute(f"SELECT * FROM fd_address WHERE customer_id = {memdata[0]}")
                    addresses = SQL.fetchall()
                    addresses = [i[5] for i in addresses]
                    times = ['10-15 часов', '12-16 часов', '14-18 часов']
                    ds = ['При получении', 'Онлайн']
                    if order[1] in addresses and order[5] in times and order[4] in ds:
                        total_price = 0
                        for i, c in enumerate(users[event.chat_id]["cart"]):
                            SQL.execute(f"SELECT price FROM fd_product WHERE product_id = {c['id']}")
                            price = SQL.fetchone()[0]
                            total_price += price
                        total_price = round(total_price, 2)
                        users[event.chat_id]['order'] = {'address': addresses.index(order[1]),
                                                         'time': times.index(order[5]), 'paykata': ds.index(order[4]),
                                                         'comment': order[2], 'total': total_price,
                                                         'backtoshop': b'ToMain'}
                        await bot.send_message(event.chat_id, 'Заказ сформирован! Нажмите "Продолжить"',
                                               buttons=[Button.inline('Продолжить', b'OrderBilling_f'),
                                                        Button.inline('Назад', b'OrderRepeat')])
                    else:
                        users[event.chat_id]['order'] = {'backtoshop': b'ToMain'}
                        await bot.send_message(event.chat_id,
                                               'Ошибка: Мы не смогли обработать данные вашего заказа. Нажмите "Продолжить", чтобы ввести данные заказа вручную.',
                                               buttons=[Button.inline('Продолжить', b'OrderBilling_a'),
                                                        Button.inline('Назад', b'OrderRepeat')])
                elif event.data == b'OrderRepeat1':
                    SQL.execute(
                        f'SELECT order_product_id, product_id, name, model, quantity FROM fd_order_product WHERE order_id = {order[0]}')
                    products = SQL.fetchall()
                    SQL.execute(f"SELECT order_product_id, value FROM fd_order_option WHERE order_id = {order[0]}")
                    options = SQL.fetchall()
                    option_ids = [i[0] for i in options]
                    users[event.chat_id]["cart"] = []
                    for com in products:
                        power = options[option_ids.index(com[0])][1] if com[0] in option_ids else ''
                        users[event.chat_id]["cart"].append(
                            {'id': com[1], 'power': power, 'name': com[2], 'model': com[3], 'quantity': com[4]})
                    users[event.chat_id]['order'] = {'backtoshop': b'ToMain'}
                    await bot.send_message(event.chat_id, 'Корзина сформирована! Нажмите "Продолжить"',
                                           buttons=[Button.inline('Продолжить', b'OrderBilling_a'),
                                                    Button.inline('Назад', b'OrderRepeat')])
                else:
                    SQL.execute(f"SELECT value FROM fd_order_total WHERE order_id = {order[0]} AND code = 'total'")
                    total_price = SQL.fetchone()[0]
                    SQL.execute(
                        f'SELECT order_product_id, name, quantity, total FROM fd_order_product WHERE order_id = {order[0]}')
                    products = SQL.fetchall()
                    SQL.execute(f"SELECT order_product_id, value FROM fd_order_option WHERE order_id = {order[0]}")
                    options = SQL.fetchall()
                    option_ids = [i[0] for i in options]
                    res = 'Данные вашего последнего заказа:\n'
                    res += f'  Заказ #{order[0]} от {order[3]} (Доставка на {order[5]})\n  Способ оплаты и адрес: {order[4]}, {order[1]}\n  Общая стоимость: {total_price} руб., в т.ч. доставка: 190 руб.\n'
                    if order[2]:
                        res += f'  Комментарий: {order[2]}\n'
                    res += '  Содержание заказа:\n'
                    for i, com in enumerate(products):
                        res += f'    {i + 1}. {com[1]} '
                        if com[0] in option_ids:
                            res += f'({options[option_ids.index(com[0])][1]}) '
                        res += f'{com[2]} шт. на сумму {com[3]}\n'
                    res += '\nЧтобы полностью повторить заказ, нажмите "Повторить". Если вы хотите купить ту же корзину, но изменить данные заказа, нажмите "Изменить"'
                    await bot.send_message(event.chat_id, res, buttons=[
                        [Button.inline('Повторить', b'OrderRepeat0'), Button.inline('Изменить', b'OrderRepeat1')],
                        [Button.inline('Назад', b'ToMain')]])
            else:
                await bot.send_message(event.chat_id, 'У вас ещё не было заказов:)',
                                       buttons=[Button.inline("Назад", b"ToMain")])

    except Exception:
        traceback.print_exc()


def main():
    print('работаю')
    bot.run_until_disconnected()


if __name__ == '__main__':
    main()
