import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
import math
from telegram.error import Conflict

# Включаем логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния для конечного автомата
MATERIAL, OPERATION, TOOL_TYPE, TOOL_SUBTYPE, DIAMETER, NUMBER_OF_TEETH, DEPTH_OF_CUT, RADIUS, GROOVE_WIDTH = range(9)

# Рекомендованные параметры резания (примерные данные из каталогов ZCC)
cutting_parameters = {
    'сталь': {
        'фрезерование': {
            'монолитная': {
                'цилиндрическая': {'скорость': [80, 120], 'подача': [0.1, 0.3], 'глубина': [1, 4]},
                'сферическая': {'скорость': [70, 110], 'подача': [0.08, 0.25], 'глубина': [1, 3]}
            },
            'с_пластинами': {
                'торцевая': {'скорость': [100, 150], 'подача': [0.15, 0.35], 'глубина': [1, 5]},
                'пазовая': {'скорость': [90, 140], 'подача': [0.1, 0.3], 'глубина': [1, 4]}
            }
        },
        'точение': {
            'проходной': {
                'радиус_пластины': {
                    0.4: {'скорость': [70, 100], 'подача': [0.1, 0.3], 'глубина': [1, 5]},
                    0.8: {'скорость': [80, 110], 'подача': [0.15, 0.35], 'глубина': [1, 5]},
                    1.2: {'скорость': [90, 120], 'подача': [0.2, 0.4], 'глубина': [1, 5]}
                }
            },
            'канавочный': {
                'ширина_пластины': {
                    2.0: {'скорость': [40, 60], 'подача': [0.05, 0.15]},
                    3.0: {'скорость': [50, 70], 'подача': [0.08, 0.2]},
                    4.0: {'скорость': [60, 80], 'подача': [0.1, 0.25]}
                }
            }
        },
        'сверление': {
            'монолитное': {
                'hss': {'скорость': [30, 50], 'подача': [0.05, 0.12], 'глубина': [1, 8]},
                'hss-co': {'скорость': [40, 60], 'подача': [0.08, 0.15], 'глубина': [1, 10]},
                'твердый_сплав': {'скорость': [70, 100], 'подача': [0.1, 0.2], 'глубина': [1, 12]}
            },
            'со_сменными_пластинами': {
                'карбид': {'скорость': [70, 100], 'подача': [0.1, 0.2], 'глубина': [1, 12]}
            }
        }
    },
    'цветной_металл': {
        'фрезерование': {
            'монолитная': {
                'цилиндрическая': {'скорость': [150, 200], 'подача': [0.2, 0.4], 'глубина': [2, 6]},
                'сферическая': {'скорость': [140, 180], 'подача': [0.15, 0.35], 'глубина': [2, 5]}
            },
            'с_пластинами': {
                'торцевая': {'скорость': [180, 250], 'подача': [0.25, 0.45], 'глубина': [2, 8]},
                'пазовая': {'скорость': [160, 220], 'подача': [0.2, 0.4], 'глубина': [2, 6]}
            }
        },
        'точение': {
            'проходной': {
                'радиус_пластины': {
                    0.4: {'скорость': [120, 150], 'подача': [0.15, 0.3], 'глубина': [2, 6]},
                    0.8: {'скорость': [130, 160], 'подача': [0.2, 0.35], 'глубина': [2, 6]},
                    1.2: {'скорость': [140, 180], 'подача': [0.25, 0.4], 'глубина': [2, 6]}
                }
            },
            'канавочный': {
                'ширина_пластины': {
                    2.0: {'скорость': [80, 120], 'подача': [0.1, 0.2]},
                    3.0: {'скорость': [90, 130], 'подача': [0.15, 0.25]},
                    4.0: {'скорость': [100, 140], 'подача': [0.2, 0.3]}
                }
            }
        },
        'сверление': {
            'монолитное': {
                'hss': {'скорость': [60, 80], 'подача': [0.1, 0.2], 'глубина': [2, 10]},
                'hss-co': {'скорость': [70, 90], 'подача': [0.15, 0.25], 'глубина': [2, 12]},
                'твердый_сплав': {'скорость': [100, 150], 'подача': [0.2, 0.3], 'глубина': [2, 15]}
            },
            'со_сменными_пластинами': {
                'карбид': {'скорость': [100, 150], 'подача': [0.2, 0.3], 'глубина': [2, 15]}
            }
        }
    }
}

def calculate_cutting_width(diameter, depth_of_cut, tool_subtype):
    """Расчет ширины резания в зависимости от типа фрезы."""
    if tool_subtype == 'цилиндрическая':
        return 0.5 * diameter
    elif tool_subtype == 'сферическая':
        return 2 * math.sqrt(depth_of_cut * (diameter - depth_of_cut))
    else:
        return None

def calculate_overlap(diameter, depth_of_cut):
    """Расчет величины съема в зависимости от глубины резания и диаметра фрезы."""
    if depth_of_cut <= 0.3 * diameter:
        return 100
    elif depth_of_cut <= 0.5 * diameter:
        return 70
    elif depth_of_cut <= 0.7 * diameter:
        return 50
    elif depth_of_cut <= diameter:
        return 30
    elif depth_of_cut <= 2 * diameter:
        return 10
    else:
        return None

def start(update: Update, context: CallbackContext) -> int:
    """Начало диалога, запрос материала."""
    # Сбрасываем все данные пользователя
    context.user_data.clear()

    # Предлагаем выбрать материал
    materials = ['сталь', 'цветной_металл']
    reply_keyboard = [[material] for material in materials]
    reply_keyboard.append(['/start'])
    update.message.reply_text(
        "Привет! Я помогу вам выбрать оптимальные режимы резания. "
        "Для начала выберите материал заготовки:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    return MATERIAL

def material(update: Update, context: CallbackContext) -> int:
    """Обработка выбора материала."""
    material = update.message.text.lower()
    if material == '/start':
        return start(update, context)
    context.user_data['material'] = material
    if material in cutting_parameters:
        operations = list(cutting_parameters[material].keys())
        reply_keyboard = [[operation] for operation in operations]
        reply_keyboard.append(['/start'])
        update.message.reply_text(
            f"Отлично! Теперь выберите тип операции для материала {material}:",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
        )
        return OPERATION
    else:
        update.message.reply_text("Извините, я не могу найти параметры для этого материала. Попробуйте снова.")
        return ConversationHandler.END

def operation(update: Update, context: CallbackContext) -> int:
    """Обработка выбора операции."""
    operation = update.message.text.lower()
    if operation == '/start':
        return start(update, context)
    context.user_data['operation'] = operation
    if operation in cutting_parameters[context.user_data['material']]:
        tool_types = list(cutting_parameters[context.user_data['material']][operation].keys())
        reply_keyboard = [[tool_type] for tool_type in tool_types]
        reply_keyboard.append(['/start'])
        update.message.reply_text(
            f"Выберите тип инструмента для операции {operation}:",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
        )
        return TOOL_TYPE
    else:
        update.message.reply_text("Извините, я не могу найти параметры для этой операции. Попробуйте снова.")
        return ConversationHandler.END

def tool_type(update: Update, context: CallbackContext) -> int:
    """Обработка выбора типа инструмента."""
    tool_type = update.message.text.lower()
    if tool_type == '/start':
        return start(update, context)
    context.user_data['tool_type'] = tool_type
    material = context.user_data['material']
    operation = context.user_data['operation']

    if tool_type in cutting_parameters[material][operation]:
        if operation == 'фрезерование':
            if tool_type == 'монолитная' or tool_type == 'с_пластинами':
                subtypes = list(cutting_parameters[material][operation][tool_type].keys())
                reply_keyboard = [[subtype] for subtype in subtypes]
                reply_keyboard.append(['/start'])
                update.message.reply_text(
                    "Выберите тип фрезы:",
                    reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
                )
                return TOOL_SUBTYPE
        elif operation == 'точение':
            if tool_type == 'канавочный':
                update.message.reply_text("Введите ширину пластины (в мм):")
                return GROOVE_WIDTH
            elif tool_type == 'проходной':
                radii = list(cutting_parameters[material][operation][tool_type]['радиус_пластины'].keys())
                reply_keyboard = [[str(radius)] for radius in radii]
                reply_keyboard.append(['/start'])
                update.message.reply_text(
                    "Выберите радиус пластины (в мм):",
                    reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
                )
                return RADIUS
        elif operation == 'сверление':
            if tool_type == 'монолитное':
                subtypes = list(cutting_parameters[material][operation][tool_type].keys())
                reply_keyboard = [[subtype] for subtype in subtypes]
                reply_keyboard.append(['/start'])
                update.message.reply_text(
                    "Выберите тип сверла:",
                    reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
                )
                return TOOL_SUBTYPE
            else:
                update.message.reply_text("Введите диаметр сверла (в мм):")
                return DIAMETER
    else:
        update.message.reply_text("Извините, я не могу найти параметры для этого типа инструмента. Попробуйте снова.")
        return ConversationHandler.END

def tool_subtype(update: Update, context: CallbackContext) -> int:
    """Обработка выбора подтипа инструмента."""
    tool_subtype = update.message.text.lower()
    if tool_subtype == '/start':
        return start(update, context)
    context.user_data['tool_subtype'] = tool_subtype
    if context.user_data['operation'] == 'фрезерование':
        update.message.reply_text("Введите диаметр фрезы (в мм):")
        return DIAMETER
    elif context.user_data['operation'] == 'сверление':
        update.message.reply_text("Введите диаметр сверла (в мм):")
        return DIAMETER
    else:
        update.message.reply_text("Извините, произошла ошибка. Попробуйте снова.")
        return ConversationHandler.END

def diameter(update: Update, context: CallbackContext) -> int:
    """Обработка ввода диаметра."""
    try:
        diameter = float(update.message.text.replace(',', '.'))
        context.user_data['diameter'] = diameter
        if context.user_data['operation'] == 'фрезерование':
            update.message.reply_text("Введите количество зубьев фрезы:")
            return NUMBER_OF_TEETH
        elif context.user_data['operation'] == 'сверление':
            params = get_cutting_parameters(context)
            if not params:
                update.message.reply_text("Ошибка: не удалось получить параметры резания.")
                return ConversationHandler.END
            recommended_speed = (params['скорость'][0] + params['скорость'][1]) / 2
            recommended_feed = (params['подача'][0] + params['подача'][1]) / 2
            n = (1000 * recommended_speed) / (math.pi * diameter)
            feed_per_minute = recommended_feed * n
            result_message = format_result(context, recommended_speed, recommended_feed, None, n, feed_per_minute)
            update.message.reply_text(result_message, reply_markup=ReplyKeyboardMarkup([[KeyboardButton('/start')]], one_time_keyboard=True))
            return ConversationHandler.END
        else:
            update.message.reply_text("Введите глубину резания в мм (используйте точку для десятичных значений):")
            return DEPTH_OF_CUT
    except ValueError:
        update.message.reply_text("Пожалуйста, введите числовое значение для диаметра (используйте точку для десятичных значений).")
        return DIAMETER

def number_of_teeth(update: Update, context: CallbackContext) -> int:
    """Обработка ввода количества зубьев."""
    try:
        number_of_teeth = int(update.message.text)
        context.user_data['number_of_teeth'] = number_of_teeth
        update.message.reply_text("Введите глубину резания в мм (используйте точку для десятичных значений):")
        return DEPTH_OF_CUT
    except ValueError:
        update.message.reply_text("Пожалуйста, введите целое число для количества зубьев.")
        return NUMBER_OF_TEETH

def depth_of_cut(update: Update, context: CallbackContext) -> int:
    """Обработка ввода глубины резания и вывод результатов."""
    try:
        depth_of_cut = float(update.message.text.replace(',', '.'))
        context.user_data['depth_of_cut'] = depth_of_cut
        params = get_cutting_parameters(context)
        if not params:
            update.message.reply_text("Ошибка: не удалось получить параметры резания.")
            return ConversationHandler.END
        
        # Расчет ширины резания
        diameter = context.user_data.get('diameter', None)
        tool_subtype = context.user_data.get('tool_subtype', None)
        if diameter and tool_subtype:
            cutting_width = calculate_cutting_width(diameter, depth_of_cut, tool_subtype)
        else:
            cutting_width = None

        # Расчет величины съема (перекрытия)
        if diameter:
            overlap = calculate_overlap(diameter, depth_of_cut)
        else:
            overlap = None

        recommended_speed = (params['скорость'][0] + params['скорость'][1]) / 2
        recommended_feed = (params['подача'][0] + params['подача'][1]) / 2
        recommended_depth = (params['глубина'][0] + params['глубина'][1]) / 2 if 'глубина' in params else None
        n = (1000 * recommended_speed) / (math.pi * context.user_data.get('diameter', None)) if context.user_data.get('diameter', None) else None
        feed_per_minute = recommended_feed * n if n else None
        
        result_message = format_result(context, recommended_speed, recommended_feed, recommended_depth, n, feed_per_minute, cutting_width, overlap)
        update.message.reply_text(result_message, reply_markup=ReplyKeyboardMarkup([[KeyboardButton('/start')]], one_time_keyboard=True))
        return ConversationHandler.END
    except ValueError:
        update.message.reply_text("Пожалуйста, введите числовое значение для глубины резания (используйте точку для десятичных значений).")
        return DEPTH_OF_CUT

def radius(update: Update, context: CallbackContext) -> int:
    """Обработка ввода радиуса пластины."""
    try:
        radius = float(update.message.text.replace(',', '.'))
        context.user_data['radius'] = radius
        params = get_cutting_parameters(context)
        if not params:
            update.message.reply_text("Ошибка: не удалось получить параметры резания.")
            return ConversationHandler.END
        recommended_speed = (params['скорость'][0] + params['скорость'][1]) / 2
        recommended_feed = (params['подача'][0] + params['подача'][1]) / 2
        recommended_depth = (params['глубина'][0] + params['глубина'][1]) / 2 if 'глубина' in params else None
        update.message.reply_text(f"Рекомендованные параметры для {context.user_data['material']} ({context.user_data['operation']}) с пластиной радиусом {radius} мм:")
        update.message.reply_text(f"Скорость резания: {recommended_speed:.1f} м/мин")
        update.message.reply_text(f"Подача: {recommended_feed:.2f} мм/об")
        if recommended_depth:
            update.message.reply_text(f"Глубина резания: {recommended_depth:.1f} мм")
        update.message.reply_text("Для нового расчета нажмите /start", reply_markup=ReplyKeyboardMarkup([[KeyboardButton('/start')]], one_time_keyboard=True))
        return ConversationHandler.END
    except ValueError:
        update.message.reply_text("Пожалуйста, введите числовое значение для радиуса (используйте точку для десятичных значений).")
        return RADIUS

def groove_width(update: Update, context: CallbackContext) -> int:
    """Обработка ввода ширины канавки."""
    try:
        groove_width = float(update.message.text.replace(',', '.'))
        context.user_data['groove_width'] = groove_width
        params = get_cutting_parameters(context)
        if not params:
            update.message.reply_text("Ошибка: не удалось получить параметры резания.")
            return ConversationHandler.END
        recommended_speed = (params['скорость'][0] + params['скорость'][1]) / 2
        recommended_feed = (params['подача'][0] + params['подача'][1]) / 2
        update.message.reply_text(f"Рекомендованные параметры для {context.user_data['material']} ({context.user_data['operation']}) с шириной канавки {groove_width} мм:")
        update.message.reply_text(f"Скорость резания: {recommended_speed:.1f} м/мин")
        update.message.reply_text(f"Подача: {recommended_feed:.2f} мм/об")
        update.message.reply_text("Для нового расчета нажмите /start", reply_markup=ReplyKeyboardMarkup([[KeyboardButton('/start')]], one_time_keyboard=True))
        return ConversationHandler.END
    except ValueError:
        update.message.reply_text("Пожалуйста, введите числовое значение для ширины канавки (используйте точку для десятичных значений).")
        return GROOVE_WIDTH

def get_cutting_parameters(context):
    """Получение параметров резания из базы данных."""
    material = context.user_data.get('material')
    operation = context.user_data.get('operation')
    tool_type = context.user_data.get('tool_type')
    tool_subtype = context.user_data.get('tool_subtype', None)
    radius = context.user_data.get('radius', None)
    groove_width = context.user_data.get('groove_width', None)

    if not material or not operation or not tool_type:
        return None

    try:
        if operation == 'фрезерование':
            if tool_type in ['монолитная', 'с_пластинами'] and tool_subtype:
                return cutting_parameters[material][operation][tool_type].get(tool_subtype, None)
        elif operation == 'точение':
            if tool_type == 'проходной' and radius:
                return cutting_parameters[material][operation][tool_type]['радиус_пластины'].get(radius, None)
            elif tool_type == 'канавочный' and groove_width:
                return cutting_parameters[material][operation][tool_type]['ширина_пластины'].get(groove_width, None)
        elif operation == 'сверление':
            if tool_type == 'монолитное' and tool_subtype:
                return cutting_parameters[material][operation][tool_type].get(tool_subtype, None)
            elif tool_type == 'со_сменными_пластинами':
                return cutting_parameters[material][operation][tool_type].get('карбид', None)
    except KeyError:
        return None

def format_result(context, speed, feed, depth=None, n=None, feed_per_minute=None, cutting_width=None, overlap=None):
    """Форматирование результата для вывода."""
    result = f"Рекомендованные параметры для {context.user_data.get('material', 'неизвестный материал')} ({context.user_data.get('operation', 'неизвестная операция')}) с инструментом {context.user_data.get('tool_type', 'неизвестный тип инструмента')}"
    if context.user_data.get('tool_subtype'):
        result += f" ({context.user_data['tool_subtype']})"
    result += ":\n"
    result += f"Скорость резания: {speed:.1f} м/мин\n"
    result += f"Подача: {feed:.2f} мм/об\n"
    if feed_per_minute:
        result += f"Минутная подача: {feed_per_minute:.1f} мм/мин\n"
    
    # Убираем вывод глубины резания для фрез
    if context.user_data.get('operation') != 'фрезерование' and depth:
        result += f"Глубина резания: {depth:.1f} мм\n"
    
    # Заменяем ширину резания на величину перекрытия, умноженную на диаметр
    diameter = context.user_data.get('diameter', None)
    if overlap and diameter:
        result += f"Ширина резания: {overlap * diameter / 100:.1f} мм\n"
    
    if n:
        result += f"Частота вращения шпинделя: {n:.0f} об/мин\n"
    
    # Добавляем сообщение с благодарностью и информацией для поддержки
    result += "\nЕсли вам понравился бот, вы можете поддержать автора Дмитрий П.:\n"
    result += "💳 Счет Сбербанк для поддержки: 2202 2081 6242 6036\n"
    result += "📧 Обратная связь: fetamlet@yandex.ru"
    
    return result

def cancel(update: Update, context: CallbackContext) -> int:
    """Отмена диалога."""
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.first_name)
    update.message.reply_text('Операция отменена.', reply_markup=ReplyKeyboardMarkup([[KeyboardButton('/start')]], one_time_keyboard=True))
    return ConversationHandler.END

def main() -> None:
    """Запуск бота."""
    updater = Updater("7817179504:AAHfUlKxlKmLlGJQlyeq30EE6ZSYdwLNfoc", use_context=True)  # Замените YOUR_BOT_TOKEN на токен вашего бота
    dispatcher = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MATERIAL: [MessageHandler(Filters.text & ~Filters.command, material)],
            OPERATION: [MessageHandler(Filters.text & ~Filters.command, operation)],
            TOOL_TYPE: [MessageHandler(Filters.text & ~Filters.command, tool_type)],
            TOOL_SUBTYPE: [MessageHandler(Filters.text & ~Filters.command, tool_subtype)],
            DIAMETER: [MessageHandler(Filters.text & ~Filters.command, diameter)],
            NUMBER_OF_TEETH: [MessageHandler(Filters.text & ~Filters.command, number_of_teeth)],
            DEPTH_OF_CUT: [MessageHandler(Filters.text & ~Filters.command, depth_of_cut)],
            RADIUS: [MessageHandler(Filters.text & ~Filters.command, radius)],
            GROOVE_WIDTH: [MessageHandler(Filters.text & ~Filters.command, groove_width)]
        },
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', start)],  # Добавляем /start в fallbacks
    )

    dispatcher.add_handler(conv_handler)

    try:
        updater.start_polling()
        updater.idle()
    except Conflict:
        logger.error("Конфликт: уже запущен другой экземпляр бота. Убедитесь, что бот не запущен в другом месте.")
    except Exception as e:
        logger.error(f"Произошла ошибка: {e}")

if __name__ == '__main__':
    main()