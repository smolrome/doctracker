import { create } from 'zustand';

interface ModalState {
  // Incrementing this triggers the add-document modal in _layout.tsx
  addModalTrigger: number;
  triggerAddModal: () => void;

  // Cart count mirrored from _layout.tsx so dashboard can read it
  cartCount: number;
  setCartCount: (n: number) => void;

  // Cart visibility mirror
  openCart: () => void;
  cartOpenTrigger: number;
}

export const useModalStore = create<ModalState>((set) => ({
  addModalTrigger: 0,
  triggerAddModal: () => set((s) => ({ addModalTrigger: s.addModalTrigger + 1 })),

  cartCount: 0,
  setCartCount: (n) => set({ cartCount: n }),

  cartOpenTrigger: 0,
  openCart: () => set((s) => ({ cartOpenTrigger: s.cartOpenTrigger + 1 })),
}));
