"use client";

import { PraticheForCustomersPanel } from "@/components/pratiche-for-customers-panel";

/** "Miei Clienti" (Session 36, reorganised in Session 67): the promoter's
    CRM and the one place where they activate contracts for their customers
    -- a new customer registered here (with their own login, see
    network/service.py::create_recruited_customer) or one they already have,
    through the same pratica wizard the customer uses. The screen itself is
    shared with the administration's "Nuovo Contratto". */
export function NetworkCustomersPanel() {
  return <PraticheForCustomersPanel mode="promoter" />;
}
