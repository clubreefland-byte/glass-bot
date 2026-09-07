# --- АЛГОРИТМ РАСЧЕТА ТОЛЩИНЫ СТЕКЛА И ЗАПАСА ПРОЧНОСТИ ---
def calculate_glass_thickness(length_cm: float, width_cm: float, height_cm: float) -> tuple[float, int, float, str]:
    if height_cm <= 0 or length_cm <= 0 or width_cm <= 0:
        raise ValueError("Размеры должны быть больше нуля.")

    if height_cm <= 30:
        base_mm = 3.5
    elif height_cm <= 35:
        base_mm = 4.5
    elif height_cm <= 40:
        base_mm = 5.5
    elif height_cm <= 45:
        base_mm = 6.5
    elif height_cm <= 50:
        base_mm = 8.0
    elif height_cm <= 55:
        base_mm = 9.5
    elif height_cm <= 60:
        base_mm = 10.8
    else:
        base_mm = height_cm * 0.19

    # Коэффициент соотношения длины и высоты
    ratio = length_cm / height_cm
    if ratio <= 1.0:
        factor = 0.90
    elif ratio <= 1.5:
        factor = 0.95 + (ratio - 1.0) * 0.10
    elif ratio <= 2.0:
        factor = 1.00 + (ratio - 1.5) * 0.12
    elif ratio <= 2.5:
        factor = 1.06 + (ratio - 2.0) * 0.10
    else:
        factor = 1.11 + (ratio - 2.5) * 0.08

    # Поправка на ширину (если аквариум широкий/глубокий)
    width_ratio = width_cm / length_cm
    if width_ratio > 0.40:
        factor += (width_ratio - 0.40) * 0.08

    exact_mm = base_mm * factor

    standard_sizes = [4, 5, 6, 8, 10, 12, 15, 19, 25]
    recommended_size = standard_sizes[-1]
    
    for size in standard_sizes:
        if size + 0.05 >= exact_mm:
            recommended_size = size
            break

    if length_cm >= 160 and height_cm >= 55 and recommended_size < 15:
        recommended_size = 15
    elif length_cm >= 130 and height_cm >= 50 and recommended_size < 12:
        recommended_size = 12
    elif length_cm >= 100 and height_cm >= 45 and recommended_size < 10:
        recommended_size = 10

    bracing_text = "Не требуются"
    if length_cm >= 140 and recommended_size < 15:
        bracing_text = "Рекомендуются рёбра жесткости"
    elif length_cm >= 180:
        bracing_text = "Требуются рёбра жесткости и стяжка"

    if exact_mm <= 0:
        safety_factor = 99.0
    else:
        safety_factor = round(3.8 * (recommended_size / exact_mm) ** 2, 1)

    return round(exact_mm, 2), recommended_size, safety_factor, bracing_text
