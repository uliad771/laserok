# LaserOK — Django + PostgreSQL

POS-система, склад, отчёты и управление товарами с фотографиями.

## Установка

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Создайте БД PostgreSQL:

```sql
CREATE DATABASE laserok;
CREATE USER laserok WITH PASSWORD 'laserok_password';
GRANT ALL PRIVILEGES ON DATABASE laserok TO laserok;
```

Запуск:

```bash
python manage.py makemigrations core
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Откройте http://127.0.0.1:8000/

Демо: `admin/admin`, `kassir/kassir`.

## Фото товаров

В разделе «Товары» нажмите «Добавить товар» или «Изменить».

- Поддерживаются JPG, PNG и WebP.
- Максимальный размер — 5 МБ.
- Файлы сохраняются в `media/products/ГОД/МЕСЯЦ/`.
- Фото отображается в таблице товаров и в POS-каталоге.
- При загрузке нового фото старое удаляется с диска.

## Удаление товаров

- Если у товара не было продаж и складских движений — он удаляется полностью вместе с фото.
- Если история есть — товар архивируется: `is_active=False`, `is_public=False`. Это сохраняет целостность отчётов и истории продаж.

## Продакшен

```bash
DEBUG=False
SECRET_KEY=длинный-случайный-ключ
ALLOWED_HOSTS=ваш-домен.ru
```

Для раздачи media в production используйте Nginx или объектное хранилище S3/MinIO.
