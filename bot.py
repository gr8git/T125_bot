import re
import logging
import os
import io

from PIL import Image
from config_reader import config
import pyodbc as odbc

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ParseMode
from aiogram.types.inline_keyboard import InlineKeyboardButton
from aiogram.utils import executor
import aiogram.utils.markdown as md


#Настройка подключения к БД
conn = odbc.connect(f'DRIVER={config.driver.get_secret_value()};SERVER={config.server.get_secret_value()};DATABASE={config.database.get_secret_value()};UID={config.username.get_secret_value()};PWD={config.password.get_secret_value()};Encrypt = Optional;', autocommit=True)
conn.setdecoding(odbc.SQL_CHAR, encoding='cp1251')
conn.setencoding('cp1251')
cursor = conn.cursor()
#Подключаем логи
logging.basicConfig(level=logging.INFO)
#стартовая конфигурация бота
bot = Bot(token = config.api_token.get_secret_value())
# создание просто хранилища для диспетчера

storage = MemoryStorage()
dp = Dispatcher(bot, storage = storage)

# Стейты(шаги) по которым шагает бот
class Form(StatesGroup):
    name = State()  
    age = State()  
    gender = State()  
    phone_number = State()
    city = State()
    photo = State()
    hobbies = State()

#загрузка списка хобби из бд
hobbies = []
cursor.execute('SELECT * FROM hobbies')
for row in cursor:
    hobbies.append(row)

#проверка на кирилицу
def isCirylic(text: str):
    for char in text:
        if re.search(r'[а-яА-ЯёЁ ]', char) is None:
            return False
    return True

#обработчик команды старт
@dp.message_handler(commands='start')
async def cmd_start(message: types.Message):
    #задание начального шага в FSMContext
    await bot.send_message(message.chat.id,"Для реги введите /reg")
    
@dp.message_handler(commands='reg')
async def cmd_reg(message: types.Message):
    result = cursor.execute("SELECT * FROM users WHERE user_telegram_id = ?", message.from_user.id).fetchall()
    if len(result)>0:
        await message.reply("Вы уже зарегестрированны! Вот ваши данные:")
        data_bytes_IO = io.BytesIO(result[0][8])
        img = Image.open(data_bytes_IO)
        img.save('user_output.jpg')
        user_photo = open('user_output.jpg', "rb")
        await bot.send_photo(chat_id = result[0][1], photo = user_photo)
        await bot.send_message(
            message.chat.id,
            md.text(
                md.text('UID Телеграмма:', md.bold(result[0][1])),
                md.text('Юзернейм:', md.bold(result[0][2])),   
                md.text('ФИО:', md.bold(result[0][3])),
                md.text('Возраст:', md.bold(result[0][4])),
                md.text('Пол:', md.bold(result[0][5])),
                md.text('Номер телефона:', md.bold(result[0][6])),
                md.text('Город: ', md.bold(result[0][7])),
                sep= '\n',
            ),  
            parse_mode = ParseMode.MARKDOWN,)
    else:
        #задание начального шага в FSMContext
        await message.reply("Привет! Для начала, введите свое ФИО(кирилицей)")
        await Form.name.set()

#хэндлер для проверки и сохранения ФИО и переводящий на следующий этап формы
@dp.message_handler(lambda message: not isCirylic(message.text),state = Form.name)
async def process_name_invalid(message: types.Message):
    return await message.reply("Кирилицей, пожалуйста, без цифр")
@dp.message_handler(lambda message: isCirylic(message.text),state = Form.name)
async def process_name(message: types.Message, state: FSMContext):
    #создание хранилища внутри FSMContext
    async with state.proxy() as data:
        #сохранение имени в FSMContext
        data['name'] = message.text
    await Form.next()
    await message.reply("Сколько вам полных лет?")


#хэндлер для возраста (текст - число и в разумных диапазонах) и формирующий следующий этап формы с 2 кнопками выбора пола.
@dp.message_handler(lambda message: not message.text.isdigit(), state=Form.age)
async def process_age_invalid(message: types.Message):
    return await message.reply("Возраст должен быть числом.\nСколько вам лет?(только число)")

@dp.message_handler(lambda message: message.text.isdigit() and int(message.text) <100 and int(message.text)>0, state=Form.age)
async def process_age(message: types.Message, state: FSMContext):
    await Form.next()
    #сохранение возраста в FSMContext
    await state.update_data(age=int(message.text))
    #создание разметки для кнопок гендера
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, selective=True)
    markup.add("Мужской", "Женский")
    await message.reply("Ваш пол?", reply_markup = markup)
    
#хэндлер для гендера и формирующий запрос контакта и обработку сообщения
@dp.message_handler(lambda message: message.text not in ["Мужской", "Женский"], state=Form.gender)
async def process_gender_invalid(message: types.Message):
    return await message.reply("ГЕНДЕРОВ ВСЕГО 2")    

@dp.message_handler(state = Form.gender)
async def process_gender(message: types.Message, state: FSMContext):
    await Form.next()
    #создание кнопки поделиться контактом
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    markup.add(InlineKeyboardButton('Поделится номером телефона', request_contact=True))
    #сохранение гендера в FSMContext
    await state.update_data(gender=str(message.text))
    await message.reply("Ваш номер телефона?", reply_markup = markup)

#хэндлер для телефона
@dp.message_handler(content_types = types.ContentType.CONTACT, state = Form.phone_number)
async def process_phone_number(message: types.Message, state: FSMContext):    
    await Form.next()
    #удаляем кнопку телефона
    markup = types.ReplyKeyboardRemove()
    #сохранение номера в FSMContext
    await state.update_data(phone_number=str(message.contact.phone_number))
    await message.reply("Введите город проживания", reply_markup = markup)

#хэндлер для города
@dp.message_handler(lambda message: not isCirylic(message.text), state = Form.city)
async def process_city_invalid(message: types.Message):
    return await message.reply("Еще раз и кирилицей, без приколов")
@dp.message_handler(lambda message: isCirylic(message.text), state = Form.city)
async def process_city(message: types.Message, state: FSMContext):
    await Form.next()
    #сохранение города в FSMContext
    await state.update_data(city = str(message.text))
    await message.reply("А теперь загрузи фото!")

#хэндлер для фото
@dp.message_handler(content_types = types.ContentType.PHOTO, state = Form.photo)
async def process_photo(message: types.Message, state: FSMContext):
    await Form.next()
    #загрузка фотки из телеги
    await message.photo[-1].download('user.jpg')
    #конвертация фотки в массив байтов
    byte_img_IO = io.BytesIO()
    byte_img = Image.open('user.jpg')
    byte_img.save(byte_img_IO, "PNG")
    byte_img_IO.seek(0)
    byte_img = byte_img_IO.read()
    os.remove('user.jpg')
    
    #Создание клавы "хобби"
    markup = types.ReplyKeyboardMarkup(resize_keyboard = True)
    for hobby in hobbies:
        markup.add(hobby[1])
    #сохранение массива байтов в FSMContext
    await state.update_data(photo = byte_img)
    await message.reply("Выберите свои хобби:", reply_markup = markup)

#последний хэндлер в цепочке; обрабатывает hobby
@dp.message_handler(state = Form.hobbies)
async def process_hobbies(message: types.Message, state: FSMContext):   
    async with state.proxy() as data:
        #Сохранение выбраного хобби в стейты
        for hobby in hobbies:
            if message.text == hobby[1]:
                data['hobby'] = hobby
        #конвертация байтов из FSMContext в фото и вывод
        byte_img = data['photo']
        data_bytes_IO = io.BytesIO(byte_img)
        img = Image.open(data_bytes_IO)
        img.save('user_output.jpg')
        user_photo = open('user_output.jpg', "rb")
        
        #загрузка данных из стейтов в переменные
        telegram_id = str(message.chat.id)
        telegram_username = str(message.chat.username)
        name = str(data['name'])
        age = int(data['age'])
        gender = str(data['gender'])
        city = str(data['city'])
        phone_number = str(data['phone_number'])
        hobby = data['hobby'][0]
        
        
        #загрузка данных юзера в БД
        query = ("""INSERT INTO users(user_telegram_id, username_telegram, fullname, age, gender, phone_number, city, user_photo, hobbyID) VALUES(?,?,?,?,?,?,?,?,?)""")
        cursor.execute(query, telegram_id, telegram_username, name, age, gender, phone_number, city, byte_img, hobby)
        
        
        #отправляем фото, закрываем стрим который читает файл c фото, удаляем сохраненное фото
        await bot.send_photo(chat_id = message.chat.id, photo = user_photo)
        user_photo.close()
        os.remove('user_output.jpg')
        
        
        #Отправляем сообщение с данными, которые внес юзер
        await bot.send_message(
            message.chat.id,
            md.text(
                md.text('UID Телеграмма: ', md.bold(telegram_id)),
                md.text('Юзернейм: ', md.bold(telegram_username)),
                md.text('ФИО: ', md.bold(name)),
                md.text('Возраст: ', md.bold(age)),
                md.text('Пол: ', md.bold(gender)),
                md.text('Номер телефона: ', md.bold(phone_number)),
                md.text('Город: ', md.bold(city)),
                md.text('Город: ', md.bold(data['hobby'][1])),
                sep= '\n',
            ),  
            parse_mode = ParseMode.MARKDOWN, reply_markup = types.ReplyKeyboardRemove()
        )
    #заканчиваем обработку и закрываем FSM
    await state.finish()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
