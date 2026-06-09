import streamlit as st
import base64
import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)

#--------------------------------------------------------------------------------------
st.sidebar.header("Настройки AI")
ai_model = st.sidebar.selectbox(
    "Модель для анализа",
    [
        #"google/gemini-2.0-flash-exp:free",
        #"qwen/qwen-2.5-vl:free",
        #"meta-llama/llama-3.2-11b-vision:free",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "sourceful/riverflow-v2.5-pro:free",
        "sourceful/riverflow-v2.5-fast:free",
        "nvidia/nemotron-3.5-content-safety:free",
        "x-ai/grok-imagine-image-quality",
        "recraft/recraft-v4.1-utility-pro",
        "google/gemma-4-26b-a4b-it:free"
    ],
    index=0
)
#--------------------------------------------------------------------------------------

# todo: тарифы расчета стоимости
TARIFFS = {
    "gold_price": {"375": 2000, "585": 3500, "750": 4500},
    "type_coefficient": {
        "Кольцо": 1.0, "Серьги": 1.1, "Браслет": 1.0,
        "Кулон": 0.9, "Цепь": 0.85, "Колье": 0.95
    },
    "condition_coefficient": {
        "Как новое": 1.0, "Среднее": 0.8, "Плохое": 0.6
    },
    "inserts_coefficient": {"Да": 1.2, "Нет": 1.0},
    "ltv_ratio": 0.6,
    "interest_14d": 1.15
}

st.set_page_config(page_title="Из Уфы с любовью", layout="centered")
st.title("AI-сервис предварительной оценки ювелирных изделий")

#----------------------------- Форма --------------------------------------------
st.header("Загрузка информации об изделии")

col1, col2 = st.columns(2)
with col1:
    item_type = st.selectbox("Тип изделия",
        ["Кольцо", "Серьги", "Браслет", "Кулон", "Цепь", "Колье"])
    purity = st.selectbox("Проба металла", ["375", "585", "750"])

    # чекбокс - нужно ли показывать поле веса
    show_weight = st.checkbox("Указать вес изделия?")

    # пустой контейнер
    weight_container = st.empty()

    # если чекбокс отмечен, добавляем поле ввода в контейнер
    if show_weight:
        weight = weight_container.number_input("Вес (грамм)", min_value=0.1, max_value=500.0,
                             value=3.5, step=0.1, help="Необязательное поле")
    else:
        # если не отмечен — очищаем контейнер (поле исчезает)
        weight_container.empty()
        weight = 1 # Значение по умолчанию, если поле скрыто

    #weight = st.number_input("Вес (грамм)", min_value=0.1, max_value=500.0,
    #                         value=3.5, step=0.1, help="Необязательное поле")

with col2:
    has_inserts = st.selectbox("Наличие вставок", ["Да", "Нет"])
    condition = st.selectbox("Состояние изделия",
        ["Как новое", "Среднее", "Плохое"])

uploaded_file = st.file_uploader("Загрузите фото изделия",
                                  type=["jpg", "jpeg", "png"],
                                  accept_multiple_files=False)

if uploaded_file:
    st.image(uploaded_file, caption="Загруженное фото", use_container_width=True)

#-------------- анализ фото и сверка с данными пользователя (с защитой от ошибок) -------------------
def analyze_jewelry_ai(image_bytes, user_data):
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    prompt = f"""Ты эксперт-товаровед ломбарда. Тебе нужно оценить примерную стоимость ювелирного изделия по фото.
    Проанализируй фото ювелирного изделия.
    Определи тип изделия на фото, наличие вставок, наличие дефектов. Если возможно, определи пробу металла.

    Пользователь указал:
    - Тип: {user_data['type']}
    - Проба: {user_data['purity']}
    - Вставки: {user_data['inserts']}
    - Состояние: {user_data['condition']}

    Определи по фото и верни ТОЛЬКО валидный JSON без markdown, без пояснений, без кавычек вокруг скобок:
    {{
    "detected_type": "Кольцо|Серьги|Браслет|Кулон|Цепь|Колье|Не определено",
    "ai_detected_inserts": "Да|Нет",
    "ai_condition": "Как новое|Среднее|Плохое",
    "defects": ["царапины", "потертости", "деформация", "повреждение вставок", "нет"],
    "insert_damage": "Да|Нет",
    "ai_confidence": 0.8,
    "match_with_user": "Высокое|Среднее|Низкое"
    }}

    ВАЖНО: Ответ должен начинаться с {{ и заканчиваться на }}. Никакого текста до и после JSON.
    Если фото нечеткое - ставь ai_confidence ниже 0.5."""

    try:
        response = client.chat.completions.create(
            model=ai_model,
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                ]}
            ],
            temperature=0.2,
            max_tokens=800
        )

        # вывод сырого ответа в терминал для отладки
        raw_content = response.choices[0].message.content
        print(f"RAW AI RESPONSE: {raw_content}")

        # проверка на пустой ответ
        if raw_content is None or raw_content.strip() == "":
            print("AI вернул пустой ответ, используем fallback")
            raise ValueError("Empty response from AI")

        # очистка от markdown (если модель все-таки обернула в ```)
        clean_content = raw_content.strip()
        if clean_content.startswith("```"):
            clean_content = clean_content.split("```")[1]
            if clean_content.startswith("json"):
                clean_content = clean_content[4:]
        clean_content = clean_content.strip()

        # парсинг json
        return json.loads(clean_content)

    except Exception as e:
        print(f"Ошибка AI: {e}")

        # усредненный ответ на основе данных пользователя
        st.warning("AI временно недоступен. Расчет выполнен на основе ваших данных.")
        return {
            "detected_type": user_data["type"],
            "ai_detected_inserts": user_data["inserts"],
            "ai_condition": user_data["condition"],
            "defects": ["нет"] if user_data["condition"] == "Как новое" else ["потертости"],
            "insert_damage": "Нет",
            "ai_confidence": 0.6,
            "match_with_user": "Высокое"
        }

#-------------------------------------------------------------------------------------------
# todo - алгоритм расчета ?
def calculate_valuation(user_data, ai_data, weight):
    """Расчет по тарифным сеткам"""

    #todo: если вес не указан
    # Базовая стоимость металла
    base_price = weight * TARIFFS["gold_price"][user_data["purity"]]

    # Коэффициенты
    type_coef = TARIFFS["type_coefficient"].get(user_data["type"], 1.0)
    condition_coef = TARIFFS["condition_coefficient"][user_data["condition"]]
    inserts_coef = TARIFFS["inserts_coefficient"][user_data["inserts"]]

    # Штраф за дефекты
    defect_penalty = 1.0
    if "деформация" in ai_data.get("defects", []):
        defect_penalty -= 0.2
    if "повреждение вставок" in ai_data.get("defects", []):
        defect_penalty -= 0.15
    if ai_data.get("insert_damage") == "Да":
        defect_penalty -= 0.1

    # Итоговая стоимость
    item_value = (base_price * type_coef * condition_coef *
                  inserts_coef * defect_penalty)

    # Сумма займа и выкупа
    loan_amount = int(item_value * TARIFFS["ltv_ratio"])
    redemption_amount = int(loan_amount * TARIFFS["interest_14d"])

    # Вероятность принятия
    confidence = ai_data.get("ai_confidence", 0.5)
    match = ai_data.get("match_with_user", "Среднее")

    if confidence >= 0.7 and match == "Высокое" and defect_penalty >= 0.9:
        probability = "Высокая"
    elif confidence >= 0.5 and defect_penalty >= 0.7:
        probability = "Средняя"
    else:
        probability = "Низкая"

    return {
        "loan": max(500, loan_amount),
        "redemption": redemption_amount,
        "probability": probability,
        "item_value": int(item_value),
        "ai_details": ai_data
    }

#-------------------------- выбор филиала ------------------------------------------------------------
def choose_filial():
    #st.write("Карта подразделений (в разработке)")
    st.subheader("Выберите удобное подразделение")
    return None

#------------------------------- Кнопка анализа -------------------------------------------------
if uploaded_file and st.button("Получить предварительную оценку", type="primary"):

    # Предупреждение
    st.warning("Расчет является предварительным и выполнен на основании фотографий. "
               "Окончательная оценка определяется специалистом после очного осмотра.")

    with st.spinner("AI анализирует фото..."):
        try:
            # Данные пользователя
            user_data = {
                "type": item_type,
                "purity": purity,
                "inserts": has_inserts,
                "condition": condition
            }

            # AI анализ
            image_bytes = uploaded_file.getvalue()
            ai_result = analyze_jewelry_ai(image_bytes, user_data)

            # Расчет
            result = calculate_valuation(user_data, ai_result, weight)

            # Показ результатов
            st.success("Анализ завершен!")

            col1, col2, col3 = st.columns(3)
            col1.metric("Сумма займа", f"{result['loan']} ₽")
            col2.metric("Сумма выкупа", f"{result['redemption']} ₽")
            col3.metric("Вероятность принятия", result['probability'])

            st.info(f"Расчет приведен для веса {weight} г")

            # Детали AI
            with st.expander("Подробнее..."):
                st.json(result['ai_details'])
                st.write(f"**Расчетная стоимость изделия:** {result['item_value']} ₽")

            # Повторное предупреждение
            st.info("Предварительная оценка. Окончательная сумма определяется после очного осмотра.")

            # Кнопки конверсии
            st.header("Следующие шаги")
            col_a, col_b = st.columns(2)

            with col_a:
                if st.button("️Выбрать подразделение", use_container_width=True):
                    #choose_filial_result = choose_filial()
                    choose_filial()
                    #st.write("Карта подразделений (в разработке)")
                    # todo: интеграция с картой

            with col_b:
                if st.button("Заказать обратный звонок", use_container_width=True):
                    #todo
                    choose_filial()
                    #st.write("### Форма обратного звонка")
                    #name = st.text_input("ФИО *")
                    #phone = st.text_input("Номер телефона *")
                    #if st.button("Отправить заявку"):
                    #    if name and phone:
                    #        st.success("Заявка отправлена! (демо)")
                    #        # todo: создание сделки в Bitrix24
                    #    else:
                    #        st.error("Заполните обязательные поля")

        except Exception as e:
            st.error(f"Ошибка анализа: {e}")
