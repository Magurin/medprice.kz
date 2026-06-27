"use client";

import { useEffect, useState } from "react";

// Корзина услуг для сравнения по клиникам. Хранится в localStorage,
// синхронизация между вкладками/компонентами - через события.
const KEY = "medprice_basket";
const EVENT = "medprice_basket_change";

export interface BasketItem {
  code: string;
  name: string;
}

function read(): BasketItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as BasketItem[]) : [];
  } catch {
    return [];
  }
}

function write(items: BasketItem[]) {
  localStorage.setItem(KEY, JSON.stringify(items));
  window.dispatchEvent(new CustomEvent(EVENT));
}

export function addToBasket(item: BasketItem) {
  const items = read();
  if (!items.some((i) => i.code === item.code)) write([...items, item]);
}

export function removeFromBasket(code: string) {
  write(read().filter((i) => i.code !== code));
}

export function clearBasket() {
  write([]);
}

export function inBasket(code: string): boolean {
  return read().some((i) => i.code === code);
}

// React-хук: актуальный список + реакция на изменения (в т.ч. из других вкладок).
export function useBasket(): BasketItem[] {
  const [items, setItems] = useState<BasketItem[]>([]);
  useEffect(() => {
    const sync = () => setItems(read());
    sync();
    window.addEventListener(EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  return items;
}
