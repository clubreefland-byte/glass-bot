# Мастерские лимиты безопасности для открытых аквариумов
    if height_cm <= 25 and (length_cm >= 80 or width_cm >= 80) and exact_mm < 7.8:
        exact_mm = 7.8  # Широкие мелкие фраговики/поддоны -> 8 мм
    elif height_cm <= 30 and exact_mm <= 4.0:
        exact_mm = 3.8  
    elif height_cm <= 36 and exact_mm <= 5.0:
        exact_mm = 5.1  
    elif length_cm == 60 and height_cm == 60:
        exact_mm = 10.0  
    elif length_cm == 65 and height_cm == 65:
        exact_mm = 12.0  
    elif length_cm == 70 and height_cm == 70:
        exact_mm = 12.0  
    elif length_cm == 80 and height_cm == 80:
        exact_mm = 15.0  
    elif length_cm <= 110 and height_cm == 55:
        exact_mm = 11.8  # 100x55x55 и 110x55x55 -> 12 мм
    elif 100 <= length_cm <= 120 and height_cm == 60:
        exact_mm = 12.0  # 100x60x60, 110x60x60, 120x60x60 -> 12 мм
    elif length_cm <= 110 and height_cm == 70:
        exact_mm = 14.8  # 100x70x70 и 110x70x70 -> 15 мм
    elif height_cm == 45 and 80 <= length_cm < 120 and exact_mm < 8.1:
        exact_mm = 8.1  
    elif length_cm >= 100 and height_cm >= 50 and exact_mm < 10.1 and height_cm < 55:
        exact_mm = 10.1  
    elif length_cm >= 120 and height_cm >= 45 and exact_mm < 10.1 and height_cm < 55:
        exact_mm = 10.1  
    elif length_cm >= 150 and exact_mm < 12.1:
        exact_mm = 12.1
