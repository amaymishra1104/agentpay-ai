"use client";

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import {
  DEFAULT_CUSTOMER_ID,
  SESSION_STORAGE_KEY_PREFIX,
  getStoredCartId,
  setStoredCartId,
  clearStoredCartId,
} from "./api";

export interface DemoCustomer {
  id: string;
  name: string;
  label: string;
  email: string;
  badge: string;
  role: string;
}

export const DEMO_CUSTOMERS: DemoCustomer[] = [
  {
    id: "c_demo_001",
    name: "Customer A",
    label: "Customer A (Alex Chen)",
    email: "customer.a@example.com",
    badge: "Premium Runner",
    role: "Verified Demo Persona",
  },
  {
    id: "c_demo_002",
    name: "Customer B",
    label: "Customer B (Sarah Connor)",
    email: "customer.b@example.com",
    badge: "Standard Buyer",
    role: "Isolated Demo Persona",
  },
];

const ACTIVE_CUSTOMER_STORAGE_KEY = "agentpay_active_customer_id";
const CUSTOMER_CHANGE_EVENT = "agentpay:customer_change";

interface CustomerContextType {
  customer: DemoCustomer;
  customerId: string;
  setCustomerId: (id: string) => void;
  availableCustomers: DemoCustomer[];
  getSessionId: () => string;
  getActiveCartId: () => string | null;
  setActiveCartId: (cartId: string) => void;
  clearActiveCartId: () => void;
}

const CustomerContext = createContext<CustomerContextType | undefined>(undefined);

export function CustomerProvider({ children }: { children: React.ReactNode }) {
  const [customerId, setCustomerIdState] = useState<string>(DEFAULT_CUSTOMER_ID);

  useEffect(() => {
    const saved = window.localStorage.getItem(ACTIVE_CUSTOMER_STORAGE_KEY);
    if (saved && DEMO_CUSTOMERS.some((c) => c.id === saved)) {
      setCustomerIdState(saved);
    }

    const handleStorage = (e: StorageEvent) => {
      if (e.key === ACTIVE_CUSTOMER_STORAGE_KEY && e.newValue) {
        if (DEMO_CUSTOMERS.some((c) => c.id === e.newValue)) {
          setCustomerIdState(e.newValue);
        }
      }
    };

    const handleCustomChange = (e: Event) => {
      const detail = (e as CustomEvent<{ customerId: string }>).detail;
      if (detail?.customerId && DEMO_CUSTOMERS.some((c) => c.id === detail.customerId)) {
        setCustomerIdState(detail.customerId);
      }
    };

    window.addEventListener("storage", handleStorage);
    window.addEventListener(CUSTOMER_CHANGE_EVENT, handleCustomChange);
    return () => {
      window.removeEventListener("storage", handleStorage);
      window.removeEventListener(CUSTOMER_CHANGE_EVENT, handleCustomChange);
    };
  }, []);

  const setCustomerId = useCallback((newId: string) => {
    if (!DEMO_CUSTOMERS.some((c) => c.id === newId)) return;
    setCustomerIdState(newId);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ACTIVE_CUSTOMER_STORAGE_KEY, newId);
      window.dispatchEvent(
        new CustomEvent(CUSTOMER_CHANGE_EVENT, { detail: { customerId: newId } })
      );
    }
  }, []);

  const customer =
    DEMO_CUSTOMERS.find((c) => c.id === customerId) || DEMO_CUSTOMERS[0];

  const getSessionId = useCallback(() => {
    if (typeof window === "undefined") return `buyer-${customerId}-default`;
    const key = `${SESSION_STORAGE_KEY_PREFIX}${customerId}`;
    let sid = window.sessionStorage.getItem(key);
    if (!sid) {
      sid = `buyer-${customerId}-${crypto.randomUUID()}`;
      window.sessionStorage.setItem(key, sid);
    }
    return sid;
  }, [customerId]);

  const getActiveCartId = useCallback(() => {
    const sid = getSessionId();
    return getStoredCartId(sid, customerId);
  }, [customerId, getSessionId]);

  const setActiveCartId = useCallback(
    (cartId: string) => {
      const sid = getSessionId();
      setStoredCartId(cartId, sid, customerId);
    },
    [customerId, getSessionId]
  );

  const clearActiveCartId = useCallback(() => {
    const sid = getSessionId();
    clearStoredCartId(sid, customerId);
  }, [customerId, getSessionId]);

  return (
    <CustomerContext.Provider
      value={{
        customer,
        customerId,
        setCustomerId,
        availableCustomers: DEMO_CUSTOMERS,
        getSessionId,
        getActiveCartId,
        setActiveCartId,
        clearActiveCartId,
      }}
    >
      {children}
    </CustomerContext.Provider>
  );
}

export function useCustomer(): CustomerContextType {
  const context = useContext(CustomerContext);
  if (!context) {
    // Fallback if rendered outside provider
    const fallbackCustomer = DEMO_CUSTOMERS[0];
    return {
      customer: fallbackCustomer,
      customerId: fallbackCustomer.id,
      setCustomerId: () => {},
      availableCustomers: DEMO_CUSTOMERS,
      getSessionId: () => `buyer-${DEFAULT_CUSTOMER_ID}-fallback`,
      getActiveCartId: () => getStoredCartId(null, DEFAULT_CUSTOMER_ID),
      setActiveCartId: (cartId: string) => setStoredCartId(cartId, null, DEFAULT_CUSTOMER_ID),
      clearActiveCartId: () => clearStoredCartId(null, DEFAULT_CUSTOMER_ID),
    };
  }
  return context;
}
