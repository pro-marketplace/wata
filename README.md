# WATA Payment Integration

Интеграция платёжной системы WATA для приёма онлайн-платежей.

## Что включено

- `backend/wata/` — создание заказа и ссылки на оплату
- `backend/wata-webhook/` — обработка webhook от WATA
- `frontend/useWata.ts` — React хук для работы с API
- `frontend/PaymentButton.tsx` — готовый компонент кнопки оплаты

## Установка

### 1. База данных

Выполни миграцию для создания таблиц заказов:

```sql
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    order_number VARCHAR(50) UNIQUE NOT NULL,
    user_name VARCHAR(255) NOT NULL,
    user_email VARCHAR(255) NOT NULL,
    user_phone VARCHAR(50),
    amount DECIMAL(10, 2) NOT NULL,
    wata_order_id INTEGER UNIQUE,
    wata_transaction_id VARCHAR(100),
    status VARCHAR(20) DEFAULT 'pending',
    payment_url TEXT,
    delivery_address TEXT,
    order_comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
    product_id VARCHAR(100),
    product_name VARCHAR(255) NOT NULL,
    product_price DECIMAL(10, 2) NOT NULL,
    quantity INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_orders_wata_order_id ON orders(wata_order_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
```

### 2. Секреты

Добавь секреты в проект:

| Переменная | Описание |
|------------|----------|
| `WATA_API_TOKEN` | API токен от WATA |
| `WATA_API_URL` | URL API (по умолчанию `https://api.wata.pro/api/h2h`) |

### 3. Backend

Скопируй папки `backend/wata/` и `backend/wata-webhook/` в свой проект и выполни sync_backend.

### 4. Frontend

Скопируй файлы из `frontend/` в свой проект и добавь `PaymentButton` в форму оплаты:

```tsx
import { PaymentButton } from "@/components/PaymentButton";

<PaymentButton
  apiUrl={func2url.wata}
  amount={totalAmount}
  userName={formData.name}
  userEmail={formData.email}
  userPhone={formData.phone}
  userAddress={formData.address}
  cartItems={cartItems}
  successUrl="https://your-site.com/success"
  failUrl="https://your-site.com/checkout"
  onSuccess={(orderNumber) => router.push(`/success?order=${orderNumber}`)}
  onError={(error) => toast.error(error.message)}
/>
```

### 5. Настройка WATA

В личном кабинете WATA укажи:

- **Webhook URL**: URL функции `wata-webhook` из func2url.json

## Поток оплаты

```
1. Пользователь нажимает "Оплатить"
   ↓
2. Frontend → POST /wata (amount, user_name, cart_items...)
   ↓
3. Backend создаёт заказ в БД, запрашивает payment_url у WATA API
   ↓
4. Frontend редиректит на страницу оплаты WATA
   ↓
5. Пользователь оплачивает
   ↓
6. WATA → POST /wata-webhook (transactionId, orderId, transactionStatus...)
   ↓
7. Backend проверяет RSA подпись, обновляет status = 'paid'
   ↓
8. WATA редиректит на Success URL
```

## API

### POST /wata

Создание заказа и получение ссылки на оплату.

**Request:**
```json
{
  "amount": 1500.00,
  "user_name": "Иван Иванов",
  "user_email": "ivan@example.com",
  "user_phone": "+79991234567",
  "user_address": "Москва, ул. Примерная, 1",
  "cart_items": [
    {"id": "1", "name": "Товар", "price": 1500, "quantity": 1}
  ],
  "success_url": "https://your-site.com/success",
  "fail_url": "https://your-site.com/failed"
}
```

**Response:**
```json
{
  "payment_url": "https://pay.wata.pro/...",
  "order_id": 123,
  "order_number": "ORD-20241228-456789",
  "wata_transaction_id": "abc123..."
}
```

### POST /wata-webhook

Webhook от WATA (вызывается автоматически после оплаты).

**Headers:**
- `X-Signature` — RSA подпись payload (SHA512)

**Response:** `{"status": "ok"}` при успехе

## Особенности WATA

- **Подпись webhook**: RSA с SHA512 (публичный ключ получается через API)
- **Статусы**: `success`, `completed`, `paid` — успех; `failed`, `error`, `rejected` — ошибка
- **Поля webhook**: `transactionId`, `orderId`, `transactionStatus`, `amount`, `currency`

## Чеклист

- [ ] Миграция БД применена
- [ ] Секрет `WATA_API_TOKEN` добавлен
- [ ] Backend функции задеплоены (sync_backend)
- [ ] PaymentButton добавлен в форму оплаты
- [ ] Webhook URL настроен в кабинете WATA
- [ ] Тестовый платёж проходит успешно
