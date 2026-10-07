// Zustand store for UI selections that must survive navigation: the active customer and the meter shown on the usage page.
import { create } from 'zustand'

interface UiState {
  selectedCustomerId: string | null
  selectedMeter: string | null
  setSelectedCustomerId: (id: string | null) => void
  setSelectedMeter: (meter: string | null) => void
}

export const useUiStore = create<UiState>()((set) => ({
  selectedCustomerId: null,
  selectedMeter: null,
  setSelectedCustomerId: (id) =>
    set((state) => {
      if (state.selectedCustomerId === id) return state
      // Meters belong to the customer's plan; a stale selection would point at a meter the new customer may not have.
      return { selectedCustomerId: id, selectedMeter: null }
    }),
  setSelectedMeter: (meter) => set({ selectedMeter: meter }),
}))
