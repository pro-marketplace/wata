/**
 * WATA Payment Hook
 *
 * Хук для интеграции с WATA в React приложении.
 */
import { useState, useCallback } from "react";

// ============================================================================
// ТИПЫ
// ============================================================================

export interface CartItem {
  id: string;
  name: string;
  price: number;
  quantity: number;
}

export interface PaymentPayload {
  amount: number;
  userName: string;
  userEmail: string;
  userPhone: string;
  userAddress?: string;
  orderComment?: string;
  cartItems: CartItem[];
  successUrl?: string;
  failUrl?: string;
}

export interface PaymentResponse {
  payment_url: string;
  order_id: number;
  order_number: string;
  wata_transaction_id: string;
}

interface UseWataOptions {
  apiUrl: string;
  onSuccess?: (orderNumber: string) => void;
  onError?: (error: Error) => void;
}

interface UseWataReturn {
  createPayment: (payload: PaymentPayload) => Promise<PaymentResponse>;
  isLoading: boolean;
  error: Error | null;
  paymentUrl: string | null;
  orderNumber: string | null;
}

// ============================================================================
// ХУК
// ============================================================================

export function useWata(options: UseWataOptions): UseWataReturn {
  const { apiUrl, onError } = options;

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [paymentUrl, setPaymentUrl] = useState<string | null>(null);
  const [orderNumber, setOrderNumber] = useState<string | null>(null);

  /**
   * Создаёт платёж и возвращает ссылку на оплату
   */
  const createPayment = useCallback(
    async (payload: PaymentPayload): Promise<PaymentResponse> => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await fetch(apiUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            amount: payload.amount,
            user_name: payload.userName,
            user_email: payload.userEmail,
            user_phone: payload.userPhone,
            user_address: payload.userAddress,
            order_comment: payload.orderComment,
            cart_items: payload.cartItems,
            success_url: payload.successUrl,
            fail_url: payload.failUrl,
          }),
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.error || "Payment creation failed");
        }

        const data: PaymentResponse = await response.json();

        setPaymentUrl(data.payment_url);
        setOrderNumber(data.order_number);

        // Сохраняем pending order в localStorage
        localStorage.setItem("pending_order", data.order_number);

        return data;
      } catch (err) {
        const error = err instanceof Error ? err : new Error("Unknown error");
        setError(error);
        onError?.(error);
        throw error;
      } finally {
        setIsLoading(false);
      }
    },
    [apiUrl, onError]
  );

  return {
    createPayment,
    isLoading,
    error,
    paymentUrl,
    orderNumber,
  };
}

// ============================================================================
// УТИЛИТЫ
// ============================================================================

/**
 * Открывает страницу оплаты
 * На мобильных устройствах открывает в новом окне
 */
export function openPaymentPage(paymentUrl: string): void {
  const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);

  if (isMobile) {
    window.open(paymentUrl, "_blank");
  } else {
    window.location.href = paymentUrl;
  }
}

/**
 * Форматирует телефон в формат +7 (XXX) XXX-XX-XX
 */
export function formatPhoneNumber(phone: string): string {
  const digits = phone.replace(/\D/g, "");

  if (digits.length === 0) return "";
  if (digits.length <= 1) return `+${digits}`;
  if (digits.length <= 4) return `+${digits.slice(0, 1)} (${digits.slice(1)}`;
  if (digits.length <= 7)
    return `+${digits.slice(0, 1)} (${digits.slice(1, 4)}) ${digits.slice(4)}`;
  if (digits.length <= 9)
    return `+${digits.slice(0, 1)} (${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;

  return `+${digits.slice(0, 1)} (${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7, 9)}-${digits.slice(9, 11)}`;
}

/**
 * Валидирует email
 */
export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

/**
 * Валидирует телефон (11 цифр)
 */
export function isValidPhone(phone: string): boolean {
  const digits = phone.replace(/\D/g, "");
  return digits.length === 11;
}
