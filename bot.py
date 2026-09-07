# --- АЛГОРИТМ РАСЧЕТА ТОЛЩИНЫ СТЕКЛА ---
def calculate_glass_thickness(length_cm: float, width_cm: float, height_cm: float) -> tuple[float, int, str]:
    if height_cm <= 0 or length_cm <= 0 or width_cm <= 0:
        raise ValueError("Размеры должны быть больше нуля.")

    # Плавная шкала базовой толщины от высоты
    if height_cm <= 30:
        base_mm = 3.5
    elif height_cm <= 35:
        base_mm = 4.5
    elif height_cm <= 40:
        base_mm = 5.5
    elif height_cm <= 45:
        base_mm = 6.5
    elif height_cm <= 50:
        base_mm = 7.8
    elif height_cm <= 55:
        base_mm = 8.8
    elif height_cm <= 60:
        base_mm = 9.8
    elif height_cm <= 65:
        base_mm = 10.8
    elif height_cm <= 70:
        base_mm = 11.8
    else:
        base_mm = height_cm * 0.175

    # Соотношение длины к высоте
    ratio = length_cm / height_cm
    if ratio <= 1.0:
        factor = 0.85
    elif ratio <= 1.5:
        factor = 0.90 + (ratio - 1.0) * 0.10
    elif ratio <= 2.0:
        factor = 0.95 + (ratio - 1.5) * 0.12
    elif ratio <= 2.5:
        factor = 1.01 + (ratio - 2.0) * 0.10
    else:
        factor = 1.06 + (ratio - 2.5) * 0.08

    # Поправка на ширину
    if width_cm > height_cm + 10:
        w_h_ratio = width_cm / height_cm
        factor += (w_h_ratio - 1.0) * 0.08

    exact_mm = base_mm * factor

    standard_sizes = [4, 5, 6, 8, 10, 12, 15, 19, 25]
    recommended_size = standard_sizes[-1]
    
    for size in standard_sizes:
        if size + 0.05 >= exact_mm:
            recommended_size = size
            break

    # Порог мастерской: минимум 6 мм при длине или ширине от 50 см
    if (length_cm >= 50 or width_cm >= 50) and recommended_size < 6:
        recommended_size = 6

    # Экспертные пороги для бескаркасных систем (Rimless) по стандарту мастерской
    # Высший приоритет — крупногабаритные и высокие системы
    if (length_cm >= 150 and height_cm >= 55) or (length_cm >= 120 and height_cm >= 60) or height_cm >= 75:
        if recommended_size < 15:
            recommended_size = 15
    elif (115 <= length_cm <= 125) and (42 <= height_cm <= 48):
        recommended_size = 12  # Стандарт для 120х45х45
    elif (length_cm >= 90 and height_cm >= 60) or (length_cm >= 100 and height_cm >= 50) or (length_cm >= 120 and height_cm >= 45):
        if recommended_size < 12:
            recommended_size = 12  # 90х60х60, 100х50х50, 120х45х45 -> 12 мм
    elif (75 <= length_cm <= 95) and (42 <= height_cm <= 55):
        if recommended_size < 10:
            recommended_size = 10  # 80х50х50, 90х50х50 -> 10 мм
    elif length_cm >= 80 or height_cm >= 40:
        if recommended_size < 8:
            recommended_size = 8

    bracing_text = "Не требуются"
    if length_cm >= 140 and recommended_size < 15:
        bracing_text = "Рекомендуются рёбра жесткости"
    elif length_cm >= 180:
        bracing_text = "Требуются рёбра жесткости и стяжка"

    return round(exact_mm, 2), recommended_size, bracing_text
