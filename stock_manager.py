import os
import random

# --- Конфигурация файла стока ---
STOCK_FILE = "verblud_squad.txt"
SEPARATOR = "----------------------------------------------------------------------------"

def ensure_stock_file_exists(filename=STOCK_FILE, separator=SEPARATOR):
    """
    Проверяет существование файла стока и создает его, если не найден.
    При создании добавляет начальный и конечный разделитель для корректного формата.
    """
    if not os.path.exists(filename):
        print(f"INFO: Создание пустого файла стока {filename}")
        try:
            with open(filename, "w", encoding="utf-8") as f:
                # Добавляем разделители, чтобы парсинг всегда работал корректно
                f.write(f"{separator}\n{separator}\n")
        except Exception as e:
            print(f"ERROR creating stock file: {e}")

def load_all_products(filename=STOCK_FILE):
    """
    Читает файл запасов и возвращает список всех блоков товара ("междустрочий").
    """
    ensure_stock_file_exists(filename) # Гарантируем, что файл существует
        
    try:
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read().strip()
    except Exception as e:
        print(f"ERROR reading stock file: {e}")
        return []
    
    # Разделяем контент по разделителю и фильтруем пустые строки/блоки
    blocks = [block.strip() for block in content.split(SEPARATOR) if block.strip()]
    return blocks

def create_delivery_file_content(blocks, separator=SEPARATOR):
    """
    Форматирует выбранные блоки в контент для файла клиента.
    """
    # Соединяем блоки, обрамляя каждый разделителем
    content = f"\n{separator}\n".join(blocks)
    
    # Добавляем разделители в начало и конец файла для чистоты
    return f"{separator}\n{content}\n{separator}\n"

def update_stock_file(remaining_blocks, filename=STOCK_FILE, separator=SEPARATOR):
    """
    Перезаписывает файл запасов оставшимися блоками.
    """
    if not remaining_blocks:
        new_content = f"{separator}\n" 
    else:
        blocks_content = f"\n{separator}\n".join(remaining_blocks)
        new_content = f"{separator}\n{blocks_content}\n{separator}\n"
    
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"INFO: Stock file {filename} updated. Remaining stock: {len(remaining_blocks)}")
    except Exception as e:
        print(f"ERROR writing stock file: {e}")


def deliver_products(quantity: int, filename=STOCK_FILE):
    """
    Загружает сток, рандомно выбирает 'quantity' позиций, обновляет файл,
    и возвращает контент для файла доставки.
    
    Возвращает: (delivery_content: str, remaining_stock: int)
    """
    all_blocks = load_all_products(filename)
    total_stock = len(all_blocks)
    
    if quantity > total_stock:
        raise ValueError("Requested quantity exceeds available stock.")
    
    # 1. Рандомно выбираем блоки
    selected_blocks = random.sample(all_blocks, quantity)
    
    # 2. Определяем оставшиеся блоки (удаляем выбранные из копии)
    temp_all_blocks = all_blocks[:] 
    for block in selected_blocks:
        try:
            temp_all_blocks.remove(block) 
        except ValueError:
            pass 
            
    remaining_blocks = temp_all_blocks
    
    # 3. Обновляем файл запасов
    update_stock_file(remaining_blocks, filename)
    
    # 4. Создаем контент для доставки
    delivery_content = create_delivery_file_content(selected_blocks)
    
    return delivery_content, len(remaining_blocks)

def get_initial_stock_count(filename=STOCK_FILE):
    """
    Возвращает текущее количество товаров (междустрочий) на складе.
    """
    return len(load_all_products(filename))
